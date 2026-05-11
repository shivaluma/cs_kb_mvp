from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas import (
    ExtractedUnitsPayload,
    GroundedAnswerPayload,
    RetrievalResponse,
    WorkflowExtractionPayload,
)


SYSTEM_PROMPT = """Bạn trích xuất bản nháp SOP chăm sóc khách hàng từ tài liệu nguồn lộn xộn.
Quy tắc:
- Chỉ trích xuất sự thật có trong tài liệu nguồn.
- Không tự tạo policy, điều kiện xử lý, cảnh báo rủi ro, hoặc nhánh workflow không có trong nguồn.
- Chỉ trả JSON, không giải thích ngoài JSON.
- Tất cả unit chỉ là bản nháp để CS Ops review, không được xem là đã phê duyệt.
- Mọi trường user-facing phải viết bằng tiếng Việt tự nhiên: title, content, note, script, warning, summary.
- Không dùng nhãn tiếng Anh chung chung như "Curated content", "Extracted workflow unit", "Workflow overview", "Initial verification script".
- Title của mỗi atomic unit phải là nhãn ngắn 4-10 từ để scan/search, không copy cả câu content. Ví dụ dạng tốt: "Thời hạn khiếu nại món ăn", "Không cung cấp mã đơn", "Kiểm tra thông tin trên hệ thống".
- Content mới là rule/action đầy đủ. Nếu title và content gần giống nhau, title bị xem là kém chất lượng.
- Giữ nguyên mã nghiệp vụ/ký hiệu/viết tắt đúng như xuất hiện trong tài liệu nguồn.
- Ưu tiên unit nhỏ, dễ review: workflow_overview, verification_dependency, workflow_step, decision_point, macro_script, operational_note, security_note, related_document.
- Mỗi unit bắt buộc có source_refs để trace ngược về nguồn. Mỗi source_ref bắt buộc có source_type và source_file.
- source_refs theo loại file: Excel dùng {source_type:"excel", source_file, sheet, row_start, row_end, column_names}; PDF dùng {source_type:"pdf", source_file, page, bbox nếu có}; DOCX dùng {source_type:"docx", source_file, paragraph_index hoặc heading_path}; text/markdown dùng {source_type:"text", source_file, line_start, line_end}.
- Không có source_refs thì output bị reject.
"""


def enabled() -> bool:
    return bool(settings.openrouter_api_key.strip())


def completion_content(payload: dict[str, Any], headers: dict[str, str]) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=settings.openrouter_timeout_seconds) as client:
                response = client.post(
                    f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
            return str(body["choices"][0]["message"]["content"])
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else 0
            if status not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                break
            retry_after = exc.response.headers.get("retry-after") if exc.response is not None else ""
            try:
                delay = min(float(retry_after), 6.0) if retry_after else 0.8 * (attempt + 1)
            except ValueError:
                delay = 0.8 * (attempt + 1)
            time.sleep(delay)
        except httpx.TransportError as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.6 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("openrouter_empty_response")


def parse_llm_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                return parsed
            except json.JSONDecodeError:
                continue
        raise


def parse_json_with_repair(content: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[Any, bool]:
    try:
        return parse_llm_json(content), False
    except json.JSONDecodeError as exc:
        repair_payload = {
            **payload,
            "temperature": 0,
            "messages": [
                *payload["messages"],
                {"role": "assistant", "content": content[:20000]},
                {
                    "role": "user",
                    "content": (
                        "Output trước không phải JSON hợp lệ. Hãy trả lại CHỈ MỘT JSON object hợp lệ, "
                        "không markdown, không giải thích, không bỏ field bắt buộc. "
                        f"Lỗi parser: {exc.msg} tại vị trí {exc.pos}."
                    ),
                },
            ],
        }
        return parse_llm_json(completion_content(repair_payload, headers)), True


def validate_workflow_payload_with_repair(
    parsed: Any,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> tuple[WorkflowExtractionPayload, bool]:
    try:
        return WorkflowExtractionPayload.model_validate(parsed), False
    except ValidationError as exc:
        repair_payload = {
            **payload,
            "temperature": 0,
            "messages": [
                *payload["messages"],
                {"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False)[:24000]},
                {
                    "role": "user",
                    "content": (
                        "JSON trên hợp lệ nhưng sai schema. Hãy chuyển nó sang ĐÚNG shape bắt buộc: "
                        "{\"document_metadata\":{},\"full_sop\":{},\"workflow_graph\":{},\"annotations\":[],\"uncertain_edges\":[],\"validation_errors\":[],\"atomic_units\":[],\"warnings\":[],\"search_enrichment\":{}}. "
                        "Không bỏ full_sop. Không bỏ workflow_graph. Nếu graph có nodes/edges trong text hoặc units, hãy tạo workflow_graph từ đó. "
                        "Nếu chỉ có units legacy, hãy chọn/tạo unit full_sop từ nội dung tổng quan và đưa các unit còn lại vào atomic_units. "
                        "Notes/scripts/warnings phải nằm trong annotations, không nằm trong workflow_graph.nodes nếu không phải bước chính. "
                        "Chỉ trả JSON object hợp lệ, không markdown. "
                        f"Validation errors: {validation_summary(exc)}"
                    ),
                },
            ],
        }
        repaired = parse_llm_json(completion_content(repair_payload, headers))
        return WorkflowExtractionPayload.model_validate(repaired), True


def validate_workflow_topology_with_repair(
    payload_model: WorkflowExtractionPayload,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> tuple[WorkflowExtractionPayload, bool, list[str]]:
    errors, warnings = validate_workflow_topology(payload_model)
    if not errors:
        payload_model.warnings = [*payload_model.warnings, *warnings]
        return payload_model, False, []

    repair_payload = {
        **payload,
        "temperature": 0,
        "messages": [
            *payload["messages"],
            {"role": "assistant", "content": payload_model.model_dump_json()[:30000]},
            {
                "role": "user",
                "content": (
                    "Graph topology đang sai nghiêm trọng. Hãy sửa JSON, không bịa policy ngoài ảnh/source. "
                    "Quy tắc bắt buộc: không suy edge từ thứ tự text; chỉ tạo edge khi thấy mũi tên/connector/Yes-No/quan hệ step rõ trong ảnh. "
                    "Không duplicate node cùng step/label. Notes, scripts, warnings, references, history/log blocks, và ghi chú phải đưa vào annotations attached_to node liên quan, không làm workflow step. "
                    "Decision node phải có nhánh yes/no nếu source có. Nếu không chắc edge, đưa vào uncertain_edges và không đưa vào edges. "
                    "Start không có incoming, End không có outgoing. "
                    "Trả đúng shape JSON có document_metadata, full_sop, workflow_graph, annotations, uncertain_edges, validation_errors, atomic_units, warnings, search_enrichment. "
                    f"Topology errors cần sửa: {'; '.join(errors[:12])}"
                ),
            },
        ],
    }
    try:
        repaired = parse_llm_json(completion_content(repair_payload, headers))
        repaired_model = WorkflowExtractionPayload.model_validate(repaired)
        repaired_errors, repaired_warnings = validate_workflow_topology(repaired_model)
        repaired_model.warnings = [*repaired_model.warnings, *repaired_warnings]
        return repaired_model, True, repaired_errors
    except Exception:
        return payload_model, False, errors


def validate_workflow_topology(payload_model: WorkflowExtractionPayload) -> tuple[list[str], list[str]]:
    graph = payload_model.workflow_graph
    errors: list[str] = []
    warnings: list[str] = [f"model_reported_validation_error:{error}" for error in payload_model.validation_errors]
    node_by_id = {node.id: node for node in graph.nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
    incoming: dict[str, list[str]] = {node.id: [] for node in graph.nodes}

    if len(node_by_id) != len(graph.nodes):
        errors.append("duplicate_node_id")

    labels: dict[str, list[str]] = {}
    for node in graph.nodes:
        label = normalized_workflow_label(node.title or node.question or node.content)
        if label and label not in {"start", "end"}:
            labels.setdefault(label, []).append(node.id)
    duplicate_labels = [label for label, ids in labels.items() if len(ids) > 1]
    if duplicate_labels:
        errors.append(f"duplicate_node_labels:{','.join(duplicate_labels[:3])}")

    for edge in graph.edges:
        if edge.from_node not in node_by_id:
            errors.append(f"edge_unknown_from:{edge.from_node}")
            continue
        if edge.to_node not in node_by_id:
            errors.append(f"edge_unknown_to:{edge.to_node}")
            continue
        outgoing[edge.from_node].append(edge.condition or "")
        incoming[edge.to_node].append(edge.condition or "")

    for node in graph.nodes:
        node_type = normalized_workflow_label(node.type)
        node_label = normalized_workflow_label(" ".join([node.title, node.question, node.content]))
        has_outgoing = bool(outgoing.get(node.id))
        has_incoming = bool(incoming.get(node.id))
        if is_annotation_like_node(node_type, node_label) and (has_outgoing or has_incoming):
            errors.append(f"annotation_used_as_flow_node:{node.id}")
        if is_start_node(node_type, node_label) and has_incoming:
            errors.append(f"start_has_incoming:{node.id}")
        if is_end_node(node_type, node_label) and has_outgoing:
            errors.append(f"end_has_outgoing:{node.id}")
        if is_decision_node(node_type, node_label, node.question):
            confirmed_conditions = [normalize_condition(condition) for condition in outgoing.get(node.id, [])]
            uncertain_conditions = [
                normalize_condition(edge.condition)
                for edge in payload_model.uncertain_edges
                if edge.from_node == node.id or edge.from_node == node.title or edge.from_node == node.question
            ]
            all_conditions = confirmed_conditions + uncertain_conditions
            if len(all_conditions) < 2:
                errors.append(f"decision_missing_two_branches:{node.id}")
            if len(all_conditions) >= 2 and not (has_yes_condition(all_conditions) and has_no_condition(all_conditions)):
                errors.append(f"decision_missing_yes_no_labels:{node.id}")
        if not has_incoming and not has_outgoing and not is_annotation_like_node(node_type, node_label):
            warnings.append(f"disconnected_node:{node.id}")

    edge_keys: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        key = (edge.from_node, edge.to_node, normalize_condition(edge.condition))
        if key in edge_keys:
            errors.append(f"duplicate_edge:{edge.from_node}->{edge.to_node}:{edge.condition}")
        edge_keys.add(key)

    if payload_model.uncertain_edges:
        warnings.append(f"uncertain_edges_require_review:{len(payload_model.uncertain_edges)}")
    if not payload_model.annotations:
        warnings.append("workflow_annotations_missing")
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def normalized_workflow_label(value: str) -> str:
    ascii_value = unicodedata.normalize("NFD", value or "").replace("đ", "d").replace("Đ", "D")
    ascii_value = "".join(char for char in ascii_value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9?]+", " ", ascii_value.lower()).strip()


def is_annotation_like_node(node_type: str, node_label: str) -> bool:
    type_signals = [
        "note",
        "annotation",
        "script",
        "macro",
        "warning",
        "security",
        "compliance",
        "reference",
        "history",
        "log",
        "operational note",
    ]
    label_signals = [
        "note",
        "annotation",
        "script",
        "macro",
        "warning",
        "reference",
        "history",
        "log",
        "luu y",
        "ghi chu",
        "canh bao",
        "bao mat",
        "tuan thu",
        "tham chieu",
        "lich su",
    ]
    return any(signal in node_type for signal in type_signals) or any(signal in node_label for signal in label_signals)


def is_decision_node(node_type: str, node_label: str, question: str) -> bool:
    return "decision" in node_type or bool(question.strip()) or "?" in node_label


def is_start_node(node_type: str, node_label: str) -> bool:
    return node_type == "start" or node_label in {"start", "bat dau"}


def is_end_node(node_type: str, node_label: str) -> bool:
    return node_type == "end" or node_label in {"end", "ket thuc"}


def normalize_condition(value: str) -> str:
    normalized = normalized_workflow_label(value)
    if normalized in {"yes", "y", "co", "dung", "co cung cap"}:
        return "yes"
    if normalized in {"no", "n", "khong", "khong co", "no response", "no or no response"}:
        return "no"
    return normalized or "next"


def has_yes_condition(conditions: list[str]) -> bool:
    return any(condition == "yes" or condition.startswith("yes ") for condition in conditions)


def has_no_condition(conditions: list[str]) -> bool:
    return any(condition == "no" or condition.startswith("no ") or "no response" in condition for condition in conditions)


def extract_workflow_units(
    filename: str,
    raw_text: str,
    page_images: list[str] | None = None,
    visual_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled():
        return [], ["openrouter_disabled"]

    extraction_prompt = (
        "Hãy trích xuất tài liệu workflow/swimlane SOP CS này thành JSON production draft. "
        "Trả đúng shape {\"document_metadata\":{},\"full_sop\":{},\"workflow_graph\":{},\"annotations\":[],\"uncertain_edges\":[],\"validation_errors\":[],\"atomic_units\":[],\"warnings\":[],\"search_enrichment\":{}}.\n\n"
        "QUY TẮC TOPOLOGY BẮT BUỘC:\n"
        "- Không được suy edge từ thứ tự text/OCR. Text order không phải flow order.\n"
        "- Chỉ tạo workflow_graph.edges khi thấy mũi tên/connector/nhãn Yes-No/quan hệ step rõ trong ảnh hoặc source.\n"
        "- Nếu không chắc mũi tên, đưa vào uncertain_edges với reason, không đưa vào edges.\n"
        "- Không duplicate node cùng số bước hoặc cùng label. Một step trong diagram chỉ là một node.\n"
        "- Notes, scripts, warnings, references, history/log blocks, ghi chú/rủi ro phải đưa vào annotations attached_to step liên quan; không biến thành workflow step và không tạo edge từ/to note.\n"
        "- Decision node phải có nhánh yes/no nếu diagram thể hiện Yes/No. Không đảo nhánh Yes/No.\n"
        "- Start không có incoming edge. End không có outgoing edge.\n"
        "- Phase/actor chỉ gán khi có căn cứ từ swimlane/label/source, không gán bừa.\n\n"
        "VISUAL GRAPH CANDIDATES:\n"
        "- Nếu có visual_layout/visual_graph_candidates bên dưới, hãy xem đó là evidence topology từ detector trước LLM.\n"
        "- Ưu tiên nodes/edge_candidates có bbox để tạo workflow_graph.nodes/edges và source_refs.bbox.\n"
        "- Edge candidate confidence thấp hoặc direction_reason là geometric_guess phải đưa vào uncertain_edges nếu ảnh không xác nhận rõ.\n"
        "- Không tạo edge mới ngoài edge_candidates trừ khi ảnh thể hiện mũi tên rất rõ.\n\n"
        "Yêu cầu document_metadata: title, effective_from nếu thấy trong nguồn, document_type=\"workflow_diagram\", sub_type nếu là swimlane_process, channel, audience, actors, phases, systems, risk_level, requires_layout_extraction=true, requires_human_review=true, extraction_confidence, required_unit_types.\n"
        "required_unit_types là danh sách generic các unit_type bắt buộc phải review trước publish dựa trên nội dung thật của source. Ví dụ nếu source có SLA thì thêm sla_rule; có handoff thì thêm handoff_rule; có cảnh báo bảo mật/compliance thì thêm security_note/compliance_note. Không thêm nếu source không có căn cứ.\n"
        "Yêu cầu full_sop: là ExtractedUnit unit_type=\"full_sop\", metadata.retrieval_scope=\"document\", title/content tiếng Việt, source_refs có page.\n"
        "Yêu cầu workflow_graph: workflow_id, title, start_node_id, nodes, edges, graph_confidence 0..1, requires_human_review=true, review_reason. "
        "Edge dùng field from_node/to_node/condition, không dùng field tên 'from'. "
        "Node cần actor, phase OPEN/BODY/CLOSE nếu có, type start/action/decision/end, title/content/question. "
        "Không dùng node type note/script/warning trong workflow_graph.nodes; dùng annotations.\n"
        "Yêu cầu annotations: note/script/warning/security/compliance/reference/history gắn attached_to node id liên quan, có source_refs.\n"
        "Yêu cầu uncertain_edges: mọi edge chưa chắc topology, có reason và confidence.\n"
        "Nếu arrow/Yes-No không chắc chắn, đặt graph_confidence thấp và review_reason rõ.\n"
        "Yêu cầu atomic_units: tạo unit nhỏ dễ search theo nội dung thật trong source, ví dụ operational_instruction, routing_rule, policy_rule, validation_rule, sla_rule, decision_rule, escalation_rule, case_creation_rule, handoff_rule, macro_script, compliance_note, security_note, operational_note. "
        "Nếu source có SLA, routing, escalation, case creation, handoff, macro/script, exception, warning, security/compliance note, hãy tách thành unit riêng tương ứng. "
        "Mỗi unit có tags/aliases/phase/actor/risk_level nếu có căn cứ trong source. "
        "Bắt buộc title/content tiếng Việt. Không bịa rule ngoài nguồn.\n"
        "Mỗi full_sop/atomic_unit phải có source_refs: PDF cần source_type=\"pdf_diagram\" hoặc \"pdf\", source_file, page; bbox nếu biết, nếu không để [].\n\n"
        f"Filename: {filename}\n\n"
        f"Visual layout candidates JSON:\n{json.dumps(visual_context or {}, ensure_ascii=False)[:18000]}\n\n"
        f"Source text:\n{raw_text[:16000]}"
    )
    user_content: str | list[dict[str, Any]]
    if page_images:
        user_content = [{"type": "text", "text": extraction_prompt}]
        user_content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in page_images[:3])
    else:
        user_content = extraction_prompt

    payload = {
        "model": settings.openrouter_vision_model if page_images else settings.openrouter_extraction_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }

    try:
        content = completion_content(payload, headers)
        parsed, repaired = parse_json_with_repair(content, payload, headers)
        payload_model, schema_repaired = validate_workflow_payload_with_repair(parsed, payload, headers)
        payload_model, topology_repaired, topology_errors = validate_workflow_topology_with_repair(payload_model, payload, headers)
        if topology_errors:
            payload_model.validation_errors = list(dict.fromkeys([*payload_model.validation_errors, *topology_errors]))
            payload_model.warnings = [
                *payload_model.warnings,
                "workflow_topology_requires_manual_review",
                *[f"workflow_topology_error:{error}" for error in topology_errors[:8]],
            ]
            payload_model.workflow_graph.requires_human_review = True
            if not payload_model.workflow_graph.review_reason:
                payload_model.workflow_graph.review_reason = "Graph topology has validator warnings and must be reviewed before publish."
        normalized = workflow_payload_to_units(payload_model, filename)
        missing_refs = source_ref_validation_errors(normalized, filename)
        if missing_refs:
            return [], missing_refs
        warnings = ["openrouter_workflow_extraction_used", *payload_model.warnings]
        if visual_context:
            warnings.append("visual_graph_context_used")
        if repaired:
            warnings.append("openrouter_json_repair_used")
        if schema_repaired:
            warnings.append("openrouter_schema_repair_used")
        if topology_repaired:
            warnings.append("openrouter_topology_repair_used")
        if payload_model.uncertain_edges:
            warnings.append(f"workflow_graph_has_{len(payload_model.uncertain_edges)}_uncertain_edges")
        if payload_model.validation_errors:
            warnings.extend(f"workflow_graph_validation_error:{error}" for error in payload_model.validation_errors[:8])
        if payload_model.workflow_graph.requires_human_review:
            warnings.append("workflow_graph_requires_human_review")
        return [unit for unit in normalized if unit["content"]], warnings
    except json.JSONDecodeError as exc:
        return [], [f"openrouter_workflow_invalid_json:{exc.msg}:{exc.pos}"]
    except ValidationError as exc:
        return [], [f"openrouter_workflow_validation_failed:{validation_summary(exc)}"]
    except Exception as exc:
        return [], [f"openrouter_extraction_failed:{exc.__class__.__name__}"]


def extract_rule_table_units(filename: str, raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled():
        return [], ["openrouter_disabled"]

    payload = {
        "model": settings.openrouter_extraction_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Hãy chuyển tài liệu Excel/bảng quy định CS này thành SOP draft có cấu trúc để CS Ops review. "
                    "Không hardcode và không tự bịa policy. Chỉ dùng thông tin có trong source.\n\n"
                    "Yêu cầu bắt buộc:\n"
                    "- Trả JSON shape {\"units\":[{\"unit_type\":\"...\",\"title\":\"...\",\"content\":\"...\",\"confidence\":0.0,\"metadata\":{...}}]}.\n"
                    "- title là nhãn ngắn 4-10 từ để agent scan/search; không copy nguyên câu content vào title.\n"
                    "- Phải có đúng 1 unit_type=\"full_sop\" với metadata.retrieval_scope=\"document\".\n"
                    "- Mỗi unit bắt buộc có source_refs. Excel cần source_refs[].sheet và row_start/row_end nếu rule đến từ dòng cụ thể. full_sop có thể dùng sheet/row range tổng.\n"
                    "- Tạo các unit nhỏ cho từng rule/action quan trọng với unit_type như routing_rule, validation_rule, handling_rule, warning, macro_script.\n"
                    "- Nếu có nhiều sheet theo ngày/version, chọn sheet mới nhất/hiện hành làm active rule units; sheet cũ chỉ ghi trong metadata.historical_sheets hoặc warning, không tạo active rule units từ sheet cũ.\n"
                    "- Với mỗi rule unit, metadata nên giữ các field/cột có trong bảng dưới dạng lowercase snake_case; ưu tiên source_sheet, source_row, domain, audience, priority, action, condition, owner, system, channel, risk_level, tags, aliases, case_reasons nếu có căn cứ.\n"
                    "- Nếu field không có trong source, không đoán. Để missing/null và thêm warning nếu quan trọng.\n"
                    "- title/content/user-facing metadata phải là tiếng Việt tự nhiên; UI labels vẫn do frontend xử lý.\n"
                    "- Nếu source thể hiện rủi ro tài chính, tài khoản, bảo mật/riêng tư, giao tiếp khách hàng, escalation, hoặc compliance, đặt metadata.risk_level phù hợp và tạo warning/compliance unit nếu đủ căn cứ.\n\n"
                    f"Filename: {filename}\n\nSource text:\n{raw_text[:50000]}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.05,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }

    try:
        content = completion_content(payload, headers)
        parsed, repaired = parse_json_with_repair(content, payload, headers)
        payload = ExtractedUnitsPayload.model_validate(parsed)
        normalized = [normalize_unit(unit.model_dump()) for unit in payload.units]
        usable = [unit for unit in normalized if unit["content"]]
        if not any(unit["unit_type"] == "full_sop" for unit in usable):
            return [], ["openrouter_missing_full_sop_unit"]
        missing_refs = source_ref_validation_errors(usable, filename)
        if missing_refs:
            return [], missing_refs
        warnings = ["openrouter_rule_table_extraction_used"]
        if repaired:
            warnings.append("openrouter_json_repair_used")
        return usable, warnings
    except json.JSONDecodeError as exc:
        return [], [f"openrouter_rule_table_invalid_json:{exc.msg}:{exc.pos}"]
    except ValidationError as exc:
        return [], [f"openrouter_rule_table_validation_failed:{validation_summary(exc)}"]
    except Exception as exc:
        return [], [f"openrouter_rule_table_extraction_failed:{exc.__class__.__name__}"]


def generate_grounded_answer(
    question: str,
    retrieval: RetrievalResponse,
    conversation: list[dict[str, str]] | None = None,
    model: str | None = None,
    strict_grounding: bool = True,
) -> tuple[GroundedAnswerPayload | None, list[str]]:
    if not enabled():
        return None, ["openrouter_disabled"]
    if not retrieval.results:
        return None, ["missing_published_sources"]

    sources = []
    for index, result in enumerate(retrieval.results, start=1):
        source_ref = f"[{index}] {result.title} v{result.version_number} / {result.section} / chunk {result.chunk_index}"
        metadata = {
            "unit_type": result.metadata.get("unit_type"),
            "retrieval_scope": result.metadata.get("retrieval_scope"),
            "risk_level": result.metadata.get("risk_level"),
            "tags": result.metadata.get("tags"),
            "aliases": result.metadata.get("aliases"),
        }
        sources.append(
            "\n".join(
                [
                    source_ref,
                    f"Heading: {result.heading}",
                    f"Source file: {result.source_filename}",
                    f"Metadata: {json.dumps(metadata, ensure_ascii=False)}",
                    f"Content: {result.content[:1800]}",
                ]
            )
        )

    conversation_text = "\n".join(
        f"{message.get('role', 'user')}: {message.get('content', '')[:800]}"
        for message in (conversation or [])[-6:]
        if message.get("content")
    )
    payload = {
        "model": model or settings.openrouter_chat_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Bạn là SOP-grounded assistant nội bộ cho CS. "
                    "Chỉ được trả lời dựa trên SOURCES là SOP units đã published. "
                    "Không dùng model knowledge ngoài sources. Không dùng raw upload, draft, archived content. "
                    "Nếu sources không đủ căn cứ, trả lời rằng không tìm thấy SOP published đủ tin cậy. "
                    "Không tự tạo policy, điều kiện xử lý, hoặc cảnh báo rủi ro ngoài source. "
                    "Câu trả lời phải ngắn, actionable, tiếng Việt, và có warning nếu source có risk/compliance/security/financial/account/escalation signal. "
                    + (
                        "Đây là câu hỏi có rủi ro cao hoặc policy/exception: nếu source không nêu rõ điều kiện/action, bắt buộc từ chối kết luận và hướng dẫn mở source/escalate Lead. "
                        "Không dùng ngôn ngữ chắc chắn cho refund/payment/account/privacy/ZT nếu citation không nói rõ. "
                        if strict_grounding
                        else ""
                    )
                    +
                    "Bắt buộc trả JSON object đúng schema: {\"answer\":\"...\",\"steps\":[\"...\"],\"warnings\":[\"...\"],\"confidence\":0.0,\"source_indices\":[1]}. "
                    "source_indices chỉ được chứa index của SOURCES đã dùng. Nếu không dùng source nào, để [] và answer phải nói không đủ căn cứ."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Recent conversation, for wording context only, not as source of policy:\n{conversation_text or '(none)'}\n\n"
                    "SOURCES, the only allowed evidence:\n"
                    + "\n\n---\n\n".join(sources)
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.05,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }

    try:
        content = completion_content(payload, headers)
        parsed, repaired = parse_json_with_repair(content, payload, headers)
        answer = GroundedAnswerPayload.model_validate(parsed)
        warnings = ["openrouter_grounded_answer_used", f"openrouter_model:{model or settings.openrouter_chat_model}"]
        if repaired:
            warnings.append("openrouter_json_repair_used")
        if not answer.source_indices:
            warnings.append("answer_without_citation_rejected")
            return GroundedAnswerPayload(
                answer="Không tìm thấy SOP published đủ căn cứ để trả lời chắc chắn. Vui lòng mở Lookup hoặc escalate Lead để xác nhận.",
                steps=[],
                warnings=["Không có citation hợp lệ từ SOP published."],
                confidence=0,
                source_indices=[],
            ), warnings
        return answer, warnings
    except Exception as exc:
        return None, [f"openrouter_grounded_answer_failed:{exc.__class__.__name__}"]


def suggest_document_metadata(
    filename: str,
    raw_text: str,
    document_type: str,
    source_type: str,
    unit_summary: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if not enabled():
        raise ValueError("openrouter_disabled")

    payload = {
        "model": settings.openrouter_metadata_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Hãy đề xuất metadata cho source SOP CS này để tự động điền form upload. "
                    "Không đoán policy hoặc case reason nếu không có căn cứ trong source. "
                    "Trả JSON shape {\"metadata\":{...},\"signals\":{...}}.\n\n"
                    "metadata bắt buộc gồm: title, audience, vertical, category, tags, case_reasons, owner_team, source, document_type, source_type, review_status, extraction_confidence.\n"
                    "- title viết tiếng Việt theo tài liệu nguồn.\n"
                    "- audience là array lowercase theo đối tượng nghiệp vụ xuất hiện rõ trong source hoặc taxonomy đang dùng; để [] nếu không rõ.\n"
                    "- vertical/category/tags/case_reasons chỉ lấy hoặc suy luận rất sát từ source.\n"
                    "- owner_team để chuỗi rỗng nếu source không có owner rõ ràng.\n"
                    "- review_status luôn là needs_review.\n"
                    "- extraction_confidence là số 0..1 dựa trên độ rõ của source.\n"
                    "- signals ghi evidence ngắn: matched_terms, missing_fields, warnings.\n\n"
                    f"Filename: {filename}\n"
                    f"Detected document_type: {document_type}\n"
                    f"Detected source_type: {source_type}\n"
                    f"Unit summary: {json.dumps(unit_summary[:20], ensure_ascii=False)}\n\n"
                    f"Source text:\n{raw_text[:30000]}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.05,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }

    content = completion_content(payload, headers)
    parsed, repaired = parse_json_with_repair(content, payload, headers)
    if not isinstance(parsed, dict):
        raise ValueError("metadata_suggestion_not_object")
    if isinstance(parsed.get("metadata"), dict):
        metadata = parsed["metadata"]
        signals = parsed.get("signals") if isinstance(parsed.get("signals"), dict) else {}
    else:
        metadata = parsed
        signals = parsed.get("signals") if isinstance(parsed.get("signals"), dict) else {}
    warnings = ["openrouter_metadata_suggestion_used"]
    if repaired:
        warnings.append("openrouter_json_repair_used")
    return normalize_metadata(metadata, filename, document_type, source_type), signals, warnings


def normalize_metadata(metadata: dict[str, Any], filename: str, document_type: str, source_type: str) -> dict[str, Any]:
    def string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def text(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    confidence = metadata.get("extraction_confidence", 0.0)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0

    return {
        "title": text(metadata.get("title")) or Path(filename).stem,
        "audience": string_list(metadata.get("audience")),
        "vertical": text(metadata.get("vertical")),
        "category": text(metadata.get("category")),
        "tags": string_list(metadata.get("tags")),
        "case_reasons": string_list(metadata.get("case_reasons")),
        "owner_team": text(metadata.get("owner_team")),
        "source": text(metadata.get("source")) or "metadata_preview",
        "document_type": text(metadata.get("document_type")) or document_type,
        "source_type": text(metadata.get("source_type")) or source_type,
        "review_status": "needs_review",
        "extraction_confidence": max(0.0, min(confidence_value, 1.0)),
    }


def normalize_unit(unit: dict[str, Any]) -> dict[str, Any]:
    metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
    content = str(unit.get("content") or "").strip()
    unit_type = str(unit.get("unit_type") or "workflow_step")
    raw_title = vietnamese_title(str(unit.get("title") or "").strip())
    title = compact_unit_title(raw_title, content, unit_type)
    confidence = unit.get("confidence", 0.72)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.72
    source_refs = unit.get("source_refs") or metadata.get("source_refs") or []
    source_ref_quality = str(metadata.get("source_ref_quality") or infer_source_ref_quality(source_refs))
    merged_metadata = {
        **metadata,
        "source_refs": source_refs,
        "source_ref_quality": source_ref_quality,
        "production_ready_source_refs": source_ref_quality != "page_only",
    }
    if source_ref_quality == "page_only":
        merged_metadata.setdefault("source_ref_acknowledged", False)
    return {
        "unit_type": unit_type,
        "title": title[:180],
        "content": content,
        "confidence": max(0.0, min(confidence_value, 1.0)),
        "metadata": merged_metadata,
        "source_refs": source_refs,
    }


def compact_unit_title(title: str, content: str, unit_type: str) -> str:
    clean_title = normalize_display_text(title)
    clean_content = normalize_display_text(content)
    if not clean_title:
        return fallback_title_from_content(clean_content, unit_type)
    title_key = normalized_workflow_label(clean_title)
    content_key = normalized_workflow_label(clean_content)
    title_words = title_key.split()
    is_too_long = len(clean_title) > 90 or len(title_words) > 14
    repeats_content = bool(title_key and content_key and (content_key.startswith(title_key) or title_key in content_key[:160]))
    if is_too_long or repeats_content:
        return fallback_title_from_content(clean_content, unit_type)
    return clean_title


def fallback_title_from_content(content: str, unit_type: str) -> str:
    if not content:
        return vietnamese_title(unit_type.replace("_", " "))
    patterns = [
        (r"^(?:Đối với|Doi voi)\s+.+?\s+có quy định\s+(.+?)(?:\s+KH\b|\s+CS\b|\s+cần\b|\s+phải\b|\s+nên\b|[.;]|$)", "Quy định {value}"),
        (r"^(?:Khi|Nếu|Neu|Trong trường hợp|Trong truong hop)\s+(.+?)(?:\s+thì\b|\s+thi\b|[.;]|$)", "{value}"),
        (r"^(?:CS|Agent)\s+(?:cần|phải|nen|can|phai)\s+(.+?)(?:[.;]|$)", "{value}"),
        (r"^(?:Không được|Khong duoc|Không cung cấp|Khong cung cap)\s+(.+?)(?:[.;]|$)", "Không {value}"),
    ]
    for pattern, template in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            value = normalize_display_text(match.group(1))
            value = trim_title_words(value, 10)
            if value:
                return normalize_display_text(template.format(value=value))[:90]
    first_sentence = re.split(r"[.;\n]", content, maxsplit=1)[0]
    return trim_title_words(first_sentence, 10) or vietnamese_title(unit_type.replace("_", " "))


def trim_title_words(value: str, max_words: int) -> str:
    words = normalize_display_text(value).split()
    return " ".join(words[:max_words]).strip(" ,;:.")


def normalize_display_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def infer_source_ref_quality(source_refs: Any) -> str:
    if not isinstance(source_refs, list) or not source_refs:
        return "missing"
    has_pdf = False
    has_bbox = False
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        source_type = str(ref.get("source_type") or "").lower()
        if source_type in {"pdf", "pdf_diagram", "diagram_pdf"}:
            has_pdf = True
            bbox = ref.get("bbox")
            has_bbox = has_bbox or (isinstance(bbox, list) and len(bbox) >= 4)
    if has_pdf and has_bbox:
        return "bbox"
    if has_pdf:
        return "page_only"
    return "structured"


def workflow_payload_to_units(payload: WorkflowExtractionPayload, filename: str) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    full_sop = payload.full_sop.model_dump()
    full_sop["unit_type"] = "full_sop"
    full_sop["metadata"] = {
        **full_sop.get("metadata", {}),
        "retrieval_scope": "document",
        "document_metadata": payload.document_metadata,
        "search_enrichment": payload.search_enrichment,
    }
    units.append(normalize_unit(full_sop))

    graph = payload.workflow_graph.model_dump()
    graph_refs = payload.full_sop.source_refs
    topology_validation_errors = payload.validation_errors
    uncertain_edges = [edge.model_dump() for edge in payload.uncertain_edges]
    annotations = [annotation.model_dump() for annotation in payload.annotations]
    graph["annotations"] = annotations
    graph["uncertain_edges"] = uncertain_edges
    graph["validation_errors"] = topology_validation_errors
    graph_unit = {
        "unit_type": "workflow_graph",
        "title": payload.workflow_graph.title,
        "content": workflow_graph_summary(graph),
        "confidence": payload.workflow_graph.graph_confidence,
        "source_refs": [ref.model_dump() for ref in graph_refs],
        "metadata": {
            "retrieval_scope": "graph",
            "document_metadata": payload.document_metadata,
            "workflow_graph": graph,
            "graph_confidence": payload.workflow_graph.graph_confidence,
            "requires_human_review": payload.workflow_graph.requires_human_review,
            "review_reason": payload.workflow_graph.review_reason,
            "annotations": annotations,
            "uncertain_edges": uncertain_edges,
            "uncertain_edges_count": len(uncertain_edges),
            "graph_validation_errors": topology_validation_errors,
            "graph_validation_error_count": len(topology_validation_errors),
            "source_filename": filename,
            "tags": payload.search_enrichment.get("tags", []),
            "aliases": payload.search_enrichment.get("aliases", []),
        },
    }
    units.append(normalize_unit(graph_unit))

    inherited_refs = [ref.model_dump() for ref in graph_refs]
    for annotation in payload.annotations:
        annotation_data = annotation.model_dump()
        annotation_refs = annotation_data.get("source_refs") or inherited_refs
        units.append(
            normalize_unit(
                {
                    "unit_type": annotation_data.get("type") or "operational_note",
                    "title": annotation_data.get("title") or annotation_data.get("type") or "Lưu ý workflow",
                    "content": annotation_data.get("content") or "",
                    "confidence": 0.72,
                    "source_refs": annotation_refs,
                    "metadata": {
                        "retrieval_scope": "annotation",
                        "annotation_id": annotation_data.get("id"),
                        "attached_to": annotation_data.get("attached_to"),
                        "risk_level": annotation_data.get("risk_level"),
                        "source_refs": annotation_refs,
                    },
                }
            )
        )

    for unit in payload.atomic_units:
        units.append(normalize_unit(unit.model_dump()))
    return units


def workflow_graph_summary(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    node_lines = [
        f"- {node.get('id')}: {node.get('title') or node.get('question')} ({node.get('actor', '')}, {node.get('phase', '')})"
        for node in nodes[:40]
        if isinstance(node, dict)
    ]
    edge_lines = [
        f"- {edge.get('from_node')} --{edge.get('condition', '')}--> {edge.get('to_node')}"
        for edge in edges[:60]
        if isinstance(edge, dict)
    ]
    annotation_lines = [
        f"- {annotation.get('type')}: {annotation.get('title') or annotation.get('content', '')[:80]} -> {annotation.get('attached_to', '')}"
        for annotation in graph.get("annotations", [])[:40]
        if isinstance(annotation, dict)
    ] if isinstance(graph.get("annotations"), list) else []
    return "\n".join(
        [
            f"Workflow graph: {graph.get('title', '')}",
            f"Graph confidence: {graph.get('graph_confidence', 0)}",
            f"Requires human review: {graph.get('requires_human_review', True)}",
            f"Review reason: {graph.get('review_reason', '')}",
            "",
            "Nodes:",
            *node_lines,
            "",
            "Edges:",
            *edge_lines,
            "",
            "Annotations:",
            *annotation_lines,
        ]
    ).strip()


def source_ref_validation_errors(units: list[dict[str, Any]], filename: str) -> list[str]:
    lower_name = filename.lower()
    errors: list[str] = []
    for index, unit in enumerate(units):
        refs = unit.get("source_refs") or unit.get("metadata", {}).get("source_refs") or []
        if not refs:
            errors.append(f"source_refs_missing:unit_{index}:{unit.get('unit_type', 'unknown')}")
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                errors.append(f"source_ref_invalid:unit_{index}")
                continue
            if lower_name.endswith((".xlsx", ".xlsm", ".xls")) and not ref.get("sheet"):
                errors.append(f"source_ref_missing_sheet:unit_{index}")
            if lower_name.endswith(".pdf") and not ref.get("page"):
                errors.append(f"source_ref_missing_page:unit_{index}")
            if lower_name.endswith(".docx") and ref.get("paragraph_index") is None and not ref.get("heading_path"):
                errors.append(f"source_ref_missing_docx_anchor:unit_{index}")
    return errors[:10]


def validation_summary(exc: ValidationError) -> str:
    return ";".join(
        f"{'.'.join(str(part) for part in error.get('loc', []))}:{error.get('msg', 'invalid')}"
        for error in exc.errors()[:8]
    )


def vietnamese_title(title: str) -> str:
    normalized = title.lower().strip()
    translations = {
        "": "Đơn vị trích xuất cần review",
        "curated content": "Nội dung đã chuẩn hóa",
        "extracted workflow unit": "Đơn vị workflow được trích xuất",
        "workflow overview": "Tổng quan quy trình",
        "initial verification script": "Script xác minh ban đầu",
        "confirmation script": "Script xác nhận",
        "operational note": "Lưu ý vận hành",
        "security note": "Lưu ý bảo mật",
        "related document": "Tài liệu liên quan",
    }
    return translations.get(normalized, title or "Đơn vị trích xuất cần review")
