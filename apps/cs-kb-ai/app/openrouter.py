from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas import ExtractedUnitsPayload, MetadataSuggestionPayload, WorkflowExtractionPayload


SYSTEM_PROMPT = """Bạn trích xuất bản nháp SOP chăm sóc khách hàng từ tài liệu nguồn lộn xộn.
Quy tắc:
- Chỉ trích xuất sự thật có trong tài liệu nguồn.
- Không tự tạo policy, refund rule, security rule, hoặc nhánh workflow không có trong nguồn.
- Chỉ trả JSON, không giải thích ngoài JSON.
- Tất cả unit chỉ là bản nháp để CS Ops review, không được xem là đã phê duyệt.
- Mọi trường user-facing phải viết bằng tiếng Việt tự nhiên: title, content, note, script, warning, summary.
- Không dùng nhãn tiếng Anh chung chung như "Curated content", "Extracted workflow unit", "Workflow overview", "Initial verification script".
- Giữ nguyên mã nghiệp vụ/ký hiệu khi cần, ví dụ Trip ID, Order ID, RH, BF, QA, ZT, beFood.
- Ưu tiên unit nhỏ, dễ review: workflow_overview, verification_dependency, workflow_step, decision_point, macro_script, operational_note, security_note, related_document.
- Mỗi unit bắt buộc có source_refs để trace ngược về nguồn. Mỗi source_ref bắt buộc có source_type và source_file.
- source_refs theo loại file: Excel dùng {source_type:"excel", source_file, sheet, row_start, row_end, column_names}; PDF dùng {source_type:"pdf", source_file, page, bbox nếu có}; DOCX dùng {source_type:"docx", source_file, paragraph_index hoặc heading_path}; text/markdown dùng {source_type:"text", source_file, line_start, line_end}.
- Không có source_refs thì output bị reject.
"""


def enabled() -> bool:
    return bool(settings.openrouter_api_key.strip())


def completion_content(payload: dict[str, Any], headers: dict[str, str]) -> str:
    with httpx.Client(timeout=settings.openrouter_timeout_seconds) as client:
        response = client.post(
            f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    return str(body["choices"][0]["message"]["content"])


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
                        "{\"document_metadata\":{},\"full_sop\":{},\"workflow_graph\":{},\"atomic_units\":[],\"warnings\":[],\"search_enrichment\":{}}. "
                        "Không bỏ full_sop. Không bỏ workflow_graph. Nếu graph có nodes/edges trong text hoặc units, hãy tạo workflow_graph từ đó. "
                        "Nếu chỉ có units legacy, hãy chọn/tạo unit full_sop từ nội dung tổng quan và đưa các unit còn lại vào atomic_units. "
                        "Chỉ trả JSON object hợp lệ, không markdown. "
                        f"Validation errors: {validation_summary(exc)}"
                    ),
                },
            ],
        }
        repaired = parse_llm_json(completion_content(repair_payload, headers))
        return WorkflowExtractionPayload.model_validate(repaired), True


def extract_workflow_units(filename: str, raw_text: str, page_images: list[str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled():
        return [], ["openrouter_disabled"]

    extraction_prompt = (
        "Hãy trích xuất tài liệu workflow/swimlane SOP CS này thành JSON production draft. "
        "Trả đúng shape {\"document_metadata\":{},\"full_sop\":{},\"workflow_graph\":{},\"atomic_units\":[],\"warnings\":[],\"search_enrichment\":{}}.\n\n"
        "Yêu cầu document_metadata: title, effective_from nếu thấy trong nguồn, document_type=\"workflow_diagram\", sub_type nếu là swimlane_process, channel, audience, actors, phases, systems, risk_level, requires_layout_extraction=true, requires_human_review=true, extraction_confidence.\n"
        "Yêu cầu full_sop: là ExtractedUnit unit_type=\"full_sop\", metadata.retrieval_scope=\"document\", title/content tiếng Việt, source_refs có page.\n"
        "Yêu cầu workflow_graph: workflow_id, title, start_node_id, nodes, edges, graph_confidence 0..1, requires_human_review=true, review_reason. "
        "Edge dùng field from_node/to_node/condition, không dùng field tên 'from'. "
        "Node cần actor, phase OPEN/BODY/CLOSE nếu có, type start/action/decision/end/note, title/content/question. "
        "Nếu arrow/Yes-No không chắc chắn, vẫn extract best-effort nhưng đặt graph_confidence thấp và review_reason rõ.\n"
        "Yêu cầu atomic_units: tạo unit nhỏ dễ search như operational_instruction, routing_rule, policy_rule, sla_rule, decision_rule, escalation_rule, case_creation_rule, handoff_rule, macro_script, operational_note. "
        "Nếu source có Chat Social/Fanpage/Pancake thì bắt buộc tách riêng các unit: sla_rule, decision_rule, escalation_rule, case_creation_rule, handoff_rule, macro_script, operational_note. "
        "Mỗi unit có tags/aliases/phase/actor/risk_level nếu có căn cứ trong source. "
        "Bắt buộc title/content tiếng Việt. Không bịa rule ngoài nguồn.\n"
        "Mỗi full_sop/atomic_unit phải có source_refs: PDF cần source_type=\"pdf_diagram\" hoặc \"pdf\", source_file, page; bbox nếu biết, nếu không để [].\n\n"
        f"Filename: {filename}\n\nSource text:\n{raw_text[:18000]}"
    )
    user_content: str | list[dict[str, Any]]
    if page_images:
        user_content = [{"type": "text", "text": extraction_prompt}]
        user_content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in page_images[:3])
    else:
        user_content = extraction_prompt

    payload = {
        "model": settings.openrouter_model,
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
        normalized = workflow_payload_to_units(payload_model, filename)
        missing_refs = source_ref_validation_errors(normalized, filename)
        if missing_refs:
            return [], missing_refs
        warnings = ["openrouter_workflow_extraction_used", *payload_model.warnings]
        if repaired:
            warnings.append("openrouter_json_repair_used")
        if schema_repaired:
            warnings.append("openrouter_schema_repair_used")
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
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Hãy chuyển tài liệu Excel/bảng quy định CS này thành SOP draft có cấu trúc để CS Ops review. "
                    "Không hardcode và không tự bịa policy. Chỉ dùng thông tin có trong source.\n\n"
                    "Yêu cầu bắt buộc:\n"
                    "- Trả JSON shape {\"units\":[{\"unit_type\":\"...\",\"title\":\"...\",\"content\":\"...\",\"confidence\":0.0,\"metadata\":{...}}]}.\n"
                    "- Phải có đúng 1 unit_type=\"full_sop\" với metadata.retrieval_scope=\"document\".\n"
                    "- Mỗi unit bắt buộc có source_refs. Excel cần source_refs[].sheet và row_start/row_end nếu rule đến từ dòng cụ thể. full_sop có thể dùng sheet/row range tổng.\n"
                    "- Tạo các unit nhỏ cho từng rule/action quan trọng với unit_type như routing_rule, validation_rule, handling_rule, warning, macro_script.\n"
                    "- Nếu có nhiều sheet theo ngày/version, chọn sheet mới nhất/hiện hành làm active rule units; sheet cũ chỉ ghi trong metadata.historical_sheets hoặc warning, không tạo active rule units từ sheet cũ.\n"
                    "- Với mỗi rule unit, metadata nên có các field tìm được trong bảng: source_sheet, source_row, service/vertical, audience, priority, action, condition, owner, requires_ping, queue, reporter, risk_level, tags, aliases, case_reasons.\n"
                    "- Nếu field không có trong source, không đoán. Để missing/null và thêm warning nếu quan trọng.\n"
                    "- title/content/user-facing metadata phải là tiếng Việt tự nhiên; UI labels vẫn do frontend xử lý.\n"
                    "- Nếu có rủi ro payment/account/privacy/customer communication/escalation/ZT, đặt metadata.risk_level phù hợp và tạo unit warning nếu source đủ căn cứ.\n\n"
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
        "model": settings.openrouter_model,
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
                    "- audience là array, dùng lowercase business keys nếu rõ: customer, driver, merchant, internal.\n"
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
    payload_model = MetadataSuggestionPayload.model_validate(parsed)
    metadata = payload_model.metadata.model_dump()
    signals = payload_model.signals
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
        "unit_type": str(unit.get("unit_type") or "workflow_step"),
        "title": vietnamese_title(str(unit.get("title") or "").strip())[:180],
        "content": str(unit.get("content") or "").strip(),
        "confidence": max(0.0, min(confidence_value, 1.0)),
        "metadata": merged_metadata,
        "source_refs": source_refs,
    }


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
    graph_unit = {
        "unit_type": "workflow_graph",
        "title": payload.workflow_graph.title,
        "content": workflow_graph_summary(graph),
        "confidence": payload.workflow_graph.graph_confidence,
        "source_refs": [ref.model_dump() for ref in graph_refs],
        "metadata": {
            "retrieval_scope": "graph",
            "workflow_graph": graph,
            "graph_confidence": payload.workflow_graph.graph_confidence,
            "requires_human_review": payload.workflow_graph.requires_human_review,
            "review_reason": payload.workflow_graph.review_reason,
            "source_filename": filename,
            "tags": payload.search_enrichment.get("tags", []),
            "aliases": payload.search_enrichment.get("aliases", []),
        },
    }
    units.append(normalize_unit(graph_unit))

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
