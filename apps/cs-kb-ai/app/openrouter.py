from __future__ import annotations

from contextvars import ContextVar, Token
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import settings
from app.vietnamese_defaults import DEFAULT_KB_COLLECTIONS
from app.search_labels import meaningful_search_label
from app.schemas import (
    ExtractionRefinementPayload,
    ExtractedUnit,
    ExtractedUnitsPayload,
    GroundedAnswerPayload,
    RetrievalResponse,
    SourceRef,
    WorkflowExtractionPayload,
)
from app.workflow_v3 import (
    compile_workflow_v3_payload,
    workflow_v3_quality_error_from_report,
)


MAX_AI_BREAKDOWN_PROMPT_CHARS = 24000
MAX_AI_BREAKDOWN_RESPONSE_CHARS = 60000
MAX_AI_BREAKDOWN_JSON_CHARS = 60000
COLLECTION_HINTS = {slug: (name, collection_type) for slug, name, collection_type in DEFAULT_KB_COLLECTIONS}

_AI_BREAKDOWN_BUFFER: ContextVar[list[dict[str, Any]] | None] = ContextVar("ai_breakdown_buffer", default=None)


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
- source_refs theo loại file: Excel dùng {source_type:"excel", source_file, sheet, row_start, row_end, column_names}; PDF dùng {source_type:"pdf", source_file, page, bbox nếu có}; DOCX prose dùng {source_type:"docx", source_file, paragraph_index hoặc heading_path}; DOCX table dùng {source_type:"docx_table", source_file, table_index, row_index, column_names}; text/markdown dùng {source_type:"text", source_file, line_start, line_end}.
- Không có source_refs thì output bị reject.
"""


WORKFLOW_EXTRACTION_PROMPT = """You are extracting a CS operational SOP from a workflow diagram.

Use the page image as the source of truth.
Use OCR text and visual candidates only as hints.
Do not infer workflow order from OCR text order.
Do not create business logic not visible in the source.

Return structured JSON with:
- document_metadata
- full_sop
- workflow_graph
- atomic_units
- annotations
- warnings
- uncertain_edges
- source_refs
- search_enrichment

Required JSON object shape:
{"document_metadata":{},"full_sop":{},"workflow_graph":{},"annotations":[],"uncertain_edges":[],"validation_errors":[],"atomic_units":[],"warnings":[],"source_refs":[],"search_enrichment":{}}.

Rules:
1. Preserve swimlanes/actors.
2. Preserve phases if visible.
3. Decision nodes must have a question string.
4. Edges must come from visible arrows/connectors.
5. If an edge is uncertain, put it in uncertain_edges with reason and confidence.
6. Notes such as Lưu ý, Quy định audit, SLA, script blocks must be annotations or warning units, not workflow steps.
7. Every node/unit must include source_refs with page and bbox if available.
8. Do not auto-confirm uncertain Yes/No branches.
9. Do not output raw OCR fragments as standalone units.
10. If you cannot determine topology, return a partial graph and explain missing/uncertain areas in validation_errors, warnings, review_reason, and uncertain_edges.

Architecture/schema mapping:
- The output must validate as WorkflowExtractionPayload.
- full_sop is an ExtractedUnit with unit_type="full_sop", title, content, confidence, metadata, source_refs.
- workflow_graph must include workflow_id, title, start_node_id, lanes, nodes, edges, annotations, uncertain_edges, graph_confidence, requires_human_review=true, review_reason, source_refs.
- workflow_graph.nodes must include id, type start/action/decision/end, title, content, question for decisions, actor/lane if visible, phase if visible, source_refs.
- workflow_graph.edges must use from_node, to_node, condition. Do not use keys named from/to/source/target in final output.
- uncertain_edges must use from_node, to_node, condition, reason, confidence, source_refs.
- annotations must include id, type annotation/warning/sla_rule/audit_rule/macro_script/operational_note, attached_to if known, title, content, source_refs.
- atomic_units should be search/review units grounded in visible diagram content: workflow_step, decision_point, sla_rule, routing_rule, handoff_rule, macro_script, operational_note, warning.
- source_refs for PDF must use source_type="pdf_diagram", source_file, page, bbox if available; use bbox=[] only when unavailable.
"""


RULE_TABLE_EXTRACTION_PROMPT = """You are extracting a CS policy rule table.

Use table rows/cells as the source of truth.
Do not split examples into standalone rules.
Do not create rules not present in the table.

For each logical table row, create one operational unit:
- policy_rule
- exception_rule
- warning
- operational_note

Attach:
- examples
- notes
- thresholds
- service
- case type
- source row/cell refs

Return JSON:
{
  "full_sop": {},
  "units": [],
  "warnings": [],
  "metadata_suggestions": {},
  "coverage_report": {}
}

Rules:
1. One table row should become one main unit unless it contains multiple explicit sub-rules.
2. Examples belong to the nearest parent rule.
3. "Không áp dụng" should become exception_rule.
4. Preserve all numeric thresholds exactly.
5. Every unit must cite source table row/cell.
6. Do not infer policy beyond the source.

Architecture/schema mapping:
- full_sop and every item in units must be ExtractedUnit objects: unit_type, title, content, confidence, metadata, source_refs.
- The parser will merge full_sop into units for the existing pipeline contract.
- Excel source_refs need source_type="excel", source_file, sheet, row_start, row_end, column_names when available.
- DOCX table source_refs need source_type="docx_table", source_file, table_index, row_index, column_names when available.
- PDF/table text source_refs need source_type="pdf" or "pdf_diagram", source_file, page, bbox when available.
- Put examples, thresholds, service, case_type, original columns/cells, tags, aliases into metadata when grounded.
- Use metadata.examples as structured input/output examples when the row contains examples.
- If rows are historical/archived versions, put that in metadata or warnings; do not create active rules unless the source says they are active.
"""


MIXED_DOCX_POLICY_EXTRACTION_PROMPT = """You are extracting a mixed DOCX communication guideline for CS SOP ingestion.

Use the structured DOCX blocks as source of truth. Each block has block_id, block_type, text, section_path, paragraph_index, table_index, row_index, cells, style, numbering, and source_ref.
Preserve the section_path on every extracted unit. Preserve DOCX table rows as rows/cells, not flattened prose.

Return JSON:
{
  "full_sop": {},
  "units": [],
  "warnings": [],
  "metadata_suggestions": {},
  "coverage_report": {}
}

Allowed unit intent for this flow:
- full_sop
- macro_table
- macro_script
- wording_rule
- handling_rule
- warning
- compliance_rule
- operational_note
- example

Rules:
1. Use section_path to attach units under the correct Roman section and numbered/text subsection.
2. For macro tables, create one macro_table unit with metadata.rows/cells and one macro_script per row when useful.
3. DOCX table units must cite {source_type:"docx_table", source_file, table_index, row_index, column_names}.
4. Paragraph/list units must cite {source_type:"docx", source_file, paragraph_index, heading_path}.
5. Do not set affected audience to Customer Service. Use actor="CS"; affected_audience is driver/customer when TX/KH appear.
6. Infer channel as email/call/chat only when present in section_path or block text.
7. If text contains "TUYỆT ĐỐI KHÔNG", "không chủ động cung cấp", "quy trình xử lý nội bộ", "chế tài", or "chấm lỗi", create warning/compliance_rule and set risk_level high or critical plus risk_category.
"""


def start_ai_breakdown_capture() -> Token[list[dict[str, Any]] | None]:
    return _AI_BREAKDOWN_BUFFER.set([])


def finish_ai_breakdown_capture(token: Token[list[dict[str, Any]] | None]) -> list[dict[str, Any]]:
    breakdowns = _AI_BREAKDOWN_BUFFER.get() or []
    _AI_BREAKDOWN_BUFFER.reset(token)
    return breakdowns


def record_ai_breakdown(entry: dict[str, Any]) -> None:
    buffer = _AI_BREAKDOWN_BUFFER.get()
    if buffer is None:
        return
    buffer.append(entry)


def truncated_text(value: str, limit: int) -> tuple[str, bool, int]:
    text = str(value or "")
    return text[:limit], len(text) > limit, len(text)


def json_preview(value: Any, limit: int = MAX_AI_BREAKDOWN_JSON_CHARS) -> dict[str, Any]:
    try:
        text = json.dumps(value, ensure_ascii=False, default=lambda item: item.model_dump() if hasattr(item, "model_dump") else str(item))
    except TypeError:
        text = str(value)
    preview, truncated, chars = truncated_text(text, limit)
    return {"chars": chars, "json": preview, "truncated": truncated}


def ai_prompt_preview(prompt: str) -> dict[str, Any]:
    preview, truncated, chars = truncated_text(prompt, MAX_AI_BREAKDOWN_PROMPT_CHARS)
    return {"chars": chars, "text": preview, "truncated": truncated}


def ai_response_preview(content: str) -> dict[str, Any]:
    preview, truncated, chars = truncated_text(content, MAX_AI_BREAKDOWN_RESPONSE_CHARS)
    return {"chars": chars, "text": preview, "truncated": truncated}


def base_ai_breakdown(
    *,
    filename: str,
    flow: str,
    model: str,
    prompt: str,
    raw_text: str,
    temperature: float,
    visual_context: dict[str, Any] | None = None,
    page_images: list[str] | None = None,
) -> dict[str, Any]:
    visual_context_json = json.dumps(visual_context or {}, ensure_ascii=False)
    return {
        "filename": filename,
        "flow": flow,
        "model": model,
        "prompt": ai_prompt_preview(prompt),
        "raw_text_chars": len(raw_text or ""),
        "response_format": "json_schema_strict" if settings.openrouter_strict_json_schema else "json_object",
        "temperature": temperature,
        "visual_context_chars": len(visual_context_json),
        "image_count": len(page_images or []),
        "images_supplied": bool(page_images),
    }


def response_format_for_schema(name: str, schema_model: Any | None = None) -> dict[str, Any]:
    if settings.openrouter_strict_json_schema and schema_model is not None:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": schema_model.model_json_schema(),
            },
        }
    return {"type": "json_object"}


def synthetic_missing_source_ref(source_type: str = "pdf_diagram") -> dict[str, Any]:
    return {
        "source_type": source_type,
        "source_file": "",
        "page": 1 if source_type in {"pdf", "pdf_diagram"} else None,
        "bbox": [] if source_type in {"pdf", "pdf_diagram"} else [],
        "source_ref_synthetic": True,
        "source_ref_quality": "synthetic_missing",
    }


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
        record_ai_breakdown({"filename": filename, "flow": "workflow_legacy", "status": "skipped", "skip_reason": "openrouter_disabled"})
        return [], ["openrouter_disabled"]

    extraction_prompt = (
        WORKFLOW_EXTRACTION_PROMPT
        + "\n\nPipeline-specific notes for the existing extraction architecture:\n"
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
        "- Nếu có semantic_refinement.workflow_graph_candidate, dùng nó làm semantic draft chính: giữ semantic_node_type, lanes, annotations, uncertain_edges và source_refs.bbox.\n"
        "- Không biến semantic annotations/warnings/audit/macro_script thành workflow_graph.nodes. Chúng phải nằm trong annotations/warnings và attached_to node liên quan.\n"
        "- Node decision phải luôn có question là string; action/start/end phải luôn có content là string. Không trả null cho title/content/question.\n"
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
        "response_format": response_format_for_schema("workflow_extraction_payload", WorkflowExtractionPayload),
        "temperature": 0.1,
    }
    breakdown = base_ai_breakdown(
        filename=filename,
        flow="workflow_legacy",
        model=str(payload["model"]),
        page_images=page_images,
        prompt=extraction_prompt,
        raw_text=raw_text,
        temperature=0.1,
        visual_context=visual_context,
    )
    content = ""
    parsed: Any = None
    normalized: list[dict[str, Any]] = []
    output_warnings: list[str] = []
    status = "failed"
    error = ""
    repaired = False
    schema_repaired = False
    topology_repaired = False
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
            output_warnings = missing_refs
            error = ",".join(missing_refs)
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
        output_warnings = warnings
        status = "completed"
        return [unit for unit in normalized if unit["content"]], warnings
    except json.JSONDecodeError as exc:
        error = f"openrouter_workflow_invalid_json:{exc.msg}:{exc.pos}"
        output_warnings = [error]
        return [], output_warnings
    except ValidationError as exc:
        error = f"openrouter_workflow_validation_failed:{validation_summary(exc)}"
        output_warnings = [error]
        return [], output_warnings
    except Exception as exc:
        error = f"openrouter_extraction_failed:{exc.__class__.__name__}"
        output_warnings = [error]
        return [], output_warnings
    finally:
        record_ai_breakdown(
            {
                **breakdown,
                "error": error,
                "normalized_unit_count": len(normalized),
                "normalized_unit_types": sorted({str(unit.get("unit_type") or "") for unit in normalized if isinstance(unit, dict)}),
                "parsed_response": json_preview(parsed) if parsed is not None else None,
                "raw_response": ai_response_preview(content),
                "repairs": {
                    "json_repair_used": repaired,
                    "schema_repair_used": schema_repaired,
                    "topology_repair_used": topology_repaired,
                },
                "status": status,
                "warnings": output_warnings[:40],
            }
        )


def extract_workflow_units_v2(
    filename: str,
    raw_text: str,
    page_images: list[str] | None = None,
    visual_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled():
        record_ai_breakdown({"filename": filename, "flow": "workflow_v2_vision_primary", "status": "skipped", "skip_reason": "openrouter_disabled"})
        return [], ["openrouter_disabled"]
    if not page_images:
        record_ai_breakdown({"filename": filename, "flow": "workflow_v2_vision_primary", "status": "skipped", "skip_reason": "workflow_v2_vision_images_required"})
        return [], ["workflow_v2_vision_images_required"]

    extraction_prompt = (
        WORKFLOW_EXTRACTION_PROMPT
        + "\n\nWorkflow extraction v2 notes:\n"
        "Bạn đang chạy WORKFLOW_EXTRACTION_V2 cho tài liệu workflow diagram/swimlane SOP CS.\n"
        "SOURCE OF TRUTH là ẢNH PDF được gửi kèm. Hãy đọc diagram như reviewer con người: lane, node, mũi tên, nhãn Yes/No, ghi chú, SLA, audit.\n"
        "OCR/raw text/layout detector chỉ là evidence phụ để tham chiếu chữ và source refs; nếu OCR/layout mâu thuẫn với ảnh thì TIN ẢNH.\n\n"
        "Trả CHỈ JSON object đúng shape:\n"
        "{\"document_metadata\":{},\"full_sop\":{},\"workflow_graph\":{},\"annotations\":[],\"uncertain_edges\":[],\"validation_errors\":[],\"atomic_units\":[],\"warnings\":[],\"search_enrichment\":{}}.\n\n"
        "QUY TẮC V2:\n"
        "- workflow_graph.nodes phải là các node nghiệp vụ chính nhìn thấy trong diagram. Giữ full content của node trong field content; title chỉ là label ngắn.\n"
        "- Decision node phải type=\"decision\" và có question string rõ ràng.\n"
        "- Action/SLA/routing/handoff node phải có content string đầy đủ, không cắt cụt dòng.\n"
        "- Notes như (a), (b), Lưu ý, Quy định audit, ZT, script/reference phải đưa vào annotations hoặc warnings, không đưa vào nodes.\n"
        "- Edge chỉ tạo khi thấy mũi tên/connector/nhãn branch trong ẢNH. Không suy edge từ thứ tự OCR.\n"
        "- Nếu thấy quan hệ nhưng không chắc hướng/nhánh, đưa vào uncertain_edges với reason/confidence; không bỏ mất edge nghi vấn.\n"
        "- Không tạo graph tối thiểu một node nếu ảnh có workflow thật. Phải trích xuất graph thực tế từ ảnh.\n"
        "- Nếu không chắc một số nhánh, vẫn trả workflow_graph reviewable với requires_human_review=true và graph_confidence thấp.\n"
        "- full_sop bắt buộc có. Nếu source không có prose tổng quan, tự tóm tắt từ workflow_graph đã đọc từ ảnh và đánh requires_human_review=true.\n"
        "- atomic_units bắt buộc có ít nhất các unit search/review được từ node chính. Chỉ dùng unit_type hợp lệ: workflow_step, decision_point, sla_rule, routing_rule, handoff_rule, operational_note, macro_script, warning.\n"
        "- source_refs cho PDF dùng source_type=\"pdf_diagram\", source_file, page, bbox nếu biết; bbox có thể [] nếu không chắc.\n\n"
        "FIELD GỢI Ý:\n"
        "document_metadata: title, effective_from, document_type=\"workflow_diagram\", sub_type=\"vision_primary_workflow\", actors, audience, risk_level, extraction_strategy=\"workflow_v2_vision_primary\".\n"
        "workflow_graph: workflow_id, title, start_node_id, lanes, nodes, edges, annotations, uncertain_edges, graph_confidence, requires_human_review=true, review_reason.\n"
        "search_enrichment: tags, aliases, actors, systems, case_reasons nếu có căn cứ trong ảnh/source.\n\n"
        f"Filename: {filename}\n\n"
        f"Auxiliary OCR text, not topology source:\n{raw_text[:16000]}\n\n"
        f"Auxiliary detector context, not source of truth:\n{json.dumps(visual_context or {}, ensure_ascii=False)[:8000]}"
    )
    user_content: list[dict[str, Any]] = [{"type": "text", "text": extraction_prompt}]
    user_content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in page_images[:3])

    payload = {
        "model": settings.openrouter_vision_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": response_format_for_schema("workflow_extraction_payload", WorkflowExtractionPayload),
        "temperature": 0.05,
    }
    breakdown = base_ai_breakdown(
        filename=filename,
        flow="workflow_v2_vision_primary",
        model=str(payload["model"]),
        page_images=page_images,
        prompt=extraction_prompt,
        raw_text=raw_text,
        temperature=0.05,
        visual_context=visual_context,
    )
    content = ""
    parsed: Any = None
    normalized: list[dict[str, Any]] = []
    output_warnings: list[str] = []
    status = "failed"
    error = ""
    repaired = False
    schema_repaired = False
    topology_repaired = False
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
        if "workflow_graph_missing_from_model_synthesized_for_review" in payload_model.warnings:
            output_warnings = ["workflow_v2_missing_workflow_graph", *payload_model.warnings]
            error = "workflow_v2_missing_workflow_graph"
            return [], output_warnings
        payload_model = ensure_workflow_v2_review_layers(payload_model, filename)
        payload_model, topology_repaired, topology_errors = validate_workflow_topology_with_repair(payload_model, payload, headers)
        payload_model = ensure_workflow_v2_review_layers(payload_model, filename)
        if topology_errors:
            payload_model.validation_errors = list(dict.fromkeys([*payload_model.validation_errors, *topology_errors]))
            payload_model.warnings = [
                *payload_model.warnings,
                "workflow_topology_requires_manual_review",
                *[f"workflow_topology_error:{error}" for error in topology_errors[:8]],
            ]
            payload_model.workflow_graph.requires_human_review = True
            if not payload_model.workflow_graph.review_reason:
                payload_model.workflow_graph.review_reason = "Vision-primary workflow graph has topology warnings and must be reviewed before publish."
        normalized = workflow_payload_to_units(payload_model, filename)
        missing_refs = source_ref_validation_errors(normalized, filename)
        if missing_refs:
            output_warnings = missing_refs
            error = ",".join(missing_refs)
            return [], missing_refs
        warnings = ["openrouter_workflow_v2_extraction_used", "workflow_v2_vision_primary", *workflow_v2_visible_warnings(payload_model.warnings)]
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
        output_warnings = warnings
        status = "completed"
        return [unit for unit in normalized if unit["content"]], warnings
    except json.JSONDecodeError as exc:
        error = f"openrouter_workflow_v2_invalid_json:{exc.msg}:{exc.pos}"
        output_warnings = [error]
        return [], output_warnings
    except ValidationError as exc:
        error = f"openrouter_workflow_v2_validation_failed:{validation_summary(exc)}"
        output_warnings = [error]
        return [], output_warnings
    except Exception as exc:
        error = f"openrouter_workflow_v2_failed:{exc.__class__.__name__}"
        output_warnings = [error]
        return [], output_warnings
    finally:
        record_ai_breakdown(
            {
                **breakdown,
                "error": error,
                "normalized_unit_count": len(normalized),
                "normalized_unit_types": sorted({str(unit.get("unit_type") or "") for unit in normalized if isinstance(unit, dict)}),
                "parsed_response": json_preview(parsed) if parsed is not None else None,
                "raw_response": ai_response_preview(content),
                "repairs": {
                    "json_repair_used": repaired,
                    "schema_repair_used": schema_repaired,
                    "topology_repair_used": topology_repaired,
                },
                "status": status,
                "warnings": output_warnings[:40],
            }
        )


def workflow_v2_visible_warnings(warnings: list[str]) -> list[str]:
    output = []
    for warning in warnings:
        if warning == "full_sop_missing_from_model_synthesized_for_review":
            output.append("full_sop_synthesized_from_workflow_graph_for_review")
            continue
        output.append(warning)
    return list(dict.fromkeys(output))


def ensure_workflow_v2_review_layers(payload: WorkflowExtractionPayload, filename: str) -> WorkflowExtractionPayload:
    if not payload.workflow_graph.source_refs:
        payload.workflow_graph.source_refs = [default_pdf_diagram_source_ref(filename)]
    for node in payload.workflow_graph.nodes:
        if not node.source_refs:
            node.source_refs = payload.workflow_graph.source_refs or [default_pdf_diagram_source_ref(filename)]
    if "full_sop_missing_from_model_synthesized_for_review" in payload.warnings:
        payload.full_sop.source_refs = payload.full_sop.source_refs or payload.workflow_graph.source_refs or [default_pdf_diagram_ref(filename)]
        payload.full_sop.metadata = {
            **payload.full_sop.metadata,
            "retrieval_scope": "document",
            "synthesized_from_workflow_graph": True,
            "requires_human_review": True,
        }
    if not payload.atomic_units:
        payload.atomic_units = workflow_atomic_units_from_graph(payload, filename)
        if payload.atomic_units:
            payload.warnings = [*payload.warnings, "workflow_v2_atomic_units_synthesized_from_graph"]
    return payload


def workflow_atomic_units_from_graph(payload: WorkflowExtractionPayload, filename: str) -> list[ExtractedUnit]:
    units: list[ExtractedUnit] = []
    for node in payload.workflow_graph.nodes:
        node_type = normalized_workflow_label(node.type)
        semantic_type = normalized_workflow_label(node.semantic_node_type)
        if is_start_node(node_type, normalized_workflow_label(node.title)) or is_end_node(node_type, normalized_workflow_label(node.title)):
            continue
        content = (node.question or node.content or node.title).strip()
        if not content:
            continue
        unit_type = workflow_atomic_unit_type(node_type, semantic_type, content)
        refs = dump_source_refs(node.source_refs or payload.workflow_graph.source_refs) or [default_pdf_diagram_ref(filename)]
        units.append(
            ExtractedUnit.model_validate(
                {
                    "unit_type": unit_type,
                    "title": node.title or node.question or unit_type,
                    "content": content,
                    "confidence": min(float(payload.workflow_graph.graph_confidence or 0.65), 0.82),
                    "metadata": {
                        "retrieval_scope": "unit",
                        "workflow_node_id": node.id,
                        "actor": node.actor,
                        "phase": node.phase,
                        "semantic_node_type": node.semantic_node_type,
                        "source_refs": refs,
                    },
                    "source_refs": refs,
                }
            )
        )
    return units[:80]


def extract_workflow_units_v3(
    filename: str,
    raw_text: str,
    page_images: list[str] | None = None,
    visual_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    if not enabled():
        record_ai_breakdown({"filename": filename, "flow": "workflow_v3_graph_primary", "status": "skipped", "skip_reason": "openrouter_disabled"})
        return [], ["openrouter_disabled"], {}
    if not page_images:
        record_ai_breakdown({"filename": filename, "flow": "workflow_v3_graph_primary", "status": "skipped", "skip_reason": "workflow_v3_vision_images_required"})
        return [], ["workflow_v3_vision_images_required"], {}

    extraction_prompt = (
        "You are extracting a CS operational workflow diagram as graph evidence.\n"
        "Use the attached page image as source of truth. OCR text and detector JSON are hints only.\n\n"
        "DO NOT summarize the workflow as prose. First transcribe the canvas into visible nodes, arrows, notes, lanes, and references.\n"
        "Preserve every numbered visible step. Preserve every decision diamond/question. Preserve every Yes/No branch explicitly.\n"
        "Do not demote decision branches into notes. Notes such as (*), (**), Lưu ý, references, SLA, audit, and script blocks must be annotations, not workflow actions.\n"
        "Every edge must come from a visible arrow/connector/branch label. If direction or endpoint is uncertain, mark that edge uncertain and include reason.\n"
        "This must work for arbitrary workflow diagram layouts, not only one sample: use visible step codes, shape/arrow evidence, labels, and bboxes rather than template assumptions.\n\n"
        "Return ONLY JSON object with this shape:\n"
        "{\n"
        "  \"document_metadata\": {\"title\":\"\", \"effective_from\":\"\", \"actors\":[], \"audience\":[], \"risk_level\":\"high\"},\n"
        "  \"canvas\": {\n"
        "    \"pages\": [\n"
        "      {\n"
        "        \"page\": 1,\n"
        "        \"image_size\": [],\n"
        "        \"lanes\": [{\"id\":\"\", \"title\":\"\", \"bbox\":[]}],\n"
        "        \"nodes\": [{\"id\":\"\", \"step_code\":\"\", \"text\":\"\", \"node_type\":\"start|action|decision|end|annotation\", \"shape_kind\":\"oval|rectangle|diamond|note|other\", \"lane\":\"\", \"bbox\":[], \"terminal_state\":\"\"}],\n"
        "        \"edges\": [{\"from_step_code\":\"\", \"to_step_code\":\"\", \"from_node\":\"\", \"to_node\":\"\", \"condition\":\"yes|no|next|timeout|escalation|fallback|handoff|return|retry\", \"confidence\":0.0, \"uncertain\":false, \"reason\":\"\", \"bbox\":[]}],\n"
        "        \"annotations\": [{\"id\":\"\", \"text\":\"\", \"annotation_type\":\"annotation|warning|sla_rule|audit_rule|macro_script\", \"attached_to_step_codes\":[], \"bbox\":[]}],\n"
        "        \"relations\": [{\"target_title\":\"\", \"target_url\":\"\", \"relation_type\":\"requires|references|related_to\", \"evidence_text\":\"\", \"bbox\":[]}],\n"
        "        \"warnings\": []\n"
        "      }\n"
        "    ]\n"
        "  },\n"
        "  \"warnings\": []\n"
        "}.\n\n"
        "Field rules:\n"
        "- For numbered nodes, set step_code exactly as visible, for example 1, 1.1, 6, 9.2, 10.2.\n"
        "- Decision node text must be the full question visible in the shape, not a shortened label.\n"
        "- Action node text must keep full operational wording visible in the node.\n"
        "- If a note references another SOP/file, include it both as annotation and as relation.\n"
        "- If arrows are visually long/curved, still capture them if endpoints are clear; otherwise uncertain=true.\n\n"
        f"Filename: {filename}\n\n"
        f"Auxiliary OCR text, not topology source:\n{raw_text[:16000]}\n\n"
        f"Auxiliary detector context, not source of truth:\n{json.dumps(visual_context or {}, ensure_ascii=False)[:12000]}"
    )
    user_content: list[dict[str, Any]] = [{"type": "text", "text": extraction_prompt}]
    user_content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in page_images[:3])
    payload = {
        "model": settings.openrouter_vision_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": response_format_for_schema("workflow_extraction_payload", WorkflowExtractionPayload),
        "temperature": 0.02,
    }
    breakdown = base_ai_breakdown(
        filename=filename,
        flow="workflow_v3_graph_primary",
        model=str(payload["model"]),
        page_images=page_images,
        prompt=extraction_prompt,
        raw_text=raw_text,
        temperature=0.02,
        visual_context=visual_context,
    )
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }
    content = ""
    parsed: Any = None
    normalized: list[dict[str, Any]] = []
    output_warnings: list[str] = []
    status = "failed"
    error = ""
    repaired = False
    artifacts: dict[str, Any] = {}
    try:
        content = completion_content(payload, headers)
        parsed, repaired = parse_json_with_repair(content, payload, headers)
        if not isinstance(parsed, dict):
            error = "workflow_v3_transcription_not_object"
            output_warnings = [error]
            return [], output_warnings, {}
        payload_model, fidelity_report, canvas = compile_workflow_v3_payload(
            filename=filename,
            raw_text=raw_text,
            transcription=parsed,
            visual_context=visual_context,
        )
        artifacts = {
            "workflow_canvas_transcription": canvas,
            "workflow_graph_draft": payload_model.workflow_graph.model_dump() if payload_model else {},
            "workflow_fidelity_report": fidelity_report,
            "workflow_graph_repair_report": (
                payload_model.workflow_graph.repair_report
                if payload_model and isinstance(payload_model.workflow_graph.repair_report, dict)
                else {}
            ),
        }
        quality_error = workflow_v3_quality_error_from_report(fidelity_report)
        if payload_model is None:
            error = quality_error or "workflow_v3_payload_compile_failed"
            output_warnings = [error, *fidelity_report.get("warnings", [])]
            return [], output_warnings, artifacts
        normalized = workflow_payload_to_units(payload_model, filename)
        missing_refs = source_ref_validation_errors(normalized, filename)
        if missing_refs:
            error = ",".join(missing_refs)
            output_warnings = missing_refs
            return [], output_warnings, artifacts
        warnings = [
            "openrouter_workflow_v3_extraction_used",
            "workflow_v3_graph_primary",
            *[f"workflow_v3_fidelity_blocker:{blocker}" for blocker in fidelity_report.get("blockers", [])[:8]],
            *fidelity_report.get("warnings", [])[:8],
        ]
        if repaired:
            warnings.append("openrouter_json_repair_used")
        if quality_error:
            error = f"workflow_v3_fidelity_failed:{quality_error}"
            output_warnings = warnings
            return [unit for unit in normalized if unit["content"]], output_warnings, artifacts
        output_warnings = warnings
        status = "completed"
        return [unit for unit in normalized if unit["content"]], warnings, artifacts
    except json.JSONDecodeError as exc:
        error = f"openrouter_workflow_v3_invalid_json:{exc.msg}:{exc.pos}"
        output_warnings = [error]
        return [], output_warnings, artifacts
    except Exception as exc:
        error = f"openrouter_workflow_v3_failed:{exc.__class__.__name__}"
        output_warnings = [error]
        return [], output_warnings, artifacts
    finally:
        record_ai_breakdown(
            {
                **breakdown,
                "error": error,
                "normalized_unit_count": len(normalized),
                "normalized_unit_types": sorted({str(unit.get("unit_type") or "") for unit in normalized if isinstance(unit, dict)}),
                "parsed_response": json_preview(parsed) if parsed is not None else None,
                "raw_response": ai_response_preview(content),
                "workflow_fidelity_report": artifacts.get("workflow_fidelity_report"),
                "workflow_graph_repair_report": artifacts.get("workflow_graph_repair_report"),
                "repairs": {"json_repair_used": repaired},
                "status": status,
                "warnings": output_warnings[:40],
            }
        )


def dump_source_refs(refs: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for ref in refs:
        if hasattr(ref, "model_dump"):
            output.append(ref.model_dump())
        elif isinstance(ref, dict):
            output.append(ref)
    return output


def workflow_atomic_unit_type(node_type: str, semantic_type: str, content: str) -> str:
    normalized = normalized_workflow_label(content)
    if "decision" in node_type or "?" in normalized:
        return "decision_point"
    if "sla" in semantic_type or "tre nhat" in normalized or re.search(r"\b\d+\s*(phut|gio)\b", normalized):
        return "sla_rule"
    if "queue" in semantic_type or "queue" in normalized or "all staff" in normalized or "food order issue" in normalized:
        return "routing_rule"
    if "handoff" in semantic_type or "chuyen case" in normalized or "chia case" in normalized:
        return "handoff_rule"
    return "workflow_step"


def default_pdf_diagram_ref(filename: str) -> dict[str, Any]:
    return {"source_type": "pdf_diagram", "source_file": filename, "page": 1, "bbox": []}


def default_pdf_diagram_source_ref(filename: str) -> SourceRef:
    return SourceRef.model_validate(default_pdf_diagram_ref(filename))


def normalize_rule_table_response_payload(parsed: Any) -> tuple[Any, list[str]]:
    if not isinstance(parsed, dict):
        return parsed, []

    warnings = [str(warning) for warning in parsed.get("warnings", []) if warning]
    raw_units = parsed.get("units") if isinstance(parsed.get("units"), list) else []
    units = [unit for unit in raw_units if isinstance(unit, dict)]

    full_sop = parsed.get("full_sop") if isinstance(parsed.get("full_sop"), dict) else None
    if full_sop:
        metadata = full_sop.get("metadata") if isinstance(full_sop.get("metadata"), dict) else {}
        if isinstance(parsed.get("metadata_suggestions"), dict):
            metadata = {**metadata, "metadata_suggestions": parsed["metadata_suggestions"]}
        if isinstance(parsed.get("coverage_report"), dict):
            metadata = {**metadata, "coverage_report": parsed["coverage_report"]}
        full_sop = {
            **full_sop,
            "unit_type": "full_sop",
            "metadata": {**metadata, "retrieval_scope": "document"},
        }
        has_full_sop = any(str(unit.get("unit_type") or "").strip() == "full_sop" for unit in units)
        if not has_full_sop:
            units.insert(0, full_sop)

    if units:
        return {"units": units}, warnings
    return parsed, warnings


def repair_spreadsheet_source_refs_from_raw_text(
    units: list[dict[str, Any]],
    filename: str,
    raw_text: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return units, []
    line_to_sheet = raw_text_line_to_sheet(raw_text)
    if not line_to_sheet:
        return units, []

    repaired_count = 0
    repaired_units: list[dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, dict):
            repaired_units.append(unit)
            continue
        unit_copy = dict(unit)
        metadata = unit_copy.get("metadata") if isinstance(unit_copy.get("metadata"), dict) else {}
        refs = unit_copy.get("source_refs") or metadata.get("source_refs") or []
        repaired_refs: list[Any] = []
        unit_repaired = False
        for ref in refs:
            if not isinstance(ref, dict):
                repaired_refs.append(ref)
                continue
            ref_copy = dict(ref)
            if not ref_copy.get("sheet"):
                line_start = int_or_none(ref_copy.get("line_start"))
                line_end = int_or_none(ref_copy.get("line_end")) or line_start
                sheet = sheet_for_line(line_to_sheet, line_start)
                if sheet:
                    ref_copy["source_type"] = "excel"
                    ref_copy["source_file"] = ref_copy.get("source_file") or filename
                    ref_copy["sheet"] = sheet
                    if line_start and not ref_copy.get("line_start"):
                        ref_copy["line_start"] = line_start
                    if line_end and not ref_copy.get("line_end"):
                        ref_copy["line_end"] = line_end
                    repaired_count += 1
                    unit_repaired = True
            repaired_refs.append(ref_copy)

        if repaired_refs:
            unit_copy["source_refs"] = repaired_refs
            unit_copy["metadata"] = {
                **metadata,
                "source_refs": repaired_refs,
                **({"source_ref_repaired_from": "raw_text_line_sheet_context"} if unit_repaired else {}),
            }
        repaired_units.append(unit_copy)

    warnings = [f"source_refs_repaired_from_text_lines:{repaired_count}"] if repaired_count else []
    return repaired_units, warnings


def raw_text_line_to_sheet(raw_text: str) -> dict[int, str]:
    line_to_sheet: dict[int, str] = {}
    current_sheet = ""
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            current_sheet = match.group(1).strip()
        if current_sheet:
            line_to_sheet[line_number] = current_sheet
    return line_to_sheet


def sheet_for_line(line_to_sheet: dict[int, str], line_number: int | None) -> str:
    if not line_number:
        return ""
    if line_number in line_to_sheet:
        return line_to_sheet[line_number]
    prior_lines = [candidate for candidate in line_to_sheet if candidate <= line_number]
    if not prior_lines:
        return ""
    return line_to_sheet[max(prior_lines)]


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def format_source_evidence_view(
    filename: str,
    raw_text: str,
    document_type: str,
    source_type: str,
) -> tuple[dict[str, Any], list[str], str]:
    if not enabled():
        record_ai_breakdown({"filename": filename, "flow": "source_evidence_view", "status": "skipped", "skip_reason": "openrouter_disabled"})
        return {}, ["openrouter_source_evidence_formatter_disabled"], "openrouter_disabled"
    if not raw_text.strip():
        record_ai_breakdown({"filename": filename, "flow": "source_evidence_view", "status": "skipped", "skip_reason": "raw_text_empty"})
        return {}, ["source_evidence_formatter_empty_raw_text"], "raw_text_empty"

    formatting_prompt = (
        "Bạn đang format lại source evidence để CS đọc SOP trực tiếp trên web.\n"
        "Nguồn CS đưa lên không có template cố định, có thể là Excel nhiều sheet, DOCX, PDF OCR, hoặc text rất lộn xộn.\n\n"
        "Nhiệm vụ: chuyển raw extraction thành Markdown dễ đọc, có cấu trúc, nhưng vẫn là SOURCE EVIDENCE, không phải policy mới.\n\n"
        "Quy tắc bắt buộc:\n"
        "- Không thêm policy, điều kiện, exception, SLA, số điện thoại, macro, hoặc bước xử lý không có trong raw source.\n"
        "- Không xoá thông tin nghiệp vụ quan trọng. Nếu đoạn quá rối, giữ lại trong mục tương ứng và ghi warning.\n"
        "- Được phép đổi layout: heading, bullet, numbered list, bảng Markdown, callout Lưu ý, decision tree text.\n"
        "- Giữ nguyên mã, kênh, SĐT, email, case reason, tên sheet, ngày hiệu lực, Yes/No, TH1/TH2, B1/B2, ký hiệu nghiệp vụ.\n"
        "- Với Excel nhiều sheet, mỗi sheet nên thành một section. Sheet lịch sử/cũ/chưa áp dụng phải ghi rõ trong heading hoặc note nếu raw source thể hiện.\n"
        "- Với dòng dạng label:value, render thành label rõ ràng. Với đoạn dài chứa nhiều điều kiện, tách thành list lồng nhau vừa đủ để scan.\n"
        "- Nếu không chắc cấu trúc, giữ nguyên text trong blockquote hoặc bullet và thêm warning, không tự suy diễn.\n\n"
        "Trả CHỈ JSON object shape:\n"
        "{\"title\":\"\",\"markdown\":\"\",\"sections\":[],\"warnings\":[],\"coverage_report\":{}}.\n\n"
        "markdown phải là Markdown thuần, không HTML. Dùng tiếng Việt tự nhiên, ngắn gọn, dễ đọc cho CS.\n"
        "sections là danh sách ngắn {title, source_hint, confidence} để UI/debug scan.\n"
        "coverage_report gồm raw_text_chars, formatted_chars, omitted_or_uncertain_areas, source_preservation_notes.\n\n"
        f"Filename: {filename}\n"
        f"Detected document_type: {document_type}\n"
        f"Detected source_type: {source_type}\n\n"
        f"Raw extraction:\n{raw_text[:60000]}"
    )
    payload = {
        "model": settings.openrouter_refine_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": formatting_prompt},
        ],
        "response_format": response_format_for_schema("source_evidence_view_payload"),
        "temperature": 0.05,
    }
    breakdown = base_ai_breakdown(
        filename=filename,
        flow="source_evidence_view",
        model=str(payload["model"]),
        prompt=formatting_prompt,
        raw_text=raw_text,
        temperature=0.05,
    )
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }
    content = ""
    parsed: Any = None
    output_warnings: list[str] = []
    error = ""
    repaired = False
    status = "failed"
    try:
        content = completion_content(payload, headers)
        parsed, repaired = parse_json_with_repair(content, payload, headers)
        if not isinstance(parsed, dict):
            error = "source_evidence_formatter_not_object"
            output_warnings = [error]
            return {}, output_warnings, error
        markdown = str(parsed.get("markdown") or "").strip()
        if not markdown:
            error = "source_evidence_formatter_empty_markdown"
            output_warnings = [error]
            return {}, output_warnings, error
        model_warnings = [str(warning) for warning in parsed.get("warnings", []) if warning] if isinstance(parsed.get("warnings"), list) else []
        coverage_report = parsed.get("coverage_report") if isinstance(parsed.get("coverage_report"), dict) else {}
        sections = parsed.get("sections") if isinstance(parsed.get("sections"), list) else []
        output = {
            "title": str(parsed.get("title") or filename.rsplit(".", 1)[0])[:240],
            "format": "markdown",
            "formatter": "ai_source_evidence_view",
            "model": settings.openrouter_refine_model,
            "markdown": markdown[:120000],
            "markdown_truncated": len(markdown) > 120000,
            "raw_text_chars": len(raw_text),
            "sections": sections[:80],
            "warnings": model_warnings,
            "coverage_report": {
                **coverage_report,
                "raw_text_chars": len(raw_text),
                "formatted_chars": len(markdown),
            },
        }
        output_warnings = ["openrouter_source_evidence_formatter_used", *[f"source_evidence_warning:{warning}" for warning in model_warnings[:10]]]
        if repaired:
            output_warnings.append("openrouter_json_repair_used")
        status = "completed"
        return output, output_warnings, ""
    except json.JSONDecodeError as exc:
        error = f"source_evidence_formatter_invalid_json:{exc.msg}:{exc.pos}"
        output_warnings = [error]
        return {}, output_warnings, error
    except Exception as exc:
        error = f"source_evidence_formatter_failed:{exc.__class__.__name__}"
        output_warnings = [error]
        return {}, output_warnings, error
    finally:
        record_ai_breakdown(
            {
                **breakdown,
                "error": error,
                "parsed_response": json_preview(parsed) if parsed is not None else None,
                "raw_response": ai_response_preview(content),
                "repairs": {"json_repair_used": repaired},
                "status": status,
                "warnings": output_warnings[:40],
            }
        )


def extract_rule_table_units(filename: str, raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled():
        record_ai_breakdown({"filename": filename, "flow": "rule_table", "status": "skipped", "skip_reason": "openrouter_disabled"})
        return [], ["openrouter_disabled"]

    extraction_prompt = (
        RULE_TABLE_EXTRACTION_PROMPT
        + "\n\nPipeline-specific constraints for the existing extraction architecture:\n"
        "Hãy chuyển tài liệu Excel/bảng quy định CS này thành SOP draft có cấu trúc để CS Ops review. "
        "Không hardcode và không tự bịa policy. Chỉ dùng thông tin có trong source.\n\n"
        "Yêu cầu bắt buộc:\n"
        "- Trả JSON theo shape policy table ở trên: full_sop object + units array + warnings/metadata_suggestions/coverage_report. Không bỏ full_sop.\n"
        "- title là nhãn ngắn 4-10 từ để agent scan/search; không copy nguyên câu content vào title.\n"
        "- Phải có đúng 1 unit_type=\"full_sop\" với metadata.retrieval_scope=\"document\".\n"
        "- Mỗi unit bắt buộc có source_refs. Nếu file là Excel, tuyệt đối không dùng source_type=\"text\" cho source_refs; phải dùng source_type=\"excel\" và source_refs[].sheet. Thêm row_start/row_end nếu rule đến từ dòng cụ thể. full_sop có thể dùng sheet/row range tổng.\n"
        "- Tạo các unit nhỏ cho từng rule/action quan trọng với unit_type như routing_rule, validation_rule, handling_rule, warning, macro_script.\n"
        "- Nếu source là policy matrix/table, mỗi dòng logic của bảng phải thành một policy_rule hoặc exception_rule atomic unit. Không tách ví dụ thành unit riêng; attach examples vào rule cha gần nhất.\n"
        "- Với bảng quy định làm tròn/threshold, trích metadata rounding_threshold, rounding_directions, rounding_applies, service, case_type, tags, aliases nếu có căn cứ trong source.\n"
        "- Nếu một dòng ghi \"Không áp dụng\", dùng unit_type=\"exception_rule\" và giữ source_refs đến đúng dòng bảng.\n"
        "- Nếu có nhiều sheet theo ngày/version, chọn sheet mới nhất/hiện hành làm active rule units; sheet cũ chỉ ghi trong metadata.historical_sheets hoặc warning, không tạo active rule units từ sheet cũ.\n"
        "- Với mỗi rule unit, metadata nên giữ các field/cột có trong bảng dưới dạng lowercase snake_case; ưu tiên source_sheet, source_row, domain, audience, priority, action, condition, owner, system, channel, risk_level, tags, aliases, case_reasons nếu có căn cứ.\n"
        "- Nếu field không có trong source, không đoán. Để missing/null và thêm warning nếu quan trọng.\n"
        "- title/content/user-facing metadata phải là tiếng Việt tự nhiên; UI labels vẫn do frontend xử lý.\n"
        "- Nếu source thể hiện rủi ro tài chính, tài khoản, bảo mật/riêng tư, giao tiếp khách hàng, escalation, hoặc compliance, đặt metadata.risk_level phù hợp và tạo warning/compliance unit nếu đủ căn cứ.\n\n"
        f"Filename: {filename}\n\nSource text:\n{raw_text[:50000]}"
    )
    payload = {
        "model": settings.openrouter_extraction_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": extraction_prompt,
            },
        ],
        "response_format": response_format_for_schema("rule_table_payload"),
        "temperature": 0.05,
    }
    breakdown = base_ai_breakdown(
        filename=filename,
        flow="rule_table",
        model=str(payload["model"]),
        prompt=extraction_prompt,
        raw_text=raw_text,
        temperature=0.05,
    )
    content = ""
    parsed: Any = None
    normalized: list[dict[str, Any]] = []
    output_warnings: list[str] = []
    status = "failed"
    error = ""
    repaired = False
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }

    try:
        content = completion_content(payload, headers)
        parsed, repaired = parse_json_with_repair(content, payload, headers)
        normalized_payload, model_warnings = normalize_rule_table_response_payload(parsed)
        payload_model = ExtractedUnitsPayload.model_validate(normalized_payload)
        normalized = [normalize_unit(unit.model_dump()) for unit in payload_model.units]
        usable = [unit for unit in normalized if unit["content"]]
        usable, source_ref_repair_warnings = repair_spreadsheet_source_refs_from_raw_text(usable, filename, raw_text)
        if not any(unit["unit_type"] == "full_sop" for unit in usable):
            output_warnings = ["openrouter_missing_full_sop_unit"]
            error = "openrouter_missing_full_sop_unit"
            return [], output_warnings
        missing_refs = source_ref_validation_errors(usable, filename)
        if missing_refs:
            output_warnings = [*source_ref_repair_warnings, *missing_refs]
            error = ",".join(missing_refs)
            return [], output_warnings
        warnings = [
            "openrouter_rule_table_extraction_used",
            *source_ref_repair_warnings,
            *[f"model_warning:{warning}" for warning in model_warnings],
        ]
        if repaired:
            warnings.append("openrouter_json_repair_used")
        output_warnings = warnings
        status = "completed"
        return usable, warnings
    except json.JSONDecodeError as exc:
        error = f"openrouter_rule_table_invalid_json:{exc.msg}:{exc.pos}"
        output_warnings = [error]
        return [], output_warnings
    except ValidationError as exc:
        error = f"openrouter_rule_table_validation_failed:{validation_summary(exc)}"
        output_warnings = [error]
        return [], output_warnings
    except Exception as exc:
        error = f"openrouter_rule_table_extraction_failed:{exc.__class__.__name__}"
        output_warnings = [error]
        return [], output_warnings
    finally:
        record_ai_breakdown(
            {
                **breakdown,
                "error": error,
                "normalized_unit_count": len(normalized),
                "normalized_unit_types": sorted({str(unit.get("unit_type") or "") for unit in normalized if isinstance(unit, dict)}),
                "parsed_response": json_preview(parsed) if parsed is not None else None,
                "raw_response": ai_response_preview(content),
                "repairs": {
                    "json_repair_used": repaired,
                    "source_ref_repairs": [warning for warning in output_warnings if warning.startswith("source_refs_repaired_from_text_lines")],
                },
                "status": status,
                "warnings": output_warnings[:40],
            }
        )


def extract_mixed_docx_policy_units(filename: str, raw_text: str, structured_blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled():
        record_ai_breakdown({"filename": filename, "flow": "mixed_docx_policy", "status": "skipped", "skip_reason": "openrouter_disabled"})
        return [], ["openrouter_disabled"]

    extraction_prompt = (
        MIXED_DOCX_POLICY_EXTRACTION_PROMPT
        + "\n\nPipeline-specific constraints:\n"
        "- Trả đúng ExtractedUnit shape: unit_type, title, content, confidence, metadata, source_refs.\n"
        "- metadata phải giữ section_path, actor, affected_audience, channel, risk_level, risk_category khi có căn cứ.\n"
        "- Với table rows, metadata.rows phải giữ cells theo header và source_refs docx_table.\n"
        "- Giữ Open/Body/Close đúng vị trí dưới section_path Email; không đưa bảng xuống cuối tài liệu.\n\n"
        f"Filename: {filename}\n\n"
        f"Structured DOCX blocks JSON:\n{json.dumps(structured_blocks[:240], ensure_ascii=False)[:50000]}\n\n"
        f"Ordered raw text fallback:\n{raw_text[:12000]}"
    )
    payload = {
        "model": settings.openrouter_extraction_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": extraction_prompt},
        ],
        "response_format": response_format_for_schema("mixed_docx_policy_payload"),
        "temperature": 0.03,
    }
    breakdown = base_ai_breakdown(
        filename=filename,
        flow="mixed_docx_policy",
        model=str(payload["model"]),
        prompt=extraction_prompt,
        raw_text=raw_text,
        temperature=0.03,
    )
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }
    content = ""
    parsed: Any = None
    normalized: list[dict[str, Any]] = []
    output_warnings: list[str] = []
    status = "failed"
    error = ""
    repaired = False
    try:
        content = completion_content(payload, headers)
        parsed, repaired = parse_json_with_repair(content, payload, headers)
        normalized_payload, model_warnings = normalize_rule_table_response_payload(parsed)
        payload_model = ExtractedUnitsPayload.model_validate(normalized_payload)
        normalized = [normalize_unit(unit.model_dump()) for unit in payload_model.units]
        usable = [unit for unit in normalized if unit["content"]]
        if not any(unit["unit_type"] == "full_sop" for unit in usable):
            output_warnings = ["openrouter_mixed_docx_missing_full_sop_unit"]
            error = "openrouter_mixed_docx_missing_full_sop_unit"
            return [], output_warnings
        missing_refs = source_ref_validation_errors(usable, filename)
        if missing_refs:
            output_warnings = missing_refs
            error = ",".join(missing_refs)
            return [], output_warnings
        warnings = ["openrouter_mixed_docx_policy_extraction_used", *[f"model_warning:{warning}" for warning in model_warnings]]
        if repaired:
            warnings.append("openrouter_json_repair_used")
        output_warnings = warnings
        status = "completed"
        return usable, warnings
    except json.JSONDecodeError as exc:
        error = f"openrouter_mixed_docx_invalid_json:{exc.msg}:{exc.pos}"
        output_warnings = [error]
        return [], output_warnings
    except ValidationError as exc:
        error = f"openrouter_mixed_docx_validation_failed:{validation_summary(exc)}"
        output_warnings = [error]
        return [], output_warnings
    except Exception as exc:
        error = f"openrouter_mixed_docx_extraction_failed:{exc.__class__.__name__}"
        output_warnings = [error]
        return [], output_warnings
    finally:
        record_ai_breakdown(
            {
                **breakdown,
                "error": error,
                "normalized_unit_count": len(normalized),
                "normalized_unit_types": sorted({str(unit.get("unit_type") or "") for unit in normalized if isinstance(unit, dict)}),
                "parsed_response": json_preview(parsed) if parsed is not None else None,
                "raw_response": ai_response_preview(content),
                "repairs": {"json_repair_used": repaired},
                "status": status,
                "warnings": output_warnings[:40],
            }
        )


def refine_extracted_units(
    *,
    filename: str,
    raw_text: str,
    document_type: str,
    source_type: str,
    units: list[dict[str, Any]],
    source_blocks: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    if not enabled():
        return [], {"llm_refine_status": "skipped", "reason": "openrouter_disabled"}, ["openrouter_refine_disabled"]
    if not units:
        return [], {"llm_refine_status": "skipped", "reason": "no_units"}, ["openrouter_refine_no_units"]

    payload = {
        "model": settings.openrouter_refine_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Bạn là bước refinement cuối cho extraction pipeline SOP CS. "
                    "Nhiệm vụ là làm sạch bản nháp đã trích xuất, KHÔNG trích xuất lại từ đầu và KHÔNG bịa policy ngoài source.\n\n"
                    "Trả JSON shape {\"units\":[ExtractedUnit...],\"refinement_report\":{},\"warnings\":[]}.\n\n"
                    "Việc cần làm:\n"
                    "- filter noise: bỏ unit trùng lặp rõ ràng hoặc ví dụ đứng riêng nếu đã attach được vào rule cha.\n"
                    "- normalize: title ngắn, content rõ, tiền tệ/ký hiệu giữ nguyên nghĩa nguồn.\n"
                    "- dedupe: chỉ gộp duplicate thật sự, không gộp các dòng bảng khác nhau.\n"
                    "- detect conflict: ghi vào refinement_report.conflicts, không tự chọn rule thắng nếu source không nói.\n"
                    "- group related rules: thêm metadata.rule_group_id/group_label/related_rule_titles cho các rule cùng nhóm.\n"
                    "- infer metadata: tags, aliases, service, case_type, risk_level, threshold/direction nếu có căn cứ.\n"
                    "- repair noisy extraction: ví dụ phải nằm trong metadata.examples/content của rule cha; không tạo standalone example unit.\n"
                    "- evaluate coverage: refinement_report.coverage gồm full_sop, atomic_units, policy_rules, exception_rules, source_ref_quality, missing_fields.\n\n"
                    "Guardrails bắt buộc:\n"
                    "- Mọi unit phải có source_refs hợp lệ. Ưu tiên giữ nguyên source_refs input.\n"
                    "- Không xoá full_sop.\n"
                    "- Không xoá atomic unit có source_ref dòng bảng riêng, trừ khi duplicate source_ref thật sự.\n"
                    "- Nếu nghi conflict/noisy nhưng chưa chắc, giữ unit và ghi warning/conflict.\n"
                    "- review_status luôn needs_review trừ khi input đã approved/reviewed.\n"
                    "- extraction_status/publish_blocked trong metadata nếu có thì giữ nguyên, không tự chuyển degraded thành structured.\n\n"
                    f"Filename: {filename}\n"
                    f"Document type: {document_type}\n"
                    f"Source type: {source_type}\n\n"
                    f"Source blocks preview:\n{json.dumps((source_blocks or [])[:80], ensure_ascii=False)[:22000]}\n\n"
                    f"Current draft units:\n{json.dumps(units[:120], ensure_ascii=False)[:42000]}\n\n"
                    f"Raw text preview:\n{raw_text[:12000]}"
                ),
            },
        ],
        "response_format": response_format_for_schema("extraction_refinement_payload", ExtractionRefinementPayload),
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
        if isinstance(parsed, dict) and "units" not in parsed:
            for key in ("refined_units", "draft_units", "extracted_units"):
                if isinstance(parsed.get(key), list):
                    parsed["units"] = parsed[key]
                    break
        payload_model = ExtractionRefinementPayload.model_validate(parsed)
        normalized = [normalize_unit(unit.model_dump()) for unit in payload_model.units]
        usable = [unit for unit in normalized if unit["content"]]
        usable, source_ref_repair_warnings = repair_spreadsheet_source_refs_from_raw_text(usable, filename, raw_text)
        if not any(unit["unit_type"] == "full_sop" for unit in usable):
            return [], {"llm_refine_status": "rejected", "reason": "missing_full_sop"}, ["openrouter_refine_missing_full_sop"]
        missing_refs = source_ref_validation_errors(usable, filename)
        if missing_refs:
            return [], {"llm_refine_status": "rejected", "reason": "missing_source_refs", "errors": missing_refs}, [
                *source_ref_repair_warnings,
                *missing_refs,
            ]
        report = {"llm_refine_status": "completed", **payload_model.refinement_report}
        warnings = ["openrouter_refine_used", *source_ref_repair_warnings, *payload_model.warnings]
        if repaired:
            warnings.append("openrouter_refine_json_repair_used")
        return usable, report, warnings
    except json.JSONDecodeError as exc:
        return [], {"llm_refine_status": "failed", "reason": "invalid_json"}, [f"openrouter_refine_invalid_json:{exc.msg}:{exc.pos}"]
    except ValidationError as exc:
        return [], {"llm_refine_status": "failed", "reason": "validation_failed"}, [f"openrouter_refine_validation_failed:{validation_summary(exc)}"]
    except Exception as exc:
        return [], {"llm_refine_status": "failed", "reason": exc.__class__.__name__}, [f"openrouter_refine_failed:{exc.__class__.__name__}"]


def generate_grounded_answer(
    question: str,
    retrieval: RetrievalResponse,
    conversation: list[dict[str, str]] | None = None,
    session_summary: str = "",
    recent_user_context: list[str] | None = None,
    recent_assistant_context: list[str] | None = None,
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
            "chat_source_role": result.metadata.get("chat_source_role"),
            "chat_retrieval_reason": result.metadata.get("chat_retrieval_reason"),
            "collection_slug": result.metadata.get("collection_slug"),
            "task_type": result.metadata.get("task_type"),
            "relation_type": result.metadata.get("relation_type"),
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

    fallback_recent_user_context = [
        str(message.get("content", ""))[:500]
        for message in (conversation or [])
        if message.get("role") == "user" and message.get("content")
    ][-2:]
    recent_user_items = [str(item or "")[:500] for item in (recent_user_context or fallback_recent_user_context) if str(item or "").strip()][-2:]
    recent_user_text = "\n".join(f"- {item}" for item in recent_user_items)
    recent_assistant_items = [str(item or "")[:1200] for item in (recent_assistant_context or []) if str(item or "").strip()][-1:]
    recent_assistant_text = "\n".join(f"- {item}" for item in recent_assistant_items)
    session_summary_text = str(session_summary or "")[:700]
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
                    "Giữ nguyên wording vận hành nhạy cảm từ source khi có thể, nhất là các cụm như 'chưa thể hỗ trợ', 'từ chối hỗ trợ', 'KHÔNG cần chuyển case', thời hạn, điều kiện Yes/No, tên queue/tool/email. "
                    "Không đổi nhẹ wording làm thay đổi mức độ policy, ví dụ không tự đổi 'chưa thể hỗ trợ' thành 'từ chối hỗ trợ' nếu source không dùng cụm đó. "
                    "Nguồn có metadata chat_source_role=issue_router/tool_link/action_template chỉ là context điều hướng/tool/action, không đủ để kết luận policy nếu không có direct_sop hoặc related_sop. "
                    "Nếu chỉ có context index/tool/action mà không có source role direct_sop hoặc related_sop, phải nói chưa đủ SOP được link để trả lời chắc chắn. "
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
                    f"Current question: {question}\n\n"
                    f"Recent user context, for intent resolution only, not policy evidence:\n{recent_user_text or '(none)'}\n\n"
                    f"Previous assistant answer summary, for resolving follow-up references only, not policy evidence. Verify every claim against SOURCES before answering:\n{recent_assistant_text or '(none)'}\n\n"
                    f"Session summary, for intent resolution only, not policy evidence:\n{session_summary_text or '(none)'}\n\n"
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


def generate_chat_session_title(question: str, model: str | None = None) -> tuple[str, list[str]]:
    fallback = deterministic_chat_title(question)
    if not enabled():
        return fallback, ["openrouter_disabled_title_fallback"]
    payload = {
        "model": model or settings.openrouter_chat_simple_model or settings.openrouter_chat_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Đặt tên ngắn cho một chat session SOP nội bộ. "
                    "Tên tối đa 60 ký tự, không dấu ngoặc kép, không markdown, cùng ngôn ngữ với câu hỏi nếu rõ. "
                    "Chỉ trả JSON object: {\"title\":\"...\"}."
                ),
            },
            {"role": "user", "content": question[:1200]},
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
        parsed, _ = parse_json_with_repair(content, payload, headers)
        title = str(parsed.get("title") or "").strip()
        if title:
            return title[:60], ["openrouter_chat_title_used"]
    except Exception as exc:
        return fallback, [f"openrouter_chat_title_failed:{exc.__class__.__name__}"]
    return fallback, ["openrouter_chat_title_empty_fallback"]


def deterministic_chat_title(question: str) -> str:
    words = re.findall(r"[\wÀ-ỹ/.-]+", str(question or ""), flags=re.UNICODE)
    title = " ".join(words[:10]).strip()
    return title[:60] or "New chat"


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
                    "Nếu source khớp rõ với một collection vận hành, thêm suggested_collection_slug, suggested_collection_name, suggested_collection_type, suggested_collection_confidence. "
                    "Không tự set collection_slug vì collection cần CS Ops approve thủ công trước khi dùng production.\n"
                    "- title viết tiếng Việt theo tài liệu nguồn.\n"
                    "- audience là array lowercase theo đối tượng nghiệp vụ xuất hiện rõ trong source hoặc taxonomy đang dùng; để [] nếu không rõ.\n"
                    "- vertical/category/tags/case_reasons chỉ lấy hoặc suy luận rất sát từ source.\n"
                    "- suggested_collection_slug chỉ được dùng một trong các slug sau, để rỗng nếu không chắc: "
                    f"{json.dumps(list(COLLECTION_HINTS.keys()), ensure_ascii=False)}.\n"
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
    suggested_collection_slug = normalize_collection_slug(
        text(metadata.get("suggested_collection_slug") or metadata.get("collection_slug") or metadata.get("collection"))
    )
    suggested_collection_name = text(metadata.get("suggested_collection_name") or metadata.get("collection_name"))
    suggested_collection_type = text(metadata.get("suggested_collection_type") or metadata.get("collection_type"))
    suggested_collection_confidence = metadata.get("suggested_collection_confidence", metadata.get("collection_confidence", 0.0))
    try:
        suggested_collection_confidence_value = float(suggested_collection_confidence)
    except (TypeError, ValueError):
        suggested_collection_confidence_value = 0.0
    if suggested_collection_slug in COLLECTION_HINTS:
        default_name, default_type = COLLECTION_HINTS[suggested_collection_slug]
        suggested_collection_name = suggested_collection_name or default_name
        suggested_collection_type = suggested_collection_type or default_type
    else:
        suggested_collection_slug = ""
        suggested_collection_name = ""
        suggested_collection_type = ""
        suggested_collection_confidence_value = 0.0

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
        "collection_assignment_status": "suggested" if suggested_collection_slug else "unassigned",
        "collection_source": "ai_suggested" if suggested_collection_slug else "",
        "suggested_collection_slug": suggested_collection_slug,
        "suggested_collection_name": suggested_collection_name,
        "suggested_collection_type": suggested_collection_type,
        "suggested_collection_confidence": max(0.0, min(suggested_collection_confidence_value, 1.0)),
    }


def normalize_collection_slug(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(text.lower())).strip("-")
    if slug in COLLECTION_HINTS:
        return slug
    for candidate_slug, (name, _collection_type) in COLLECTION_HINTS.items():
        if slug == re.sub(r"[^a-z0-9]+", "-", strip_accents(name.lower())).strip("-"):
            return candidate_slug
    return ""


def strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    ).replace("đ", "d")


def normalize_unit(unit: dict[str, Any]) -> dict[str, Any]:
    metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
    content = str(unit.get("content") or "").strip()
    unit_type = str(unit.get("unit_type") or "workflow_step")
    raw_title = vietnamese_title(str(unit.get("title") or "").strip())
    title = meaningful_search_label(compact_unit_title(raw_title, content, unit_type), content, unit_type)
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
    if any(isinstance(ref, dict) and (ref.get("source_ref_synthetic") is True or ref.get("source_ref_quality") == "synthetic_missing") for ref in source_refs):
        return "synthetic_missing"
    has_pdf = False
    has_bbox = False
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        source_type = str(ref.get("source_type") or "").lower()
        if source_type == "docx_table" or (ref.get("table_index") is not None and ref.get("row_index") is not None):
            return "table_row"
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
    graph_refs = payload.workflow_graph.source_refs or payload.full_sop.source_refs
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
            "graph_fidelity_score": payload.workflow_graph.graph_fidelity_score or payload.workflow_graph.fidelity_score,
            "requires_human_review": payload.workflow_graph.requires_human_review,
            "review_reason": payload.workflow_graph.review_reason,
            "selected_flow": payload.workflow_graph.selected_flow,
            "repair_applied": payload.workflow_graph.repair_applied,
            "workflow_graph_repair_report": payload.workflow_graph.repair_report,
            "decision_edges_review_required": payload.workflow_graph.decision_edges_review_required,
            "missing_terminal_edges": payload.workflow_graph.missing_terminal_edges,
            "orphan_annotations": payload.workflow_graph.orphan_annotations,
            "unresolved_relations": payload.workflow_graph.unresolved_relations,
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
        f"- {node.get('id')}: {node.get('question') or node.get('title') or node.get('content')} ({node.get('actor', '')}, {node.get('phase', '')})"
        + (f" — {node.get('content')}" if node.get("content") and node.get("content") not in {node.get("title"), node.get("question")} else "")
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
            if ref.get("source_ref_synthetic") is True or ref.get("source_ref_quality") == "synthetic_missing":
                errors.append(f"source_ref_synthetic_missing:unit_{index}")
                continue
            if lower_name.endswith((".xlsx", ".xlsm", ".xls")) and not ref.get("sheet"):
                errors.append(f"source_ref_missing_sheet:unit_{index}")
            if lower_name.endswith(".pdf") and not ref.get("page"):
                errors.append(f"source_ref_missing_page:unit_{index}")
            if (
                lower_name.endswith(".docx")
                and ref.get("paragraph_index") is None
                and not ref.get("heading_path")
                and (ref.get("table_index") is None or ref.get("row_index") is None)
            ):
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
