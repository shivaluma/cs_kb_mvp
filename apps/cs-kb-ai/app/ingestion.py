from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from app.embedding import embed_text
from app.openrouter import (
    extract_rule_table_units,
    extract_workflow_units,
    extract_workflow_units_v2,
    finish_ai_breakdown_capture,
    format_source_evidence_view,
    refine_extracted_units,
    start_ai_breakdown_capture,
    suggest_document_metadata,
)
from app.schemas import DocumentMetadata
from app.text_processing import (
    Chunk,
    ai_units_to_chunks,
    checksum,
    chunk_text,
    classify_document,
    ensure_full_sop_layer,
    extract_docx_structure,
    extract_spreadsheet,
    extract_text,
    is_docx_file,
    is_spreadsheet_file,
    render_pdf_pages_as_data_urls,
    spreadsheet_rows,
    tokenize,
    workflow_units_to_chunks,
)
from app.visual_layout import (
    bbox_distance,
    compact_visual_context,
    extract_pdf_visual_layout,
    iou_bbox,
    union_bboxes,
)


CONDITION_ACTION_SIGNALS = [
    "nếu",
    "neu",
    "trường hợp",
    "truong hop",
    "đối với",
    "doi voi",
    "thì",
    "thi",
    "không được",
    "khong duoc",
    "được phép",
    "duoc phep",
    "bắt buộc",
    "bat buoc",
    "cần",
    "can",
    "phải",
    "phai",
    "xử lý",
    "xu ly",
    "chuyển",
    "chuyen",
    "kiểm tra",
    "kiem tra",
]

WARNING_SIGNALS = [
    "lưu ý",
    "luu y",
    "zt",
    "rủi ro",
    "rui ro",
    "không cung cấp",
    "khong cung cap",
    "bảo mật",
    "bao mat",
    "compliance",
    "qa chấm lỗi",
    "qa cham loi",
]

AI_STRUCTURED_DOCUMENT_TYPES = {"policy_rule", "policy_table", "workflow_diagram"}


def prepare_document_version(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    metadata: DocumentMetadata,
) -> tuple[str, str, list[dict[str, Any]], list[str], dict[str, Any]]:
    raw_text, warnings, raw_context = extract_raw_evidence(filename, content_type, data)
    blocks = parse_document_blocks(filename, content_type, raw_text, raw_context)
    classification = classify_document(filename, content_type, raw_text)
    warnings.extend(classification.warnings)
    visual_layout: dict[str, Any] = {}
    if classification.document_type == "workflow_diagram" and is_pdf_file(filename, content_type):
        visual_layout, visual_warnings = extract_pdf_visual_layout(data, filename)
        warnings.extend(visual_warnings)
        if visual_layout:
            raw_context["visual_layout"] = visual_layout
            blocks.extend(visual_blocks_for_map(visual_layout))
    pipeline_artifacts = [
        stage_artifact(
            "map",
            "source_blocks",
            source_blocks_payload(filename, content_type, raw_text, blocks, raw_context, warnings),
        ),
        stage_artifact(
            "classify",
            "classification_result",
            classification_payload(classification),
        ),
    ]
    if visual_layout:
        pipeline_artifacts.append(stage_artifact("map", "visual_layout_blocks", visual_layout_payload(visual_layout)))
        pipeline_artifacts.append(stage_artifact("map", "visual_graph_candidates", visual_graph_payload(visual_layout)))
        semantic_refinement = build_workflow_semantic_refinement(
            filename=filename,
            visual_layout=visual_layout,
            source_blocks=blocks,
            classification=classification,
        )
        visual_layout["semantic_refinement"] = semantic_refinement
        raw_context["workflow_semantic_refinement"] = semantic_refinement
        pipeline_artifacts.append(
            stage_artifact(
                "workflow_semantic_refine",
                "workflow_semantic_refinement",
                semantic_refinement,
            )
        )

    if raw_text.strip() and classification.document_type in AI_STRUCTURED_DOCUMENT_TYPES:
        source_view_token = start_ai_breakdown_capture()
        try:
            source_view_payload, source_view_warnings, source_view_error = format_source_evidence_view(
                filename=filename,
                raw_text=raw_text,
                document_type=classification.document_type,
                source_type=classification.source_type,
            )
        finally:
            source_view_breakdowns = finish_ai_breakdown_capture(source_view_token)
        warnings.extend(source_view_warnings)
        if source_view_payload:
            pipeline_artifacts.append(
                stage_artifact(
                    "map",
                    "source_evidence_view",
                    source_view_payload,
                    status="failed" if source_view_error else "completed",
                    error=source_view_error,
                )
            )
        if source_view_breakdowns:
            pipeline_artifacts.append(
                stage_artifact(
                    "map",
                    "source_evidence_ai_breakdown",
                    ai_breakdown_payload(source_view_breakdowns, source_view_warnings, source_view_error),
                    status="failed" if source_view_error else "completed",
                    error=source_view_error,
                )
            )

    source_chunks: list[Any] = []
    ai_error = ""
    if classification.document_type in {"policy_rule", "policy_table", "workflow_diagram"}:
        ai_warnings: list[str] = []
        ai_breakdown_token = start_ai_breakdown_capture()
        try:
            source_chunks, ai_warnings, ai_error = try_ai_structuring(
                filename=filename,
                content_type=content_type,
                data=data,
                raw_text=raw_text,
                classification=classification,
                visual_layout=visual_layout,
                raw_context=raw_context,
            )
        finally:
            ai_breakdowns = finish_ai_breakdown_capture(ai_breakdown_token)
        warnings.extend(ai_warnings)
        pipeline_artifacts.append(
            stage_artifact(
                "ai_structure",
                "ai_structured_payload",
                ai_structured_payload(source_chunks, ai_warnings),
                status="failed" if ai_error else "completed",
                error=ai_error,
            )
        )
        if ai_breakdowns:
            pipeline_artifacts.append(
                stage_artifact(
                    "ai_structure",
                    "ai_breakdown",
                    ai_breakdown_payload(ai_breakdowns, ai_warnings, ai_error),
                    status="failed" if ai_error else "completed",
                    error=ai_error,
                )
            )

    if not source_chunks and classification.document_type not in AI_STRUCTURED_DOCUMENT_TYPES:
        source_chunks = mark_structured_chunks(chunk_text(raw_text))

    if not source_chunks:
        if ai_error:
            warnings.append(ai_error)
        source_chunks = build_degraded_draft(
            filename=filename,
            content_type=content_type,
            raw_text=raw_text,
            classification=classification,
            blocks=blocks,
            raw_context=raw_context,
            ai_error=ai_error,
        )
        pipeline_artifacts.append(
            stage_artifact(
                "plan",
                "degraded_draft",
                draft_units_payload(source_chunks),
                status="degraded",
                error=ai_error,
            )
        )
    else:
        source_chunks = normalize_units(source_chunks)

    if should_create_structuring_plan(classification.document_type, raw_text, raw_context, source_chunks):
        pipeline_artifacts.append(stage_artifact("plan", "structuring_plan", structuring_plan_payload(classification, source_chunks, raw_context)))

    source_chunks = validate_units_for_review(source_chunks, classification.document_type)

    source_chunks = ensure_full_sop_layer(
        source_chunks,
        raw_text,
        filename,
        classification.source_type,
        classification.document_type,
    )
    source_chunks = normalize_units(source_chunks)

    source_chunks, refinement_report, refinement_warnings, refinement_error = refine_units_for_delivery(
        filename=filename,
        raw_text=raw_text,
        classification=classification,
        blocks=blocks,
        source_chunks=source_chunks,
    )
    warnings.extend(refinement_warnings)
    pipeline_artifacts.append(
        stage_artifact(
            "refine",
            "refinement_report",
            refinement_report,
            status="failed" if refinement_error else "completed",
            error=refinement_error,
        )
    )

    extraction_status = "degraded" if any(chunk.metadata.get("extraction_status") == "degraded" for chunk in source_chunks) else "structured"
    lifecycle_status = "degraded_structured_draft" if extraction_status == "degraded" else "structured_draft"
    publish_blocked = extraction_status == "degraded"
    publish_blocked_reason = ""
    if publish_blocked:
        publish_blocked_reason = next(
            (
                str(chunk.metadata.get("publish_blocked_reason"))
                for chunk in source_chunks
                if chunk.metadata.get("publish_blocked_reason")
            ),
            "ai_structuring_failed_requires_manual_curation",
        )
    phase_history = ["uploaded", "raw_extracted", "classified"]
    if classification.document_type in AI_STRUCTURED_DOCUMENT_TYPES:
        phase_history.append("ai_structuring_failed" if extraction_status == "degraded" else "structured_draft")
    else:
        phase_history.append("structured_draft")
    if extraction_status == "degraded":
        phase_history.append("degraded_structured_draft")

    enrichment = {
        "document_type": classification.document_type,
        "source_type": classification.source_type,
        "review_status": "needs_review",
        "extraction_confidence": classification.confidence,
        "extraction_status": extraction_status,
        "extraction_lifecycle_status": lifecycle_status,
        "extraction_error": "",
        "ai_error": ai_error or None,
        "ai_structuring_status": "failed" if extraction_status == "degraded" and ai_error else ("succeeded" if classification.document_type in AI_STRUCTURED_DOCUMENT_TYPES else "skipped"),
        "extraction_phase_history": phase_history,
        "extraction_warnings": warnings,
        "publish_blocked": publish_blocked,
        "publish_blocked_reason": publish_blocked_reason,
        "requires_human_review": True,
        "source_ref_quality": aggregate_source_ref_quality(source_chunks),
    }

    chunks = embed_chunks(source_chunks, metadata.model_dump(), enrichment, filename)
    pipeline_artifacts.append(stage_artifact("refine", "draft_units", draft_units_payload(source_chunks)))
    verification_report = verification_report_payload(chunks, classification.document_type)
    pipeline_artifacts.append(stage_artifact("verify", "verification_report", verification_report, status="failed" if verification_report["hard_blockers"] else "completed"))
    pipeline_artifacts.append(stage_artifact("verify", "publish_readiness_report", verification_report, status="failed" if verification_report["hard_blockers"] else "completed"))
    enrichment.update(
        {
            "pipeline_artifacts": pipeline_artifacts,
            "pipeline_current_stage": "verify",
            "pipeline_job_status": "degraded" if extraction_status == "degraded" else "completed",
        }
    )

    if not chunks:
        warnings.append("no_chunks_created")

    return raw_text, checksum(data), chunks, list(dict.fromkeys(warnings)), enrichment


def extract_raw_evidence(filename: str, content_type: str, data: bytes) -> tuple[str, list[str], dict[str, Any]]:
    if is_spreadsheet_file(filename.lower(), content_type):
        raw_text, warnings, spreadsheet_chunks = extract_spreadsheet(filename.lower(), data)
        return raw_text, warnings, {"spreadsheet_chunks": spreadsheet_chunks, "sheets": spreadsheet_rows(filename.lower(), data)}
    if is_docx_file(filename.lower(), content_type):
        raw_text, blocks, tables = extract_docx_structure(data)
        return raw_text, [], {"docx_blocks": blocks, "docx_tables": tables}
    raw_text, warnings = extract_text(filename, content_type, data)
    return raw_text, warnings, {}


def is_pdf_file(filename: str, content_type: str) -> bool:
    return filename.lower().endswith(".pdf") or content_type == "application/pdf"


def parse_document_blocks(filename: str, content_type: str, raw_text: str, raw_context: dict[str, Any]) -> list[dict[str, Any]]:
    if "sheets" in raw_context:
        return [
            {"type": "sheet", "sheet": sheet_name, "rows": rows}
            for sheet_name, rows in raw_context.get("sheets", [])
        ]
    if isinstance(raw_context.get("docx_blocks"), list):
        return raw_context["docx_blocks"]
    if filename.lower().endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        paragraphs = [line.strip() for line in raw_text.splitlines() if line.strip()]
        return [{"type": "paragraph", "paragraph_index": index, "text": text} for index, text in enumerate(paragraphs)]
    if filename.lower().endswith(".pdf") or content_type == "application/pdf":
        return pdf_text_blocks(raw_text)
    return text_line_blocks(raw_text)


def try_ai_structuring(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    raw_text: str,
    classification: Any,
    visual_layout: dict[str, Any] | None = None,
    raw_context: dict[str, Any] | None = None,
) -> tuple[list[Any], list[str], str]:
    warnings: list[str] = []
    raw_context = raw_context or {}
    try:
        if classification.document_type in {"policy_rule", "policy_table"}:
            table_chunks = extract_docx_policy_table_chunks(filename, content_type, raw_text, raw_context, classification)
            if table_chunks:
                return mark_structured_chunks(table_chunks), ["docx_policy_table_extraction_used"], ""
            llm_units, llm_warnings = extract_rule_table_units(filename, raw_text)
            warnings.extend(llm_warnings)
            if not llm_units:
                return [], warnings, f"ai_{classification.document_type}_structuring_failed:{','.join(llm_warnings)}"
            chunks = ai_units_to_chunks(llm_units, filename, classification.source_type, classification.document_type)
            return mark_structured_chunks(chunks), warnings, ""
        if classification.document_type == "workflow_diagram":
            page_images, render_warnings = render_pdf_pages_as_data_urls(data) if filename.lower().endswith(".pdf") or content_type == "application/pdf" else ([], [])
            warnings.extend(render_warnings)
            if not page_images:
                return [], warnings, "ai_workflow_structuring_failed:pdf_vision_render_required"
            semantic_refinement = raw_context.get("workflow_semantic_refinement") if isinstance(raw_context.get("workflow_semantic_refinement"), dict) else {}
            v2_units, v2_warnings = extract_workflow_units_v2(filename, raw_text, page_images=page_images, visual_context=None)
            warnings.extend(v2_warnings)
            v2_chunks = workflow_units_to_chunks(v2_units, raw_text, filename) if v2_units else []
            if v2_chunks:
                v2_quality_error = workflow_structuring_quality_error(v2_chunks, v2_warnings)
                if not v2_quality_error:
                    warnings.append("workflow_extraction_flow:v2_vision_primary")
                    return mark_structured_chunks(v2_chunks), warnings, ""
                warnings.append(f"workflow_v2_quality_rejected:{v2_quality_error}")

            visual_context = compact_visual_context(visual_layout) if visual_layout else None
            if visual_context:
                warnings.append("visual_graph_context_supplied_to_llm")
            llm_units, llm_warnings = extract_workflow_units(filename, raw_text, page_images=page_images, visual_context=visual_context)
            warnings.extend(llm_warnings)
            if semantic_refinement:
                llm_units = enrich_workflow_units_with_semantic_refinement(llm_units, semantic_refinement)
            chunks = workflow_units_to_chunks(llm_units, raw_text, filename) if llm_units else []
            if not chunks:
                semantic_chunks = semantic_workflow_structured_chunks(filename, raw_text, classification, semantic_refinement)
                if semantic_chunks:
                    warnings.append("semantic_workflow_structuring_used_after_ai_failure")
                    if llm_warnings:
                        warnings.append(f"ai_workflow_structuring_rejected:{','.join(llm_warnings[:3])}")
                    return mark_structured_chunks(semantic_chunks), warnings, ""
                return [], warnings, f"ai_workflow_structuring_failed:{','.join(llm_warnings)}"
            quality_error = workflow_structuring_quality_error(chunks, llm_warnings)
            if quality_error:
                semantic_chunks = semantic_workflow_structured_chunks(filename, raw_text, classification, semantic_refinement)
                if semantic_chunks:
                    warnings.append("semantic_workflow_structuring_used_after_ai_quality_reject")
                    warnings.append(f"ai_workflow_structuring_rejected:{quality_error}")
                    return mark_structured_chunks(semantic_chunks), warnings, ""
                return [], warnings, f"ai_workflow_structuring_failed:{quality_error}"
            return mark_structured_chunks(chunks), warnings, ""
    except Exception as exc:
        return [], warnings, f"ai_structuring_exception:{sanitize_ai_error(exc)}"
    return [], warnings, ""


def extract_docx_policy_table_chunks(
    filename: str,
    content_type: str,
    raw_text: str,
    raw_context: dict[str, Any],
    classification: Any,
) -> list[Chunk]:
    if not is_docx_file(filename.lower(), content_type):
        return []
    tables = raw_context.get("docx_tables")
    if not isinstance(tables, list):
        return []

    row_chunks: list[Chunk] = []
    source_refs: list[dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, dict) or not looks_like_docx_policy_rule_table(table):
            continue
        table_index = int(table.get("table_index") or 0)
        columns = [str(column) for column in table.get("columns", []) if str(column).strip()]
        if columns:
            source_refs.append(docx_table_source_ref(filename, table_index, 0, columns))
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            chunk = docx_policy_row_chunk(
                filename=filename,
                table_index=table_index,
                row=row,
                columns=columns,
                index=len(row_chunks) + 1,
                classification=classification,
            )
            if chunk:
                row_chunks.append(chunk)

    if not row_chunks:
        return []

    policy_count = sum(1 for chunk in row_chunks if chunk.metadata.get("unit_type") == "policy_rule")
    exception_count = sum(1 for chunk in row_chunks if chunk.metadata.get("unit_type") == "exception_rule")
    full_content = docx_policy_full_sop_content(raw_text, row_chunks)
    full_metadata = {
        "unit_type": "full_sop",
        "retrieval_scope": "document",
        "document_type": classification.document_type,
        "source_type": classification.source_type,
        "sub_type": "policy_table",
        "structure_type": "financial_threshold_matrix",
        "risk_level": "high",
        "required_unit_types": ["policy_rule", "exception_rule"] if exception_count else ["policy_rule"],
        "expected_policy_rule_count": policy_count,
        "expected_exception_rule_count": exception_count,
        "source_refs": source_refs or [docx_table_source_ref(filename, 0, 0, [])],
        "source_ref_quality": "table_row",
        "source_ref_acknowledged": True,
        "tags": ["rounding", "financial_policy", "refund"],
        "aliases": ["quy định làm tròn số tiền", "mốc làm tròn", "rounding policy"],
        "confidence": min(max(float(getattr(classification, "confidence", 0.84)), 0.0), 0.92),
        "review_status": "needs_review",
    }
    full_sop = Chunk(
        chunk_index=0,
        section="full_sop",
        heading=path_title(filename),
        content=full_content,
        token_count=len(tokenize(full_content)),
        metadata=full_metadata,
    )
    return [full_sop, *row_chunks]


def looks_like_docx_policy_rule_table(table: dict[str, Any]) -> bool:
    columns = [normalized_key(column) for column in table.get("columns", []) if str(column).strip()]
    column_text = " ".join(columns)
    has_case_matrix = (
        any(key in column_text for key in ["dich_vu", "service"])
        and any(key in column_text for key in ["truong_hop", "case"])
        and any(key in column_text for key in ["quy_tac", "rule", "lam_tron"])
    )
    row_text = normalized_search_text(json.dumps(table.get("rows", []), ensure_ascii=False))
    has_rounding_policy = "lam tron" in row_text and any(signal in row_text for signal in ["moc", "khong ap dung", "refund", "hoan", "rut"])
    return has_case_matrix and has_rounding_policy


def docx_policy_row_chunk(
    *,
    filename: str,
    table_index: int,
    row: dict[str, Any],
    columns: list[str],
    index: int,
    classification: Any,
) -> Chunk | None:
    values = row.get("values") if isinstance(row.get("values"), dict) else {}
    service = value_by_header(values, columns, ["dich_vu", "service"])
    case_name = value_by_header(values, columns, ["truong_hop", "case"])
    rule_text = value_by_header(values, columns, ["quy_tac", "lam_tron", "rule"])
    note_text = value_by_header(values, columns, ["luu_y", "note"])
    if not (service or case_name or rule_text):
        return None

    row_index = int(row.get("row_index") or index)
    threshold = parse_rounding_threshold(rule_text)
    no_apply = is_no_apply_rule(rule_text)
    raw_notes, parsed_examples = extract_note_and_examples(note_text)
    examples = [] if no_apply else parsed_examples
    unit_type = "exception_rule" if no_apply else "policy_rule"
    source_ref = docx_table_source_ref(filename, table_index, row_index, columns)
    title = " - ".join(part for part in [service, case_name] if part).strip() or f"Dòng {row_index}"
    content = policy_row_content(
        service=service,
        case_name=case_name,
        rule_text=rule_text,
        no_apply=no_apply,
        threshold=threshold,
        notes=raw_notes,
        examples=examples,
    )
    row_text = " ".join([service, case_name, rule_text, note_text])
    metadata = {
        "unit_type": unit_type,
        "retrieval_scope": "unit",
        "document_type": classification.document_type,
        "source_type": classification.source_type,
        "sub_type": "policy_table",
        "structure_type": "financial_threshold_matrix",
        "service": normalize_service_key(service),
        "service_label": service,
        "case_type": normalized_key(case_name),
        "case_name": case_name,
        "rounding_applies": not no_apply,
        "rounding_threshold": threshold,
        "rounding_rule_raw": rule_text,
        "rounding_directions": rounding_directions(rule_text, threshold),
        "examples": examples,
        "examples_need_review": parsed_examples if no_apply and parsed_examples else [],
        "notes": raw_notes,
        "risk_level": "high",
        "tags": policy_tags(row_text, threshold, no_apply),
        "aliases": policy_aliases(service, case_name, threshold, no_apply),
        "source_table_index": table_index,
        "source_row_index": row_index,
        "source_columns": columns,
        "source_refs": [source_ref],
        "source_ref_quality": "table_row",
        "source_ref_acknowledged": True,
        "confidence": min(max(float(getattr(classification, "confidence", 0.84)), 0.0), 0.9),
        "review_status": "needs_review",
    }
    return Chunk(
        chunk_index=index,
        section=unit_type,
        heading=title[:180],
        content=content,
        token_count=len(tokenize(content)),
        metadata=metadata,
    )


def docx_policy_full_sop_content(raw_text: str, row_chunks: list[Chunk]) -> str:
    title = next((line.strip() for line in raw_text.splitlines() if line.strip()), "Quy định làm tròn số tiền")
    rules = []
    exceptions = []
    for chunk in row_chunks:
        first_line = next((line for line in chunk.content.splitlines() if line.strip()), chunk.content)
        if chunk.metadata.get("unit_type") == "exception_rule":
            exceptions.append(f"- {chunk.heading}: {first_line}")
        else:
            rules.append(f"- {chunk.heading}: {first_line}")
    sections = [
        title,
        "Mục đích: Quy định cách làm tròn số tiền theo từng dịch vụ và trường hợp trong bảng nguồn.",
    ]
    if rules:
        sections.extend(["", "Quy tắc áp dụng:", *rules])
    if exceptions:
        sections.extend(["", "Trường hợp không áp dụng:", *exceptions])
    return "\n".join(sections).strip()


def policy_row_content(
    *,
    service: str,
    case_name: str,
    rule_text: str,
    no_apply: bool,
    threshold: int | None,
    notes: list[str],
    examples: list[dict[str, str]],
) -> str:
    subject = " - ".join(part for part in [service, case_name] if part).strip()
    if no_apply:
        first = f"{subject}: Không áp dụng quy định làm tròn." if subject else "Không áp dụng quy định làm tròn."
    elif threshold:
        first = f"{subject}: {rounding_sentence(rule_text, threshold)}" if subject else rounding_sentence(rule_text, threshold)
    else:
        first = f"{subject}: {rule_text}." if subject else rule_text

    lines = [normalize_money_text(first)]
    for note in notes:
        lines.append(f"Lưu ý: {normalize_money_text(note)}")
    if examples:
        lines.append("Ví dụ:")
        for example in examples:
            lines.append(f"- {example['input']} -> {example['output']}")
    return "\n".join(line for line in lines if line.strip()).strip()


def rounding_sentence(rule_text: str, threshold: int) -> str:
    normalized = normalized_search_text(rule_text)
    if "<" in rule_text and ("≥" in rule_text or ">=" in rule_text):
        return f"Mốc làm tròn {threshold}đ: <{threshold} làm tròn xuống, >={threshold} làm tròn lên."
    if ">" in rule_text and ("≤" in rule_text or "<=" in rule_text):
        return f"Mốc làm tròn {threshold}đ: >{threshold} làm tròn lên, <={threshold} làm tròn xuống."
    if "xuong" in normalized and "len" in normalized:
        return f"Mốc làm tròn {threshold}đ theo quy tắc trong nguồn: {rule_text}."
    return f"Áp dụng quy tắc làm tròn: {rule_text}."


def parse_rounding_threshold(rule_text: str) -> int | None:
    match = re.search(r"(?:mốc\s*:?\s*)?(\d{2,6})\s*đ?", rule_text, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def is_no_apply_rule(rule_text: str) -> bool:
    return "khong ap dung" in normalized_search_text(rule_text)


def rounding_directions(rule_text: str, threshold: int | None) -> list[dict[str, Any]]:
    if threshold is None:
        return []
    directions: list[dict[str, Any]] = []
    if re.search(rf"<\s*{threshold}\b", rule_text):
        directions.append({"operator": "<", "threshold": threshold, "direction": "down"})
    if re.search(rf"(?:≥|>=)\s*{threshold}\b", rule_text):
        directions.append({"operator": ">=", "threshold": threshold, "direction": "up"})
    if re.search(rf">\s*{threshold}\b", rule_text) and not re.search(rf">=\s*{threshold}\b", rule_text):
        directions.append({"operator": ">", "threshold": threshold, "direction": "up"})
    if re.search(rf"(?:≤|<=)\s*{threshold}\b", rule_text):
        directions.append({"operator": "<=", "threshold": threshold, "direction": "down"})
    return directions


def extract_note_and_examples(note_text: str) -> tuple[list[str], list[dict[str, str]]]:
    notes: list[str] = []
    examples: list[dict[str, str]] = []
    for line in note_text.splitlines():
        text = line.strip()
        if not text:
            continue
        if re.match(r"^(ví dụ|vi du|vd)\s*:?\s*$", normalized_search_text(text), re.IGNORECASE):
            continue
        parsed = parse_example_line(text)
        if parsed:
            examples.extend(parsed)
            continue
        notes.append(text)
    return notes, examples


def parse_example_line(text: str) -> list[dict[str, str]]:
    if "->" not in text and "=>" not in text:
        return []
    left, right = re.split(r"->|=>", text, maxsplit=1)
    output = normalize_money_text(right.strip())
    inputs = re.findall(r"\d[\d,.]*(?:\s*đ)?", left)
    if not inputs and left.strip():
        inputs = [left.strip()]
    return [
        {"input": normalize_money_text(input_value), "output": output}
        for input_value in inputs
        if normalize_money_text(input_value) and output
    ]


def value_by_header(values: dict[str, Any], columns: list[str], candidates: list[str]) -> str:
    for column in columns:
        key = normalized_key(column)
        if any(candidate in key for candidate in candidates):
            return str(values.get(column) or "").strip()
    return ""


def docx_table_source_ref(filename: str, table_index: int, row_index: int, columns: list[str]) -> dict[str, Any]:
    return {
        "source_type": "docx_table",
        "source_file": filename,
        "table_index": table_index,
        "row_index": row_index,
        "column_names": columns,
    }


def policy_tags(text: str, threshold: int | None, no_apply: bool) -> list[str]:
    normalized = normalized_search_text(text)
    tags = ["rounding", "financial_policy"]
    if "befood" in normalized:
        tags.append("befood")
    if any(term in normalized for term in ["hoan", "refund", "boi hoan"]):
        tags.append("refund")
    if any(term in normalized for term in ["rut", "withdraw"]):
        tags.append("withdraw")
    if "pm04" in normalized:
        tags.append("pm04")
    if "pttt" in normalized or "thanh toan" in normalized:
        tags.append("payment_method")
    if "chiet khau" in normalized:
        tags.append("discount")
    if no_apply:
        tags.append("no_rounding")
    if threshold:
        tags.append(f"threshold_{threshold}")
    return list(dict.fromkeys(tags))


def policy_aliases(service: str, case_name: str, threshold: int | None, no_apply: bool) -> list[str]:
    aliases = [
        " ".join(part for part in [service, case_name, "làm tròn"] if part).strip(),
        " ".join(part for part in [case_name, "rounding"] if part).strip(),
    ]
    if threshold:
        aliases.append(f"mốc {threshold}đ")
        aliases.append(f"{threshold}đ rounding")
    if no_apply:
        aliases.append(f"{case_name} không làm tròn".strip())
        aliases.append("không áp dụng làm tròn")
    return [alias for alias in dict.fromkeys(aliases) if alias]


def normalize_service_key(service: str) -> str:
    normalized = normalized_key(service)
    if normalized in {"dich_vu_khac", "khac"}:
        return "other_services"
    return normalized or "unknown"


def normalized_key(value: str) -> str:
    return "_".join(tokenize(value))


def normalized_search_text(value: str) -> str:
    return " ".join(tokenize(value))


def normalize_money_text(value: str) -> str:
    return re.sub(r"\s+đ\b", "đ", str(value or "").strip()).replace(">=", "≥").replace("<=", "≤")


def workflow_structuring_quality_error(chunks: list[Any], warnings: list[str]) -> str:
    warning_set = set(warnings)
    synthesized_required_layers = {
        "full_sop_missing_from_model_synthesized_for_review",
        "workflow_graph_missing_from_model_synthesized_for_review",
    }
    if warning_set & synthesized_required_layers:
        return ",".join(sorted(warning_set & synthesized_required_layers))

    unit_types = {str(chunk.metadata.get("unit_type") or chunk.section or "") for chunk in chunks}
    if "full_sop" not in unit_types:
        return "missing_full_sop"
    if "workflow_graph" not in unit_types:
        return "missing_workflow_graph"

    atomic_count = sum(
        1
        for chunk in chunks
        if str(chunk.metadata.get("retrieval_scope") or "") == "unit"
        and str(chunk.metadata.get("unit_type") or chunk.section or "") not in {"full_sop", "workflow_graph"}
    )
    if atomic_count == 0:
        return "missing_atomic_workflow_units"

    return ""


def semantic_workflow_structured_chunks(filename: str, raw_text: str, classification: Any, semantic_refinement: dict[str, Any]) -> list[Any]:
    if not semantic_refinement:
        return []
    from app.text_processing import Chunk

    graph_candidate = semantic_refinement.get("workflow_graph_candidate") if isinstance(semantic_refinement.get("workflow_graph_candidate"), dict) else {}
    nodes = graph_candidate.get("nodes") if isinstance(graph_candidate.get("nodes"), list) else []
    if not nodes:
        return []

    chunks: list[Any] = []
    graph_refs = graph_candidate.get("source_refs") if isinstance(graph_candidate.get("source_refs"), list) else []
    full_sop_content = raw_text[:30000] or semantic_workflow_graph_summary(graph_candidate)
    chunks.append(
        Chunk(
            chunk_index=len(chunks),
            section="full_sop",
            heading=path_title(filename),
            content=full_sop_content,
            token_count=len(tokenize(full_sop_content)),
            metadata={
                "unit_type": "full_sop",
                "retrieval_scope": "document",
                "source_refs": graph_refs or [default_pdf_source_ref(filename)],
                "source_ref_quality": source_ref_quality_from_refs(graph_refs or [default_pdf_source_ref(filename)]),
                "requires_human_review": True,
                "confidence": min(float(getattr(classification, "confidence", 0.78) or 0.78), 0.78),
            },
        )
    )
    graph_content = semantic_workflow_graph_summary(graph_candidate)
    validation_errors = graph_candidate.get("validation_errors") if isinstance(graph_candidate.get("validation_errors"), list) else semantic_refinement.get("validation_errors", [])
    uncertain_edges = graph_candidate.get("uncertain_edges") if isinstance(graph_candidate.get("uncertain_edges"), list) else []
    chunks.append(
        Chunk(
            chunk_index=len(chunks),
            section="workflow_graph",
            heading=str(graph_candidate.get("title") or path_title(filename)),
            content=graph_content,
            token_count=len(tokenize(graph_content)),
            metadata={
                "unit_type": "workflow_graph",
                "retrieval_scope": "graph",
                "workflow_graph": graph_candidate,
                "graph_confidence": graph_candidate.get("graph_confidence"),
                "requires_human_review": True,
                "review_reason": graph_candidate.get("review_reason") or "Semantic workflow graph was normalized from visual candidates and requires manual topology review.",
                "annotations": graph_candidate.get("annotations", []),
                "uncertain_edges": uncertain_edges,
                "uncertain_edges_count": len(uncertain_edges),
                "graph_validation_errors": validation_errors,
                "graph_validation_error_count": len(validation_errors),
                "topology_review_required": graph_candidate.get("topology_review_required", True),
                "graph_extraction_status": "semantic_workflow_graph_candidate_needs_review",
                "source_refs": graph_refs or [default_pdf_source_ref(filename)],
                "source_ref_quality": source_ref_quality_from_refs(graph_refs or [default_pdf_source_ref(filename)]),
                "source_ref_acknowledged": False,
                "confidence": min(float(graph_candidate.get("graph_confidence") or 0.62), 0.78),
            },
        )
    )

    pages = semantic_refinement.get("pages") if isinstance(semantic_refinement.get("pages"), list) else []
    for page in pages:
        if not isinstance(page, dict):
            continue
        for node in [*(page.get("semantic_nodes") or []), *(page.get("annotations") or [])]:
            if not isinstance(node, dict):
                continue
            semantic_type = str(node.get("semantic_node_type") or "action")
            if semantic_type in {"start", "end"}:
                continue
            unit_type = SEMANTIC_CANDIDATE_UNIT_TYPES.get(semantic_type, "candidate_action")
            title = str(node.get("title") or node.get("content") or unit_type).strip()
            content = str(node.get("content") or title).strip()
            if not content:
                continue
            node_refs = node.get("source_refs") if isinstance(node.get("source_refs"), list) else []
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    section=unit_type,
                    heading=candidate_heading(title, unit_type, len(chunks) + 1),
                    content=content,
                    token_count=len(tokenize(content)),
                    metadata={
                        "unit_type": unit_type,
                        "retrieval_scope": "unit",
                        "semantic_node_id": node.get("id"),
                        "semantic_node_type": semantic_type,
                        "dedupe_status": node.get("dedupe_status", "unique"),
                        "attached_to_node_id": node.get("attached_to_node_id", ""),
                        "attached_annotations": node.get("attached_annotations", []),
                        "graph_confidence": graph_candidate.get("graph_confidence"),
                        "topology_review_required": graph_candidate.get("topology_review_required", True),
                        "graph_extraction_status": "semantic_workflow_refinement_needs_review",
                        "source_refs": node_refs or [default_pdf_source_ref(filename)],
                        "source_ref_quality": source_ref_quality_from_refs(node_refs or [default_pdf_source_ref(filename)]),
                        "source_ref_acknowledged": False,
                        "confidence": 0.62,
                    },
                )
            )
    return chunks[:100]


def enrich_workflow_units_with_semantic_refinement(units: list[dict[str, Any]], semantic_refinement: dict[str, Any]) -> list[dict[str, Any]]:
    semantic_nodes = semantic_nodes_for_enrichment(semantic_refinement)
    if not semantic_nodes:
        return units
    output: list[dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, dict):
            output.append(unit)
            continue
        metadata = dict(unit.get("metadata") or {})
        unit_type = str(unit.get("unit_type") or metadata.get("unit_type") or "")
        graph = metadata.get("workflow_graph") if isinstance(metadata.get("workflow_graph"), dict) else None
        if unit_type != "workflow_graph" or not graph:
            output.append(unit)
            continue
        enriched_graph, enriched_count = enrich_workflow_graph_nodes(graph, semantic_nodes)
        if enriched_count:
            metadata = {
                **metadata,
                "workflow_graph": enriched_graph,
                "semantic_refinement_enriched_node_count": enriched_count,
            }
            output.append(
                {
                    **unit,
                    "content": semantic_workflow_graph_summary(enriched_graph),
                    "metadata": metadata,
                }
            )
        else:
            output.append(unit)
    return output


def semantic_nodes_for_enrichment(semantic_refinement: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    graph_candidate = semantic_refinement.get("workflow_graph_candidate") if isinstance(semantic_refinement.get("workflow_graph_candidate"), dict) else {}
    for node in graph_candidate.get("nodes", []) if isinstance(graph_candidate.get("nodes"), list) else []:
        if isinstance(node, dict):
            nodes.append(node)
    for page in semantic_refinement.get("pages", []) if isinstance(semantic_refinement.get("pages"), list) else []:
        if not isinstance(page, dict):
            continue
        for node in page.get("semantic_nodes", []) if isinstance(page.get("semantic_nodes"), list) else []:
            if isinstance(node, dict):
                nodes.append(node)
    deduped: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        key = node_id or semantic_text_key(str(node.get("content") or node.get("question") or node.get("title") or ""))
        if not key:
            continue
        existing = deduped.get(key)
        if not existing or len(str(node.get("content") or "")) > len(str(existing.get("content") or "")):
            deduped[key] = node
    return list(deduped.values())


def enrich_workflow_graph_nodes(graph: dict[str, Any], semantic_nodes: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    if not nodes:
        return graph, 0
    enriched_nodes: list[dict[str, Any]] = []
    used_semantic_ids: set[str] = set()
    enriched_count = 0
    for node in nodes:
        if not isinstance(node, dict):
            enriched_nodes.append(node)
            continue
        semantic_node = match_semantic_node_for_graph_node(node, semantic_nodes, used_semantic_ids)
        if semantic_node:
            used_semantic_ids.add(str(semantic_node.get("id") or ""))
            merged = merge_graph_node_with_semantic_node(node, semantic_node)
            enriched_count += int(merged != node)
            enriched_nodes.append(merged)
        else:
            enriched_nodes.append(node)
    return {**graph, "nodes": enriched_nodes}, enriched_count


def match_semantic_node_for_graph_node(node: dict[str, Any], semantic_nodes: list[dict[str, Any]], used_ids: set[str]) -> dict[str, Any] | None:
    node_id = str(node.get("id") or "").strip()
    if node_id:
        direct = next((item for item in semantic_nodes if str(item.get("id") or "") == node_id), None)
        if direct:
            return direct
    node_text = " ".join(str(node.get(key) or "") for key in ("id", "title", "question", "content"))
    node_code = workflow_step_code(node_text)
    node_type = str(node.get("semantic_node_type") or node.get("type") or "")
    if node_code:
        candidates = [
            item for item in semantic_nodes
            if workflow_step_code(str(item.get("content") or item.get("question") or item.get("title") or "")) == node_code
        ]
        if candidates:
            candidates.sort(
                key=lambda item: (
                    str(item.get("id") or "") in used_ids,
                    not compatible_graph_semantic_type(node_type, str(item.get("semantic_node_type") or item.get("type") or "")),
                    -len(str(item.get("content") or "")),
                )
            )
            return candidates[0]
    node_key = semantic_text_key(node_text)
    if not node_key:
        return None
    best: tuple[float, dict[str, Any]] | None = None
    for item in semantic_nodes:
        item_text = str(item.get("content") or item.get("question") or item.get("title") or "")
        item_key = semantic_text_key(item_text)
        if not item_key:
            continue
        score = max(SequenceMatcher(None, node_key, item_key).ratio(), token_containment(node_key, item_key))
        if score < 0.72:
            continue
        if not best or score > best[0]:
            best = (score, item)
    return best[1] if best else None


def workflow_step_code(text: str) -> str:
    match = re.search(r"\b(\d+(?:\.\d+)*)[.)]?\s+", str(text or ""))
    return match.group(1) if match else ""


def compatible_graph_semantic_type(graph_type: str, semantic_type: str) -> bool:
    if not graph_type or not semantic_type:
        return True
    if graph_type == semantic_type:
        return True
    if graph_type == "action" and semantic_type in GRAPH_SEMANTIC_NODE_TYPES - {"decision", "start", "end"}:
        return True
    return graph_type == "decision" and semantic_type == "decision"


def merge_graph_node_with_semantic_node(node: dict[str, Any], semantic_node: dict[str, Any]) -> dict[str, Any]:
    semantic_content = str(semantic_node.get("content") or semantic_node.get("question") or semantic_node.get("title") or "").strip()
    node_content = str(node.get("content") or "").strip()
    content = semantic_content if len(semantic_content) > len(node_content) else node_content
    semantic_type = str(semantic_node.get("semantic_node_type") or node.get("semantic_node_type") or "")
    graph_type = graph_node_type_for_semantic(semantic_type) if semantic_type else str(node.get("type") or "action")
    question = normalize_decision_question(content) if graph_type == "decision" else str(node.get("question") or "").strip()
    title = str(node.get("title") or "").strip()
    if not title or len(semantic_title(content)) > len(title):
        title = semantic_title(content)
    source_refs = node.get("source_refs") if isinstance(node.get("source_refs"), list) and node.get("source_refs") else semantic_node.get("source_refs", [])
    return {
        **node,
        "type": graph_type,
        "semantic_node_type": semantic_type or node.get("semantic_node_type", ""),
        "title": title[:240] or semantic_title(content),
        "content": content,
        "question": question,
        "actor": node.get("actor") or semantic_node.get("actor") or infer_workflow_actor(content),
        "source_refs": source_refs,
        "bbox": node.get("bbox") or semantic_node.get("bbox", []),
        "page": node.get("page") or semantic_node.get("page"),
        "dedupe_status": node.get("dedupe_status") or semantic_node.get("dedupe_status", "unique"),
        "attached_annotations": node.get("attached_annotations") or semantic_node.get("attached_annotations", []),
    }


def build_degraded_draft(
    *,
    filename: str,
    content_type: str,
    raw_text: str,
    classification: Any,
    blocks: list[dict[str, Any]],
    raw_context: dict[str, Any],
    ai_error: str,
) -> list[Any]:
    if classification.document_type == "policy_table":
        return build_degraded_spreadsheet_draft(filename, raw_text, blocks, classification, ai_error)
    if classification.document_type == "workflow_diagram":
        return build_degraded_workflow_draft(filename, raw_text, blocks, raw_context, classification, ai_error)
    if classification.document_type == "policy_rule":
        return build_degraded_policy_text_draft(filename, content_type, raw_text, blocks, classification, ai_error)
    return mark_degraded_chunks(
        chunk_text(raw_text),
        classification,
        ai_error,
        "generic_degraded_chunking",
        "degraded_structured_draft",
    )


def build_degraded_policy_text_draft(filename: str, content_type: str, raw_text: str, blocks: list[dict[str, Any]], classification: Any, ai_error: str) -> list[Any]:
    chunks: list[Any] = [
        degraded_chunk(
            0,
            "full_sop",
            path_title(filename),
            raw_text[:30000],
            {
                "unit_type": "full_sop",
                "retrieval_scope": "document",
                "source_refs": [source_ref_for_text_block(filename, content_type, blocks, 0, 0, raw_text)],
            },
            classification,
            ai_error,
        )
    ]
    paragraph_groups = paragraph_groups_from_blocks(blocks)
    for group_index, group in enumerate(paragraph_groups, start=1):
        text = "\n".join(item["text"] for item in group).strip()
        if not text:
            continue
        unit_type = "candidate_section"
        has_warning = contains_signal(text, WARNING_SIGNALS)
        has_rule = contains_signal(text, CONDITION_ACTION_SIGNALS)
        if starts_warning_block(text):
            unit_type = "candidate_warning"
        elif has_rule:
            unit_type = "candidate_rule"
        elif has_warning:
            unit_type = "candidate_warning"
        heading = candidate_heading(text, unit_type, group_index)
        chunks.append(
            degraded_chunk(
                len(chunks),
                unit_type,
                heading,
                text,
                {
                    "unit_type": unit_type,
                    "retrieval_scope": "unit",
                    "inline_warning": has_warning and unit_type != "candidate_warning",
                    "source_refs": [source_ref_for_text_block(filename, content_type, blocks, group[0]["index"], group[-1]["index"], text)],
                },
                classification,
                ai_error,
            )
        )
    return chunks


def build_degraded_spreadsheet_draft(filename: str, raw_text: str, blocks: list[dict[str, Any]], classification: Any, ai_error: str) -> list[Any]:
    chunks: list[Any] = []
    sheets = [(block["sheet"], block.get("rows", [])) for block in blocks if block.get("type") == "sheet"]
    summary = "\n".join(f"- {sheet_name}: {len(rows)} non-empty rows" for sheet_name, rows in sheets) or raw_text[:2000]
    chunks.append(
        degraded_chunk(
            0,
            "full_sop",
            path_title(filename),
            f"Workbook extracted for review.\n{summary}",
            {
                "unit_type": "full_sop",
                "retrieval_scope": "document",
                "source_refs": [{"source_type": "excel", "source_file": filename, "sheet": sheets[0][0] if sheets else "", "row_start": 1, "row_end": 1}],
                "source_ref_quality": "sheet_row",
            },
            classification,
            ai_error,
        )
    )
    for sheet_name, rows in sheets:
        headers = first_header_row(rows)
        scope = version_scope_from_sheet(sheet_name)
        effective_from = effective_from_from_sheet(sheet_name)
        for row_number, values in rows:
            if row_is_header(values, headers):
                continue
            content = row_content(values, headers)
            if not content:
                continue
            chunks.append(
                degraded_chunk(
                    len(chunks),
                    "candidate_table_row",
                    f"{sheet_name} dòng {row_number}",
                    content,
                    {
                        "unit_type": "candidate_table_row",
                        "retrieval_scope": "unit",
                        "sheet_name": sheet_name,
                        "row_number": row_number,
                        "headers": headers,
                        "effective_from": effective_from,
                        "version_scope": scope,
                        "historical_sheets": scope == "historical_candidate",
                        "source_ref_quality": "sheet_row",
                        "source_ref_acknowledged": True,
                        "source_refs": [{"source_type": "excel", "source_file": filename, "sheet": sheet_name, "row_start": row_number, "row_end": row_number, "column_names": headers}],
                    },
                    classification,
                    ai_error,
                )
        )
    return chunks


GRAPH_SEMANTIC_NODE_TYPES = {"start", "end", "action", "decision", "queue_rule", "sla_rule"}
ANNOTATION_SEMANTIC_NODE_TYPES = {"annotation", "warning", "audit_rule", "macro_script"}
WORKFLOW_EDGE_CONDITIONS = {"yes", "no", "next", "timeout", "escalation", "fallback", "handoff", "return", "retry"}
SEMANTIC_CANDIDATE_UNIT_TYPES = {
    "start": "candidate_action",
    "end": "candidate_action",
    "action": "candidate_action",
    "decision": "candidate_decision",
    "annotation": "candidate_annotation",
    "warning": "candidate_warning",
    "sla_rule": "candidate_sla",
    "audit_rule": "candidate_audit_rule",
    "queue_rule": "candidate_queue_rule",
    "macro_script": "macro_script",
}


def build_workflow_semantic_refinement(
    *,
    filename: str,
    visual_layout: dict[str, Any],
    source_blocks: list[dict[str, Any]],
    classification: Any,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    all_graph_nodes: list[dict[str, Any]] = []
    all_annotations: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    all_uncertain_edges: list[dict[str, Any]] = []
    all_validation_errors: list[str] = []
    raw_node_count = 0
    deduped_count = 0

    for page in visual_layout.get("pages", []) if isinstance(visual_layout.get("pages"), list) else []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page") or 1)
        graph = page.get("graph_candidate") if isinstance(page.get("graph_candidate"), dict) else {}
        raw_nodes = semantic_nodes_from_visual_page(filename, page, graph)
        raw_nodes.extend(semantic_nodes_from_visual_text_blocks(filename, page, raw_nodes))
        raw_nodes.extend(semantic_annotations_from_visual_text_blocks(filename, page, raw_nodes))
        raw_node_count += len(raw_nodes)

        semantic_nodes, id_map, page_deduped_count = dedupe_semantic_nodes(raw_nodes)
        deduped_count += page_deduped_count
        attach_semantic_annotations(semantic_nodes)

        edges, uncertain_edges, edge_warnings = normalize_semantic_edges(graph, semantic_nodes, id_map, filename, page_number)
        graph_nodes = [node for node in semantic_nodes if node["semantic_node_type"] in GRAPH_SEMANTIC_NODE_TYPES]
        annotations = [node for node in semantic_nodes if node["semantic_node_type"] in ANNOTATION_SEMANTIC_NODE_TYPES]
        page_payload = {
            "page": page_number,
            "image_size": page.get("image_size", []),
            "semantic_nodes": [public_semantic_node(node) for node in graph_nodes],
            "annotations": [public_semantic_node(node) for node in annotations],
            "edges": edges,
            "uncertain_edges": uncertain_edges,
            "deduped_count": page_deduped_count,
            "warnings": edge_warnings,
        }
        page_errors = validate_semantic_page(page_payload)
        page_payload["validation_errors"] = page_errors
        pages.append(page_payload)
        all_graph_nodes.extend(graph_nodes)
        all_annotations.extend(annotations)
        all_edges.extend(edges)
        all_uncertain_edges.extend(uncertain_edges)
        all_validation_errors.extend(page_errors)

    graph_candidate = build_semantic_workflow_graph_candidate(
        filename=filename,
        title=path_title(filename),
        nodes=all_graph_nodes,
        annotations=all_annotations,
        edges=all_edges,
        uncertain_edges=all_uncertain_edges,
        visual_layout=visual_layout,
    )
    graph_errors = validate_semantic_workflow_graph_candidate(graph_candidate)
    all_validation_errors.extend(graph_errors)

    semantic_node_count = len(all_graph_nodes) + len(all_annotations)
    topology_review_required = bool(all_uncertain_edges or graph_errors or deduped_count)
    graph_confidence = semantic_graph_confidence(
        visual_layout.get("summary") if isinstance(visual_layout.get("summary"), dict) else {},
        semantic_node_count,
        len(all_edges),
        len(all_uncertain_edges),
        all_validation_errors,
    )
    graph_candidate["graph_confidence"] = graph_confidence
    graph_candidate["topology_review_required"] = topology_review_required
    graph_candidate["validation_errors"] = list(dict.fromkeys(all_validation_errors))

    return {
        "source_type": "workflow_semantic_refinement",
        "filename": filename,
        "document_type": classification.document_type,
        "source_type_document": classification.source_type,
        "summary": {
            "raw_visual_node_count": raw_node_count,
            "semantic_node_count": semantic_node_count,
            "workflow_node_count": len(all_graph_nodes),
            "annotation_count": len(all_annotations),
            "deduped_count": deduped_count,
            "confirmed_edge_count": len(all_edges),
            "uncertain_edge_count": len(all_uncertain_edges),
            "graph_confidence": graph_confidence,
            "topology_review_required": topology_review_required,
            "topology_source": "visual_connector_candidates_only",
            "source_block_count": len(source_blocks),
        },
        "pages": pages,
        "workflow_graph_candidate": graph_candidate,
        "validation_errors": list(dict.fromkeys(all_validation_errors)),
        "rules": [
            "Semantic nodes are derived from visual candidates and bbox/layout evidence.",
            "Graph edges are derived only from visual connector candidates, never raw OCR text order.",
            "Annotation, warning, audit, and macro/script blocks cannot have outgoing workflow edges.",
            "Uncertain topology must be reviewed manually before publish.",
        ],
    }


def semantic_nodes_from_visual_page(filename: str, page: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    page_number = int(page.get("page") or 1)
    for index, node in enumerate(graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else [], start=1):
        if not isinstance(node, dict):
            continue
        text = str(node.get("title") or node.get("text") or "").strip()
        if not text:
            continue
        bbox = normalize_bbox_list(node.get("bbox"))
        semantic_type = classify_semantic_node_type(text, str(node.get("type") or "action"))
        semantic_id = f"sem_{node.get('id') or f'p{page_number}_node_{index}'}"
        source_ref = {"source_type": "pdf_diagram", "source_file": filename, "page": page_number, "bbox": bbox}
        output.append(
            {
                "id": semantic_id,
                "page": page_number,
                "title": semantic_title(text),
                "content": text,
                "text_key": semantic_text_key(text),
                "semantic_node_type": semantic_type,
                "graph_node_type": graph_node_type_for_semantic(semantic_type),
                "actor": infer_workflow_actor(text),
                "bbox": bbox,
                "confidence": float(node.get("confidence") or 0.55),
                "source_refs": [source_ref],
                "source_node_ids": [str(node.get("id") or semantic_id)],
                "visual_node_type": str(node.get("type") or ""),
                "dedupe_status": "unique",
                "attached_annotations": [],
            }
        )
    return output


def semantic_nodes_from_visual_text_blocks(filename: str, page: dict[str, Any], existing_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    page_number = int(page.get("page") or 1)
    existing_keys = {node.get("text_key") for node in existing_nodes}
    for group in workflow_text_groups_from_visual_blocks(page.get("text_blocks", [])):
        text = str(group.get("text") or "").strip()
        if not text:
            continue
        key = semantic_text_key(text)
        if key in existing_keys:
            continue
        semantic_type = classify_semantic_node_type(text, "decision" if is_decision_text(text) else "action")
        if semantic_type in ANNOTATION_SEMANTIC_NODE_TYPES:
            continue
        bbox = normalize_bbox_list(group.get("bbox"))
        semantic_id = f"sem_{group.get('id') or f'p{page_number}_text_node_{len(output) + 1}'}"
        output.append(
            {
                "id": semantic_id,
                "page": page_number,
                "title": semantic_title(text),
                "content": text,
                "text_key": key,
                "semantic_node_type": semantic_type,
                "graph_node_type": graph_node_type_for_semantic(semantic_type),
                "actor": infer_workflow_actor(text),
                "bbox": bbox,
                "confidence": 0.56,
                "source_refs": [{"source_type": "pdf_diagram", "source_file": filename, "page": page_number, "bbox": bbox}],
                "source_node_ids": list(group.get("source_text_ids") or [str(group.get("id") or semantic_id)]),
                "visual_node_type": "text_block_backfill",
                "dedupe_status": "unique",
                "attached_annotations": [],
            }
        )
    return output


def workflow_text_groups_from_visual_blocks(text_blocks: Any) -> list[dict[str, Any]]:
    if not isinstance(text_blocks, list):
        return []
    blocks = [
        block for block in text_blocks
        if isinstance(block, dict)
        and str(block.get("text") or "").strip()
        and len(normalize_bbox_list(block.get("bbox"))) == 4
    ]
    blocks.sort(key=lambda block: (normalize_bbox_list(block.get("bbox"))[1], normalize_bbox_list(block.get("bbox"))[0]))
    groups: list[dict[str, Any]] = []
    for block in blocks:
        start_text = str(block.get("text") or "").strip()
        if not is_numbered_workflow_step(start_text):
            continue
        start_bbox = normalize_bbox_list(block.get("bbox"))
        group_blocks = [block]
        group_bbox = start_bbox
        last_bottom = start_bbox[3]
        for candidate in blocks:
            if candidate is block:
                continue
            candidate_bbox = normalize_bbox_list(candidate.get("bbox"))
            candidate_text = str(candidate.get("text") or "").strip()
            if candidate_bbox[1] < start_bbox[1] - 2:
                continue
            if candidate_bbox[1] > start_bbox[1] + 220:
                break
            if candidate_bbox[1] <= start_bbox[1] + 2 and candidate_bbox[0] <= start_bbox[0]:
                continue
            if is_visual_workflow_noise(candidate_text):
                continue
            vertical_gap = candidate_bbox[1] - last_bottom
            if vertical_gap > 38 and len(group_blocks) > 1:
                break
            if is_numbered_workflow_step(candidate_text):
                if horizontally_related_text_block(group_bbox, candidate_bbox) and candidate_bbox[1] > start_bbox[1] + 8:
                    break
                continue
            if not horizontally_related_text_block(group_bbox, candidate_bbox):
                continue
            if vertical_gap > 46:
                continue
            group_blocks.append(candidate)
            group_bbox = union_bboxes([group_bbox, candidate_bbox])
            last_bottom = max(last_bottom, candidate_bbox[3])
        text = "\n".join(str(item.get("text") or "").strip() for item in group_blocks if str(item.get("text") or "").strip())
        groups.append(
            {
                "id": f"{block.get('id') or 'text'}_group",
                "page": block.get("page"),
                "text": text,
                "bbox": group_bbox,
                "source_text_ids": [str(item.get("id") or "") for item in group_blocks if item.get("id")],
            }
        )
    return groups


def is_visual_workflow_noise(text: str) -> bool:
    normalized = normalized_search_text(text)
    line_keys = {normalized_search_text(line) for line in str(text or "").splitlines() if line.strip()}
    stripped = text.strip().lower()
    if not normalized:
        return True
    if normalized in {"yes", "no", "co", "khong", "khach hang", "cs a", "cs b", "cs l2", "cs layer2", "msc", "end"}:
        return True
    if line_keys & {"yes", "no", "co", "khong"}:
        return True
    return bool(re.match(r"^\([a-z]\)$", stripped))


def horizontally_related_text_block(group_bbox: list[float], block_bbox: list[float]) -> bool:
    if len(group_bbox) != 4 or len(block_bbox) != 4:
        return False
    overlap = max(0.0, min(group_bbox[2], block_bbox[2]) - max(group_bbox[0], block_bbox[0]))
    min_width = max(1.0, min(group_bbox[2] - group_bbox[0], block_bbox[2] - block_bbox[0]))
    center_distance = abs(((group_bbox[0] + group_bbox[2]) / 2) - ((block_bbox[0] + block_bbox[2]) / 2))
    return overlap / min_width > 0.35 or center_distance < max(120.0, (group_bbox[2] - group_bbox[0]) * 0.75)


def semantic_annotations_from_visual_text_blocks(filename: str, page: dict[str, Any], existing_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    page_number = int(page.get("page") or 1)
    existing_keys = {node.get("text_key") for node in existing_nodes}
    for block in page.get("text_blocks", []) if isinstance(page.get("text_blocks"), list) else []:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        if not text or not is_annotation_like_text(text):
            continue
        key = semantic_text_key(text)
        if key in existing_keys:
            continue
        bbox = normalize_bbox_list(block.get("bbox"))
        semantic_type = classify_semantic_node_type(text, "annotation")
        if semantic_type not in ANNOTATION_SEMANTIC_NODE_TYPES:
            semantic_type = "annotation"
        semantic_id = f"sem_{block.get('id') or f'p{page_number}_annotation_{len(output) + 1}'}"
        output.append(
            {
                "id": semantic_id,
                "page": page_number,
                "title": semantic_title(text),
                "content": text,
                "text_key": key,
                "semantic_node_type": semantic_type,
                "graph_node_type": "annotation",
                "actor": infer_workflow_actor(text),
                "bbox": bbox,
                "confidence": 0.58,
                "source_refs": [{"source_type": "pdf_diagram", "source_file": filename, "page": page_number, "bbox": bbox}],
                "source_node_ids": [str(block.get("id") or semantic_id)],
                "visual_node_type": "text_block",
                "dedupe_status": "unique",
                "attached_annotations": [],
            }
        )
    return output


def classify_semantic_node_type(text: str, visual_type: str) -> str:
    normalized = normalized_search_text(text)
    stripped = text.strip()
    visual_type = visual_type.lower()
    if visual_type == "decision" or is_decision_text(stripped):
        return "decision"
    if normalized == "end":
        return "end"
    if visual_type == "start" and not is_numbered_workflow_step(stripped):
        return "start"
    if visual_type == "end" and not is_numbered_workflow_step(stripped):
        return "end"
    if is_numbered_workflow_step(stripped):
        if is_queue_text(normalized):
            return "queue_rule"
        if is_sla_text(normalized):
            return "sla_rule"
    if is_audit_text(normalized):
        return "audit_rule"
    if is_warning_text(normalized):
        return "warning"
    if is_macro_text(normalized):
        return "macro_script"
    if is_annotation_like_text(text):
        return "annotation"
    if is_queue_text(normalized):
        return "queue_rule"
    if is_sla_text(normalized):
        return "sla_rule"
    return "action"


def is_decision_text(text: str) -> bool:
    normalized = normalized_search_text(text)
    return "?" in text or " hay khong" in normalized


def is_numbered_workflow_step(text: str) -> bool:
    return bool(re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+", text))


def is_annotation_like_text(text: str) -> bool:
    normalized = normalized_search_text(text)
    stripped = text.strip().lower()
    return (
        stripped.startswith(("(a)", "(b)", "(c)", "(*)", "(**)"))
        or normalized.startswith(("luu y", "ghi chu", "note"))
        or "quy dinh note" in normalized
        or "quy dinh audit" in normalized
        or "zt" in normalized
        or bool(re.search(r"\bscript\b", normalized))
    )


def is_audit_text(normalized: str) -> bool:
    return "quy dinh audit" in normalized or "audit" in normalized or "zt" in normalized


def is_warning_text(normalized: str) -> bool:
    return any(signal in normalized for signal in ["canh bao", "rủi ro", "rui ro", "loi zt", "khong duoc"])


def is_macro_text(normalized: str) -> bool:
    return bool(re.search(r"\b(script|macro)\b", normalized)) or "noi dung phan hoi" in normalized


def is_queue_text(normalized: str) -> bool:
    return "queue" in normalized or "food order issue" in normalized or "all staff" in normalized


def is_sla_text(normalized: str) -> bool:
    return "sla" in normalized or "tre nhat" in normalized or bool(re.search(r"\b\d+\s*(phut|gio)\b", normalized))


def graph_node_type_for_semantic(semantic_type: str) -> str:
    if semantic_type == "decision":
        return "decision"
    if semantic_type in {"start", "end"}:
        return semantic_type
    if semantic_type in GRAPH_SEMANTIC_NODE_TYPES:
        return "action"
    return "annotation"


def infer_workflow_actor(text: str) -> str:
    upper = text.upper()
    if "CS_L2" in upper or re.search(r"\bL2\b", upper):
        return "CS_L2"
    if "CS_A" in upper:
        return "CS_A"
    if "CS_B" in upper:
        return "CS_B"
    if "MSC" in upper:
        return "MSC"
    if "KHÁCH HÀNG" in upper or re.search(r"\bKH\b", upper):
        return "KH"
    if "CS" in upper:
        return "CS"
    return ""


def semantic_title(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    question_index = next((index for index in range(len(lines) - 1, -1, -1) if "?" in lines[index]), -1)
    if question_index >= 0:
        start_index = question_index
        for index in range(question_index, -1, -1):
            if re.match(r"^\d+(?:\.\d+)*[.)]?\s+", lines[index]):
                start_index = index
                break
        question_title = " ".join(line for line in lines[start_index:question_index + 1] if normalized_search_text(line) not in {"yes", "no"}).strip()
        if question_title:
            return question_title[:180]
    lines = [line for line in lines if normalized_search_text(line) not in {"yes", "no"}]
    first_line = lines[0] if lines else text.strip()
    return first_line[:180] or "Workflow semantic node"


def semantic_text_key(text: str) -> str:
    return normalized_search_text(re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", text))


def normalize_bbox_list(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        return []
    output: list[float] = []
    for item in value:
        try:
            output.append(float(item))
        except (TypeError, ValueError):
            return []
    return output


def dedupe_semantic_nodes(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    output: list[dict[str, Any]] = []
    id_map: dict[str, str] = {}
    deduped_count = 0
    for node in nodes:
        existing_index = next((index for index, existing in enumerate(output) if should_merge_semantic_nodes(existing, node)), None)
        if existing_index is None:
            output.append(node)
            id_map[node["id"]] = node["id"]
            for source_id in node.get("source_node_ids", []):
                id_map[str(source_id)] = node["id"]
            continue
        merged = merge_semantic_nodes(output[existing_index], node)
        output[existing_index] = merged
        id_map[node["id"]] = merged["id"]
        for source_id in node.get("source_node_ids", []):
            id_map[str(source_id)] = merged["id"]
        deduped_count += 1
    return output, id_map, deduped_count


def should_merge_semantic_nodes(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if int(left.get("page") or 0) != int(right.get("page") or 0):
        return False
    if not compatible_semantic_types(str(left.get("semantic_node_type") or ""), str(right.get("semantic_node_type") or "")):
        return False
    left_text = str(left.get("text_key") or "")
    right_text = str(right.get("text_key") or "")
    if not left_text or not right_text:
        return False
    left_code = workflow_step_code(str(left.get("content") or left.get("title") or ""))
    right_code = workflow_step_code(str(right.get("content") or right.get("title") or ""))
    if left_code and right_code and left_code != right_code:
        return False
    text_similarity = max(SequenceMatcher(None, left_text, right_text).ratio(), token_jaccard(left_text, right_text))
    text_containment = token_containment(left_text, right_text)
    left_bbox = left.get("bbox") if isinstance(left.get("bbox"), list) else []
    right_bbox = right.get("bbox") if isinstance(right.get("bbox"), list) else []
    overlap = bbox_overlap_strength(left_bbox, right_bbox)
    distance = bbox_distance(left_bbox, right_bbox) if len(left_bbox) == 4 and len(right_bbox) == 4 else 99999.0
    if left_code and left_code == right_code and text_containment > 0.62 and distance < 450:
        return True
    if overlap > 0.25 and text_containment > 0.72:
        return True
    if (left_text.startswith(right_text) or right_text.startswith(left_text)) and overlap > 0.2:
        return True
    if overlap > 0.35 and text_similarity > 0.68:
        return True
    if text_similarity > 0.88 and distance < 380:
        return True
    if text_similarity > 0.96:
        return True
    return False


def compatible_semantic_types(left: str, right: str) -> bool:
    if left == right:
        return True
    graph_action_family = {"start", "end", "action", "queue_rule", "sla_rule"}
    annotation_family = {"annotation", "warning", "audit_rule", "macro_script"}
    return left in graph_action_family and right in graph_action_family or left in annotation_family and right in annotation_family


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def token_containment(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def bbox_overlap_strength(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return 0.0
    iou = iou_bbox(left, right)
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    min_area = min(max(1.0, (left[2] - left[0]) * (left[3] - left[1])), max(1.0, (right[2] - right[0]) * (right[3] - right[1])))
    return max(iou, intersection / min_area)


def merge_semantic_nodes(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_content = str(left.get("content") or "")
    right_content = str(right.get("content") or "")
    content = left_content if len(left_content) >= len(right_content) else right_content
    bboxes = [bbox for bbox in [left.get("bbox"), right.get("bbox")] if isinstance(bbox, list) and len(bbox) == 4]
    semantic_type = preferred_semantic_type(str(left.get("semantic_node_type") or ""), str(right.get("semantic_node_type") or ""))
    source_refs = [*(left.get("source_refs") or []), *(right.get("source_refs") or [])]
    source_node_ids = list(dict.fromkeys([*(left.get("source_node_ids") or []), *(right.get("source_node_ids") or [])]))
    return {
        **left,
        "title": semantic_title(content),
        "content": content,
        "text_key": semantic_text_key(content),
        "semantic_node_type": semantic_type,
        "graph_node_type": graph_node_type_for_semantic(semantic_type),
        "actor": left.get("actor") or right.get("actor") or infer_workflow_actor(content),
        "bbox": union_bboxes(bboxes) if bboxes else left.get("bbox", []),
        "confidence": max(float(left.get("confidence") or 0), float(right.get("confidence") or 0)),
        "source_refs": dedupe_source_refs(source_refs),
        "source_node_ids": source_node_ids,
        "dedupe_status": "merged",
        "merged_node_count": int(left.get("merged_node_count") or 1) + int(right.get("merged_node_count") or 1),
    }


def preferred_semantic_type(left: str, right: str) -> str:
    priority = {
        "decision": 90,
        "queue_rule": 80,
        "sla_rule": 70,
        "audit_rule": 68,
        "warning": 65,
        "macro_script": 62,
        "annotation": 60,
        "start": 55,
        "end": 55,
        "action": 50,
    }
    return left if priority.get(left, 0) >= priority.get(right, 0) else right


def dedupe_source_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        key = json.dumps(ref, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        output.append(ref)
    return output


def attach_semantic_annotations(nodes: list[dict[str, Any]]) -> None:
    graph_nodes = [node for node in nodes if node["semantic_node_type"] in GRAPH_SEMANTIC_NODE_TYPES]
    annotations = [node for node in nodes if node["semantic_node_type"] in ANNOTATION_SEMANTIC_NODE_TYPES]
    for annotation in annotations:
        target = nearest_semantic_node(annotation, graph_nodes)
        if not target:
            annotation["attached_to_node_id"] = ""
            annotation["orphan"] = True
            continue
        annotation["attached_to_node_id"] = target["id"]
        annotation["attached_to"] = target["id"]
        annotation["orphan"] = False
        target.setdefault("attached_annotations", []).append(annotation["id"])


def nearest_semantic_node(annotation: dict[str, Any], graph_nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [node for node in graph_nodes if int(node.get("page") or 0) == int(annotation.get("page") or 0)]
    if not candidates:
        return None
    bbox = annotation.get("bbox") if isinstance(annotation.get("bbox"), list) else []
    if len(bbox) != 4:
        return candidates[0]
    return sorted(
        candidates,
        key=lambda node: bbox_distance(bbox, node.get("bbox", [])) if isinstance(node.get("bbox"), list) and len(node.get("bbox", [])) == 4 else 99999.0,
    )[0]


def normalize_semantic_edges(
    graph: dict[str, Any],
    semantic_nodes: list[dict[str, Any]],
    id_map: dict[str, str],
    filename: str,
    page_number: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    semantic_by_id = {node["id"]: node for node in semantic_nodes}
    edges: list[dict[str, Any]] = []
    uncertain_edges: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in graph.get("edge_candidates", []) if isinstance(graph.get("edge_candidates"), list) else []:
        if not isinstance(edge, dict):
            continue
        from_id = id_map.get(str(edge.get("from_node") or ""), str(edge.get("from_node") or ""))
        to_id = id_map.get(str(edge.get("to_node") or ""), str(edge.get("to_node") or ""))
        from_node = semantic_by_id.get(from_id)
        to_node = semantic_by_id.get(to_id)
        if not from_node or not to_node or from_id == to_id:
            continue
        if from_node["semantic_node_type"] in ANNOTATION_SEMANTIC_NODE_TYPES or to_node["semantic_node_type"] in ANNOTATION_SEMANTIC_NODE_TYPES:
            warnings.append("annotation_edge_candidate_ignored")
            continue
        condition = normalize_edge_condition(str(edge.get("condition") or "next"))
        edge_key = (from_id, to_id, condition)
        if edge_key in seen:
            continue
        seen.add(edge_key)
        confidence = clamp_float(edge.get("confidence"), 0.0, 1.0, default=0.0)
        source_ref = {"source_type": "pdf_diagram", "source_file": filename, "page": page_number, "bbox": normalize_bbox_list(edge.get("bbox"))}
        payload = {
            "from_node": from_id,
            "to_node": to_id,
            "condition": condition,
            "confidence": confidence,
            "source_refs": [source_ref],
            "review_status": "needs_review",
            "direction_reason": str(edge.get("direction_reason") or ""),
        }
        if semantic_edge_is_confirmed(payload):
            edges.append(payload)
        else:
            uncertain_edges.append(
                {
                    **payload,
                    "reason": uncertain_edge_reason(payload),
                }
            )
    return edges, uncertain_edges, list(dict.fromkeys(warnings))


def semantic_edge_is_confirmed(edge: dict[str, Any]) -> bool:
    confidence = float(edge.get("confidence") or 0.0)
    direction_reason = str(edge.get("direction_reason") or "")
    condition = str(edge.get("condition") or "")
    if confidence >= 0.66 and "geometric_guess" not in direction_reason:
        return True
    return condition in {"yes", "no"} and confidence >= 0.7 and "geometric_guess" not in direction_reason


def uncertain_edge_reason(edge: dict[str, Any]) -> str:
    direction_reason = str(edge.get("direction_reason") or "visual_connector_low_confidence")
    confidence = float(edge.get("confidence") or 0.0)
    if confidence < 0.62:
        return "low_confidence_visual_connector"
    if "geometric_guess" in direction_reason:
        return "geometric_direction_needs_review"
    return "topology_needs_manual_review"


def normalize_edge_condition(value: str) -> str:
    normalized = normalized_search_text(value)
    if normalized in {"yes", "y", "co", "dung"}:
        return "yes"
    if normalized in {"no", "n", "khong", "sai"}:
        return "no"
    if any(signal in normalized for signal in ["qua han", "het han", "timeout"]):
        return "timeout"
    if any(signal in normalized for signal in ["escalation", "team lead", "msc"]):
        return "escalation"
    if any(signal in normalized for signal in ["handoff", "chuyen", "chia case"]):
        return "handoff"
    return normalized if normalized in WORKFLOW_EDGE_CONDITIONS else "next"


def clamp_float(value: Any, minimum: float, maximum: float, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def public_semantic_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "page": node.get("page"),
        "title": node.get("title"),
        "content": node.get("content"),
        "semantic_node_type": node.get("semantic_node_type"),
        "graph_node_type": node.get("graph_node_type"),
        "actor": node.get("actor", ""),
        "bbox": node.get("bbox", []),
        "source_refs": node.get("source_refs", []),
        "source_node_ids": node.get("source_node_ids", []),
        "dedupe_status": node.get("dedupe_status", "unique"),
        "attached_to_node_id": node.get("attached_to_node_id", ""),
        "attached_annotations": node.get("attached_annotations", []),
        "orphan": bool(node.get("orphan")),
        "confidence": node.get("confidence", 0.0),
    }


def build_semantic_workflow_graph_candidate(
    *,
    filename: str,
    title: str,
    nodes: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    uncertain_edges: list[dict[str, Any]],
    visual_layout: dict[str, Any],
) -> dict[str, Any]:
    graph_nodes = [workflow_graph_node_payload(node) for node in nodes]
    graph_annotations = [workflow_annotation_payload(node) for node in annotations]
    lanes = workflow_lanes_from_nodes(nodes)
    start_node_id = next((node["id"] for node in graph_nodes if node.get("type") == "start"), graph_nodes[0]["id"] if graph_nodes else "start")
    warnings = [annotation for annotation in graph_annotations if annotation.get("type") in {"warning", "audit_rule"}]
    summary = visual_layout.get("summary") if isinstance(visual_layout.get("summary"), dict) else {}
    graph_source_ref = workflow_graph_page_source_ref(filename, visual_layout)
    return {
        "workflow_id": normalized_key(title) or "workflow_graph",
        "title": title,
        "start_node_id": start_node_id,
        "lanes": lanes,
        "nodes": graph_nodes,
        "edges": [{key: edge[key] for key in ("from_node", "to_node", "condition") if key in edge} | {"source_refs": edge.get("source_refs", [])} for edge in edges],
        "annotations": graph_annotations,
        "warnings": warnings,
        "uncertain_edges": uncertain_edges,
        "graph_confidence": float(summary.get("confidence") or 0.0),
        "requires_human_review": True,
        "review_status": "needs_review",
        "review_reason": "Semantic workflow graph was normalized from visual candidates and requires manual topology review.",
        "topology_source": "visual_connector_candidates_only",
        "topology_review_required": True,
        "source_refs": [graph_source_ref],
    }


def workflow_graph_page_source_ref(filename: str, visual_layout: dict[str, Any]) -> dict[str, Any]:
    pages = visual_layout.get("pages") if isinstance(visual_layout.get("pages"), list) else []
    first_page = next((page for page in pages if isinstance(page, dict)), {})
    image_size = first_page.get("image_size") if isinstance(first_page.get("image_size"), list) else []
    bbox: list[float] = []
    if len(image_size) >= 2:
        try:
            bbox = [0.0, 0.0, float(image_size[0]), float(image_size[1])]
        except (TypeError, ValueError):
            bbox = []
    return {"source_type": "pdf_diagram", "source_file": filename, "page": int(first_page.get("page") or 1), "bbox": bbox}


def workflow_graph_node_payload(node: dict[str, Any]) -> dict[str, Any]:
    graph_type = graph_node_type_for_semantic(str(node.get("semantic_node_type") or "action"))
    title = str(node.get("title") or node.get("content") or "Workflow node").strip()
    content = str(node.get("content") or title).strip()
    question = normalize_decision_question(content) if graph_type == "decision" else ""
    return {
        "id": node["id"],
        "type": graph_type,
        "semantic_node_type": node.get("semantic_node_type"),
        "actor": node.get("actor", ""),
        "phase": "",
        "title": (question or title)[:240] if graph_type == "decision" else title[:240],
        "content": content,
        "question": question,
        "source_refs": node.get("source_refs", []),
        "attached_annotations": node.get("attached_annotations", []),
        "dedupe_status": node.get("dedupe_status", "unique"),
        "bbox": node.get("bbox", []),
        "page": node.get("page"),
    }


def normalize_decision_question(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    question_index = next((index for index in range(len(lines) - 1, -1, -1) if "?" in lines[index]), -1)
    if question_index >= 0:
        start_index = question_index
        for index in range(question_index, -1, -1):
            if re.match(r"^\d+(?:\.\d+)*[.)]?\s+", lines[index]):
                start_index = index
                break
        lines = lines[start_index:question_index + 1]
    lines = [line for line in lines if normalized_search_text(line) not in {"yes", "no"}]
    cleaned = re.sub(r"\s+([?!.])", r"\1", re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", " ".join(lines)).strip())
    if cleaned and not cleaned.endswith("?"):
        cleaned += "?"
    return cleaned or "Điểm quyết định cần review?"


def workflow_annotation_payload(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node["id"],
        "type": node.get("semantic_node_type") or "annotation",
        "attached_to": node.get("attached_to_node_id", ""),
        "attached_to_node_id": node.get("attached_to_node_id", ""),
        "title": node.get("title", ""),
        "content": node.get("content", ""),
        "risk_level": "high" if node.get("semantic_node_type") in {"warning", "audit_rule"} else "",
        "source_refs": node.get("source_refs", []),
        "bbox": node.get("bbox", []),
        "orphan": bool(node.get("orphan")),
        "dedupe_status": node.get("dedupe_status", "unique"),
    }


def workflow_lanes_from_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for actor in dict.fromkeys(str(node.get("actor") or "") for node in nodes if node.get("actor")):
        lane_nodes = [node["id"] for node in nodes if node.get("actor") == actor]
        lanes.append({"id": normalized_key(actor) or actor.lower(), "actor": actor, "node_ids": lane_nodes})
    return lanes


def validate_semantic_page(page_payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    annotation_ids = {node.get("id") for node in page_payload.get("annotations", []) if isinstance(node, dict)}
    for edge in [*page_payload.get("edges", []), *page_payload.get("uncertain_edges", [])]:
        if edge.get("from_node") in annotation_ids:
            errors.append(f"annotation_has_outgoing_edge:{edge.get('from_node')}")
    for annotation in page_payload.get("annotations", []):
        if isinstance(annotation, dict) and annotation.get("orphan"):
            errors.append(f"orphan_annotation:{annotation.get('id')}")
    return list(dict.fromkeys(errors))


def validate_semantic_workflow_graph_candidate(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    annotations = graph.get("annotations") if isinstance(graph.get("annotations"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    uncertain_edges = graph.get("uncertain_edges") if isinstance(graph.get("uncertain_edges"), list) else []
    annotation_ids = {annotation.get("id") for annotation in annotations if isinstance(annotation, dict)}
    seen_node_keys: set[tuple[str, str]] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_text = str(node.get("question") or node.get("content") or node.get("title") or "")
        key = (semantic_text_key(node_text), str(node.get("semantic_node_type") or node.get("type") or ""))
        if key in seen_node_keys and key[0]:
            errors.append(f"duplicate_semantic_node:{node.get('id')}")
        seen_node_keys.add(key)
    for edge in edges:
        condition = str(edge.get("condition") or "next")
        if edge.get("from_node") in annotation_ids:
            errors.append(f"annotation_has_outgoing_edge:{edge.get('from_node')}")
        if condition not in WORKFLOW_EDGE_CONDITIONS:
            errors.append(f"invalid_edge_condition:{condition}")
    for annotation in annotations:
        if isinstance(annotation, dict) and not annotation.get("attached_to"):
            errors.append(f"orphan_annotation:{annotation.get('id')}")
    incoming = {edge.get("to_node") for edge in edges}
    outgoing = {}
    uncertain_outgoing = {}
    for edge in edges:
        outgoing.setdefault(edge.get("from_node"), []).append(edge)
    for edge in uncertain_edges:
        uncertain_outgoing.setdefault(edge.get("from_node"), []).append(edge)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        if node_type == "start" and node_id in incoming:
            errors.append(f"start_has_incoming_edge:{node_id}")
        if node_type == "end" and outgoing.get(node_id):
            errors.append(f"end_has_outgoing_edge:{node_id}")
        if node_type == "decision":
            branch_conditions = {edge.get("condition") for edge in outgoing.get(node_id, [])}
            has_confirmed_branches = {"yes", "no"}.issubset(branch_conditions)
            if not has_confirmed_branches and not uncertain_outgoing.get(node_id):
                errors.append(f"decision_missing_branches_or_uncertain_edges:{node_id}")
    if graph.get("topology_source") == "raw_text_order":
        errors.append("workflow_graph_built_from_raw_text_order")
    return list(dict.fromkeys(errors))


def semantic_graph_confidence(summary: dict[str, Any], node_count: int, edge_count: int, uncertain_count: int, validation_errors: list[str]) -> float:
    base = clamp_float(summary.get("confidence"), 0.2, 0.75, default=0.45)
    if node_count >= 4:
        base += 0.08
    if edge_count:
        base += 0.05
    if uncertain_count:
        base -= 0.06
    if validation_errors:
        base -= 0.08
    return round(max(0.15, min(0.82, base)), 2)


def build_degraded_workflow_draft(filename: str, raw_text: str, blocks: list[dict[str, Any]], raw_context: dict[str, Any], classification: Any, ai_error: str) -> list[Any]:
    visual_layout = raw_context.get("visual_layout") if isinstance(raw_context.get("visual_layout"), dict) else {}
    semantic_refinement = raw_context.get("workflow_semantic_refinement") if isinstance(raw_context.get("workflow_semantic_refinement"), dict) else {}
    visual_summary = visual_layout.get("summary") if isinstance(visual_layout, dict) and isinstance(visual_layout.get("summary"), dict) else {}
    graph_status = "visual_layout_candidates_need_review" if visual_summary.get("shape_candidate_count") else "not_reliable_without_layout_review"
    chunks: list[Any] = [
        degraded_chunk(
            0,
            "full_sop",
            path_title(filename),
            raw_text[:30000],
            {
                "unit_type": "full_sop",
                "retrieval_scope": "document",
                "source_refs": [default_pdf_source_ref(filename)],
                "graph_extraction_status": graph_status,
                "visual_layout_summary": visual_summary,
                "publish_blocked_reason": "workflow_graph_requires_review",
            },
            classification,
            ai_error or "workflow_graph_requires_review",
        ),
        degraded_chunk(
            1,
            "candidate_workflow_text",
            "Workflow text extracted for review",
            raw_text[:30000],
            {
                "unit_type": "candidate_workflow_text",
                "retrieval_scope": "unit",
                "source_refs": [default_pdf_source_ref(filename)],
                "graph_extraction_status": graph_status,
                "visual_layout_summary": visual_summary,
                "publish_blocked_reason": "workflow_graph_requires_review",
            },
            classification,
            ai_error or "workflow_graph_requires_review",
        ),
    ]
    semantic_chunks = semantic_workflow_candidate_chunks(filename, semantic_refinement, len(chunks), classification, ai_error)
    if semantic_chunks:
        chunks.extend(semantic_chunks)
    else:
        for visual_chunk in visual_node_candidate_chunks(filename, visual_layout, len(chunks), classification, ai_error):
            chunks.append(visual_chunk)
        step_candidates = workflow_step_candidates(raw_text)
        for index, text in enumerate(step_candidates, start=1):
            unit_type = "candidate_warning" if contains_signal(text, [*WARNING_SIGNALS, "script", "sla"]) else "candidate_step"
            chunks.append(
                degraded_chunk(
                    len(chunks),
                    unit_type,
                    candidate_heading(text, unit_type, index),
                    text,
                    {
                        "unit_type": unit_type,
                        "retrieval_scope": "unit",
                        "source_refs": [default_pdf_source_ref(filename)],
                        "graph_extraction_status": "not_reliable_without_layout_review",
                        "publish_blocked_reason": "workflow_graph_requires_review",
                    },
                    classification,
                    ai_error or "workflow_graph_requires_review",
                )
            )
    return chunks


def semantic_workflow_candidate_chunks(filename: str, semantic_refinement: dict[str, Any], start_index: int, classification: Any, ai_error: str) -> list[Any]:
    if not semantic_refinement:
        return []
    output: list[Any] = []
    graph_candidate = semantic_refinement.get("workflow_graph_candidate") if isinstance(semantic_refinement.get("workflow_graph_candidate"), dict) else {}
    graph_confidence = graph_candidate.get("graph_confidence") or semantic_refinement.get("summary", {}).get("graph_confidence")
    topology_review_required = bool(graph_candidate.get("topology_review_required", True))
    uncertain_edges = graph_candidate.get("uncertain_edges") if isinstance(graph_candidate.get("uncertain_edges"), list) else []
    pages = semantic_refinement.get("pages") if isinstance(semantic_refinement.get("pages"), list) else []
    if graph_candidate.get("nodes"):
        validation_errors = graph_candidate.get("validation_errors") if isinstance(graph_candidate.get("validation_errors"), list) else semantic_refinement.get("validation_errors", [])
        annotations = graph_candidate.get("annotations") if isinstance(graph_candidate.get("annotations"), list) else []
        graph_refs = graph_candidate.get("source_refs") if isinstance(graph_candidate.get("source_refs"), list) else []
        output.append(
            degraded_chunk(
                start_index,
                "workflow_graph",
                str(graph_candidate.get("title") or path_title(filename) or "Workflow graph"),
                semantic_workflow_graph_summary(graph_candidate),
                {
                    "unit_type": "workflow_graph",
                    "retrieval_scope": "graph",
                    "workflow_graph": graph_candidate,
                    "graph_confidence": graph_confidence,
                    "requires_human_review": True,
                    "review_reason": graph_candidate.get("review_reason") or "Semantic workflow graph was normalized from visual candidates and requires manual topology review.",
                    "annotations": annotations,
                    "uncertain_edges": uncertain_edges,
                    "uncertain_edges_count": len(uncertain_edges),
                    "graph_validation_errors": validation_errors,
                    "graph_validation_error_count": len(validation_errors),
                    "topology_review_required": topology_review_required,
                    "graph_extraction_status": "semantic_workflow_graph_candidate_needs_review",
                    "source_ref_quality": source_ref_quality_from_refs(graph_refs),
                    "source_ref_acknowledged": False,
                    "source_refs": graph_refs or [default_pdf_source_ref(filename)],
                    "publish_blocked_reason": "workflow_graph_requires_review",
                },
                classification,
                ai_error or "workflow_graph_requires_review",
            )
        )
    for page in pages:
        if not isinstance(page, dict):
            continue
        for node in [*(page.get("semantic_nodes") or []), *(page.get("annotations") or [])]:
            if not isinstance(node, dict):
                continue
            semantic_type = str(node.get("semantic_node_type") or "action")
            if semantic_type in {"start", "end"}:
                continue
            unit_type = SEMANTIC_CANDIDATE_UNIT_TYPES.get(semantic_type, "candidate_action")
            title = str(node.get("title") or node.get("content") or unit_type).strip()
            content = str(node.get("content") or title).strip()
            if not content:
                continue
            attached_uncertain_edges = [
                edge for edge in uncertain_edges
                if edge.get("from_node") == node.get("id") or edge.get("to_node") == node.get("id")
            ][:6]
            output.append(
                degraded_chunk(
                    start_index + len(output),
                    unit_type,
                    candidate_heading(title, unit_type, len(output) + 1),
                    content,
                    {
                        "unit_type": unit_type,
                        "retrieval_scope": "unit",
                        "semantic_node_id": node.get("id"),
                        "semantic_node_type": semantic_type,
                        "dedupe_status": node.get("dedupe_status", "unique"),
                        "attached_to_node_id": node.get("attached_to_node_id", ""),
                        "attached_annotations": node.get("attached_annotations", []),
                        "uncertain_edges": attached_uncertain_edges,
                        "graph_confidence": graph_confidence,
                        "topology_review_required": topology_review_required,
                        "graph_extraction_status": "semantic_workflow_refinement_needs_review",
                        "source_ref_quality": source_ref_quality_from_refs(node.get("source_refs") or []),
                        "source_ref_acknowledged": False,
                        "source_refs": node.get("source_refs") or [default_pdf_source_ref(filename)],
                        "publish_blocked_reason": "workflow_graph_requires_review",
                    },
                    classification,
                    ai_error or "workflow_graph_requires_review",
                )
            )
    return output[:100]


def semantic_workflow_graph_summary(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    uncertain_edges = graph.get("uncertain_edges") if isinstance(graph.get("uncertain_edges"), list) else []
    annotations = graph.get("annotations") if isinstance(graph.get("annotations"), list) else []
    node_lines = [
        f"- {node.get('id')}: {node.get('question') or node.get('title') or node.get('content')} ({node.get('semantic_node_type') or node.get('type') or ''})"
        + (f" — {node.get('content')}" if node.get("content") and node.get("content") not in {node.get("title"), node.get("question")} else "")
        for node in nodes[:40]
        if isinstance(node, dict)
    ]
    return "\n".join(
        [
            f"Workflow graph: {graph.get('title') or 'Workflow graph'}",
            f"Nodes: {len(nodes)}",
            f"Confirmed edges: {len(edges)}",
            f"Uncertain edges requiring review: {len(uncertain_edges)}",
            f"Annotations: {len(annotations)}",
            "Node text:",
            *node_lines,
            str(graph.get("review_reason") or "Manual topology review required before publish."),
        ]
    )


def visual_node_candidate_chunks(filename: str, visual_layout: dict[str, Any], start_index: int, classification: Any, ai_error: str) -> list[Any]:
    if not visual_layout:
        return []
    output: list[Any] = []
    for page in visual_layout.get("pages", []) if isinstance(visual_layout.get("pages"), list) else []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page") or 1)
        graph = page.get("graph_candidate") if isinstance(page.get("graph_candidate"), dict) else {}
        for node in graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []:
            if not isinstance(node, dict):
                continue
            title = str(node.get("title") or "").strip()
            if not title:
                continue
            node_type = str(node.get("type") or "")
            unit_type = "candidate_step"
            if node_type == "decision":
                unit_type = "decision_point"
            content = f"Visual node candidate: {title}"
            output.append(
                degraded_chunk(
                    start_index + len(output),
                    unit_type,
                    candidate_heading(title, unit_type, len(output) + 1),
                    content,
                    {
                        "unit_type": unit_type,
                        "retrieval_scope": "unit",
                        "visual_node_id": node.get("id"),
                        "visual_node_type": node_type,
                        "graph_extraction_status": "visual_layout_candidates_need_review",
                        "source_ref_quality": "bbox" if node.get("bbox") else "page_only",
                        "source_ref_acknowledged": False,
                        "source_refs": [
                            {
                                "source_type": "pdf_diagram",
                                "source_file": filename,
                                "page": page_number,
                                "bbox": node.get("bbox") or [],
                            }
                        ],
                        "publish_blocked_reason": "workflow_graph_requires_review",
                    },
                    classification,
                    ai_error or "workflow_graph_requires_review",
                )
            )
    return output[:80]


def degraded_chunk(index: int, section: str, heading: str, content: str, metadata: dict[str, Any], classification: Any, ai_error: str) -> Any:
    from app.text_processing import Chunk

    base_metadata = {
        "document_type": classification.document_type,
        "source_type": classification.source_type,
        "review_status": "needs_review",
        "confidence": min(classification.confidence, 0.55),
        "extraction_status": "degraded",
        "extraction_lifecycle_status": "degraded_structured_draft",
        "publish_blocked": True,
        "publish_blocked_reason": metadata.get("publish_blocked_reason") or "ai_structuring_failed_requires_manual_curation",
        "ai_error": ai_error or None,
        "requires_human_review": True,
        "source_ref_quality": metadata.get("source_ref_quality") or source_ref_quality_from_refs(metadata.get("source_refs", [])),
        "source_ref_acknowledged": metadata.get("source_ref_acknowledged", source_ref_quality_from_refs(metadata.get("source_refs", [])) != "page_only"),
        "source_evidence_only": True,
    }
    return Chunk(
        chunk_index=index,
        section=section,
        heading=heading[:180] or section,
        content=content.strip(),
        token_count=len(tokenize(content)),
        metadata={**base_metadata, **metadata},
    )


def mark_structured_chunks(chunks: list[Any]) -> list[Any]:
    output = []
    for chunk in chunks:
        metadata = {
            **chunk.metadata,
            "extraction_status": "structured",
            "extraction_lifecycle_status": "structured_draft",
            "publish_blocked": False,
            "publish_blocked_reason": "",
            "requires_human_review": True,
        }
        output.append(replace_chunk_metadata(chunk, metadata))
    return output


def mark_degraded_chunks(chunks: list[Any], classification: Any, ai_error: str, reason: str, lifecycle: str) -> list[Any]:
    return [
        degraded_chunk(
            index,
            chunk.section,
            chunk.heading or f"Candidate section {index + 1}",
            chunk.content,
            {**chunk.metadata, "publish_blocked_reason": reason, "extraction_lifecycle_status": lifecycle},
            classification,
            ai_error,
        )
        for index, chunk in enumerate(chunks)
    ]


def normalize_units(chunks: list[Any]) -> list[Any]:
    normalized = [
        replace_chunk_metadata(
            chunk,
            {
                **chunk.metadata,
                "source_refs": chunk.metadata.get("source_refs") or source_refs_from_chunk(chunk),
                "source_ref_quality": chunk.metadata.get("source_ref_quality") or source_ref_quality_from_refs(chunk.metadata.get("source_refs") or source_refs_from_chunk(chunk)),
            },
        )
        for chunk in chunks
        if str(chunk.content or "").strip()
    ]
    return attach_notes_to_nearest_parent(normalized)


def refine_units_for_delivery(
    *,
    filename: str,
    raw_text: str,
    classification: Any,
    blocks: list[dict[str, Any]],
    source_chunks: list[Any],
) -> tuple[list[Any], dict[str, Any], list[str], str]:
    deterministic_chunks, deterministic_report = deterministic_refine_chunks(source_chunks, classification.document_type)
    original_degraded = any(chunk.metadata.get("extraction_status") == "degraded" for chunk in deterministic_chunks)
    report: dict[str, Any] = {
        "deterministic": deterministic_report,
        "llm": {"llm_refine_status": "not_attempted"},
    }
    warnings: list[str] = []

    if not should_attempt_llm_refine(classification.document_type, deterministic_chunks):
        report["llm"] = {"llm_refine_status": "skipped", "reason": "document_type_or_degraded_status"}
        return deterministic_chunks, report, warnings, ""

    llm_units, llm_report, llm_warnings = refine_extracted_units(
        filename=filename,
        raw_text=raw_text,
        document_type=classification.document_type,
        source_type=classification.source_type,
        units=chunks_to_refine_units(deterministic_chunks),
        source_blocks=blocks,
    )
    report["llm"] = llm_report
    user_visible_warnings = [warning for warning in llm_warnings if warning != "openrouter_refine_disabled"]
    warnings.extend(user_visible_warnings)

    if not llm_units:
        return deterministic_chunks, report, warnings, "" if "openrouter_refine_disabled" in llm_warnings else ",".join(llm_warnings[:3])

    llm_chunks = ai_units_to_chunks(llm_units, filename, classification.source_type, classification.document_type)
    llm_chunks = mark_refined_degraded_chunks(llm_chunks, deterministic_chunks) if original_degraded else mark_structured_chunks(llm_chunks)
    llm_chunks = normalize_units(llm_chunks)
    validation_error = refined_chunks_validation_error(deterministic_chunks, llm_chunks, filename, classification.document_type)
    if validation_error:
        report["llm"] = {**report.get("llm", {}), "llm_refine_status": "rejected", "reject_reason": validation_error}
        warnings.append(f"llm_refine_rejected:{validation_error}")
        return deterministic_chunks, report, warnings, ""

    merged_report = evaluate_refinement_report(llm_chunks, classification.document_type)
    report["llm"] = {**report.get("llm", {}), "post_guard": merged_report}
    return llm_chunks, report, warnings, ""


def should_attempt_llm_refine(document_type: str, chunks: list[Any]) -> bool:
    return document_type in {"policy_rule", "policy_table"}


def mark_refined_degraded_chunks(chunks: list[Any], original_chunks: list[Any]) -> list[Any]:
    publish_blocked_reason = next(
        (
            str(chunk.metadata.get("publish_blocked_reason"))
            for chunk in original_chunks
            if chunk.metadata.get("publish_blocked_reason")
        ),
        "ai_structuring_failed_requires_manual_curation",
    )
    return [
        replace_chunk_metadata(
            chunk,
            {
                **chunk.metadata,
                "extraction_status": "degraded",
                "extraction_lifecycle_status": "degraded_refined_draft",
                "publish_blocked": True,
                "publish_blocked_reason": publish_blocked_reason,
                "requires_human_review": True,
                "source_evidence_only": True,
                "refined_from_degraded_draft": True,
            },
        )
        for chunk in chunks
    ]


def chunks_to_refine_units(chunks: list[Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for chunk in chunks:
        metadata = dict(chunk.metadata or {})
        units.append(
            {
                "unit_type": metadata.get("unit_type") or chunk.section,
                "title": chunk.heading,
                "content": chunk.content,
                "confidence": metadata.get("confidence", 0.72),
                "metadata": metadata,
                "source_refs": metadata.get("source_refs") or source_refs_from_chunk(chunk),
            }
        )
    return units


def deterministic_refine_chunks(chunks: list[Any], document_type: str) -> tuple[list[Any], dict[str, Any]]:
    output: list[Any] = []
    seen: set[str] = set()
    seen_content: dict[str, int] = {}
    last_parent_index: int | None = None
    report: dict[str, Any] = {
        "status": "completed",
        "filtered_noise_count": 0,
        "deduped_count": 0,
        "repaired_orphan_examples": 0,
        "normalized_metadata_count": 0,
        "groups": [],
        "conflicts": [],
        "coverage": {},
    }

    for chunk in chunks:
        metadata = dict(chunk.metadata or {})
        unit_type = str(metadata.get("unit_type") or chunk.section or "text_section")
        examples = parse_examples_from_text(chunk.content)
        if examples and is_example_only_chunk(chunk) and last_parent_index is not None:
            parent = output[last_parent_index]
            parent_metadata = dict(parent.metadata or {})
            parent_examples = list(parent_metadata.get("examples") or [])
            parent_metadata["examples"] = merge_examples(parent_examples, examples)
            parent_metadata.setdefault("refinement_repairs", []).append("attached_orphan_examples")
            output[last_parent_index] = replace_chunk_metadata(parent, parent_metadata)
            report["filtered_noise_count"] += 1
            report["repaired_orphan_examples"] += 1
            continue

        content_key = content_fingerprint(chunk.content)
        if unit_type != "full_sop" and content_key and content_key in seen_content:
            existing_index = seen_content[content_key]
            output[existing_index] = merge_duplicate_chunks(output[existing_index], chunk)
            report["deduped_count"] += 1
            continue

        key = dedupe_chunk_key(chunk)
        if key in seen and unit_type != "full_sop":
            report["deduped_count"] += 1
            continue
        seen.add(key)

        refined_metadata = refine_unit_metadata(chunk, metadata)
        if refined_metadata != metadata:
            report["normalized_metadata_count"] += 1
        refined_chunk = replace_chunk_metadata(chunk, refined_metadata)
        output.append(refined_chunk)
        if unit_type != "full_sop" and content_key:
            seen_content[content_key] = len(output) - 1
        if unit_type not in {"full_sop", "candidate_warning", "warning", "operational_note", "security_note", "compliance_note"}:
            last_parent_index = len(output) - 1

    output, groups = group_related_rules(output)
    conflicts = detect_refinement_conflicts(output)
    coverage = evaluate_refinement_report(output, document_type)
    report.update({"groups": groups, "conflicts": conflicts, "coverage": coverage})
    output = attach_refinement_summary_to_document_layer(output, report)
    return reindex_local_chunks(output), report


def refine_unit_metadata(chunk: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    unit_type = str(metadata.get("unit_type") or chunk.section or "text_section")
    refs = metadata.get("source_refs") or source_refs_from_chunk(chunk)
    source_ref_quality = source_ref_quality_from_refs(refs)
    tags = list(metadata.get("tags") or [])
    aliases = list(metadata.get("aliases") or [])
    text = " ".join([chunk.heading or "", chunk.content or "", json.dumps(metadata, ensure_ascii=False)])

    if not tags:
        tags = infer_tags_from_text(text, unit_type)
    else:
        tags = list(dict.fromkeys([*tags, *infer_tags_from_text(text, unit_type)]))
    if not aliases:
        aliases = infer_aliases_from_unit(chunk, metadata)

    refined = {
        **metadata,
        "unit_type": unit_type,
        "source_refs": refs,
        "source_ref_quality": metadata.get("source_ref_quality") or source_ref_quality,
        "source_ref_acknowledged": metadata.get("source_ref_acknowledged", source_ref_quality not in {"page_only", "none"}),
        "tags": tags,
        "aliases": aliases,
    }
    if metadata.get("structure_type") == "financial_threshold_matrix" or "rounding" in tags:
        threshold = metadata.get("rounding_threshold") or parse_rounding_threshold(chunk.content)
        if threshold:
            refined["rounding_threshold"] = threshold
            try:
                refined.setdefault("rounding_directions", rounding_directions(chunk.content, int(threshold)))
            except (TypeError, ValueError):
                pass
    return refined


def infer_tags_from_text(text: str, unit_type: str) -> list[str]:
    normalized = normalized_search_text(text)
    tags: list[str] = []
    if unit_type:
        tags.append(unit_type)
    if any(term in normalized for term in ["lam tron", "moc", "threshold"]):
        tags.append("rounding")
    if any(term in normalized for term in ["hoan", "refund", "boi hoan"]):
        tags.append("refund")
    if any(term in normalized for term in ["rut", "withdraw"]):
        tags.append("withdraw")
    if any(term in normalized for term in ["tien", "payment", "thanh toan", "pttt"]):
        tags.append("financial_policy")
    if "pm04" in normalized:
        tags.append("pm04")
    if any(term in normalized for term in ["khong ap dung", "exception", "ngoai le"]):
        tags.append("no_rounding")
    return list(dict.fromkeys(tag for tag in tags if tag))


def infer_aliases_from_unit(chunk: Any, metadata: dict[str, Any]) -> list[str]:
    aliases = []
    service = str(metadata.get("service_label") or metadata.get("service") or "").strip()
    case_name = str(metadata.get("case_name") or "").strip()
    threshold = metadata.get("rounding_threshold")
    title = str(chunk.heading or "").strip()
    if title:
        aliases.append(title)
    if service or case_name:
        aliases.append(" ".join(part for part in [service, case_name] if part))
        aliases.append(" ".join(part for part in [service, case_name, "làm tròn"] if part))
    if threshold:
        aliases.append(f"mốc {threshold}đ")
        aliases.append(f"{threshold}đ rounding")
    if metadata.get("rounding_applies") is False:
        aliases.append("không áp dụng làm tròn")
    return [alias for alias in dict.fromkeys(aliases) if alias]


def group_related_rules(chunks: list[Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    grouped: dict[str, list[int]] = {}
    for index, chunk in enumerate(chunks):
        metadata = chunk.metadata or {}
        unit_type = str(metadata.get("unit_type") or chunk.section or "")
        if unit_type == "full_sop":
            continue
        group_key = refinement_group_key(metadata)
        if group_key:
            grouped.setdefault(group_key, []).append(index)

    groups: list[dict[str, Any]] = []
    output = list(chunks)
    for group_key, indexes in grouped.items():
        if len(indexes) < 2:
            continue
        titles = [output[index].heading for index in indexes if output[index].heading]
        group_id = f"group_{normalized_key(group_key)[:80] or len(groups) + 1}"
        groups.append({"group_id": group_id, "group_label": group_key, "unit_count": len(indexes), "titles": titles})
        for index in indexes:
            chunk = output[index]
            metadata = {
                **chunk.metadata,
                "rule_group_id": group_id,
                "group_label": group_key,
                "related_rule_titles": [title for title in titles if title != chunk.heading],
            }
            output[index] = replace_chunk_metadata(chunk, metadata)
    return output, groups


def refinement_group_key(metadata: dict[str, Any]) -> str:
    if metadata.get("structure_type") == "financial_threshold_matrix":
        return str(metadata.get("service_label") or metadata.get("service") or "financial_threshold_matrix")
    if metadata.get("service_label") or metadata.get("service"):
        return str(metadata.get("service_label") or metadata.get("service"))
    section_path = metadata.get("section_path")
    if isinstance(section_path, list) and section_path:
        return str(section_path[0])
    return ""


def detect_refinement_conflicts(chunks: list[Any]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    by_case: dict[str, list[Any]] = {}
    for chunk in chunks:
        metadata = chunk.metadata or {}
        unit_type = str(metadata.get("unit_type") or chunk.section or "")
        if unit_type not in {"policy_rule", "exception_rule", "threshold_rule"}:
            continue
        service = str(metadata.get("service") or metadata.get("service_label") or "")
        case_type = str(metadata.get("case_type") or metadata.get("case_name") or chunk.heading)
        key = normalized_key(f"{service} {case_type}")
        by_case.setdefault(key, []).append(chunk)

    for key, items in by_case.items():
        applies_values = {item.metadata.get("rounding_applies") for item in items if "rounding_applies" in item.metadata}
        thresholds = {item.metadata.get("rounding_threshold") for item in items if item.metadata.get("rounding_threshold")}
        if True in applies_values and False in applies_values:
            conflicts.append({"type": "rounding_apply_conflict", "case_key": key, "titles": [item.heading for item in items]})
        if len(thresholds) > 1:
            conflicts.append({"type": "threshold_conflict", "case_key": key, "thresholds": sorted(thresholds), "titles": [item.heading for item in items]})
    return conflicts


def evaluate_refinement_report(chunks: list[Any], document_type: str) -> dict[str, Any]:
    metadata_items = [chunk.metadata or {} for chunk in chunks]
    atomic_units = [
        metadata for metadata in metadata_items
        if str(metadata.get("retrieval_scope") or "") != "document"
        and str(metadata.get("unit_type") or "") != "full_sop"
        and not str(metadata.get("unit_type") or "").startswith("candidate_")
    ]
    missing_fields: list[str] = []
    if not any(metadata.get("unit_type") == "full_sop" for metadata in metadata_items):
        missing_fields.append("full_sop")
    if document_type in {"policy_rule", "policy_table", "workflow_diagram"} and not atomic_units:
        missing_fields.append("atomic_units")
    if any(metadata.get("unit_type") == "policy_rule" and not metadata.get("source_refs") for metadata in metadata_items):
        missing_fields.append("policy_rule_source_refs")
    if any(metadata.get("unit_type") == "policy_rule" and metadata.get("structure_type") == "financial_threshold_matrix" and not metadata.get("rounding_threshold") for metadata in metadata_items):
        missing_fields.append("rounding_threshold")

    hard_blockers = policy_table_verification_blockers(metadata_items, document_type)
    quality = aggregate_source_ref_quality(chunks)
    score = max(0, 100 - len(missing_fields) * 15 - len(hard_blockers) * 20)
    return {
        "coverage_score": score,
        "unit_count": len(chunks),
        "atomic_unit_count": len(atomic_units),
        "full_sop_count": sum(1 for metadata in metadata_items if metadata.get("unit_type") == "full_sop"),
        "policy_rule_count": sum(1 for metadata in metadata_items if metadata.get("unit_type") == "policy_rule"),
        "exception_rule_count": sum(1 for metadata in metadata_items if metadata.get("unit_type") == "exception_rule"),
        "source_ref_quality": quality,
        "missing_fields": list(dict.fromkeys(missing_fields)),
        "semantic_blockers": hard_blockers,
    }


def refined_chunks_validation_error(original_chunks: list[Any], refined_chunks: list[Any], filename: str, document_type: str) -> str:
    if not refined_chunks:
        return "empty_refined_units"
    original_metadata = [chunk.metadata or {} for chunk in original_chunks]
    refined_metadata = [chunk.metadata or {} for chunk in refined_chunks]
    if not any(metadata.get("unit_type") == "full_sop" for metadata in refined_metadata):
        return "missing_full_sop"
    original_atomic = [
        metadata for metadata in original_metadata
        if metadata.get("unit_type") != "full_sop"
        and str(metadata.get("retrieval_scope") or "") != "document"
        and not str(metadata.get("unit_type") or "").startswith("candidate_")
    ]
    refined_atomic = [
        metadata for metadata in refined_metadata
        if metadata.get("unit_type") != "full_sop"
        and str(metadata.get("retrieval_scope") or "") != "document"
        and not str(metadata.get("unit_type") or "").startswith("candidate_")
    ]
    if original_atomic and len(refined_atomic) < max(1, len(original_atomic) - duplicate_source_ref_count(original_metadata)):
        return "atomic_units_dropped"
    if missing_source_ref_units(refined_chunks, filename):
        return "missing_source_refs"
    semantic_blockers = policy_table_verification_blockers(refined_metadata, document_type)
    blocking = [blocker for blocker in semantic_blockers if blocker in {"missing_policy_rules", "missing_exception_rules", "missing_threshold_metadata", "weak_table_source_refs", "orphan_examples"}]
    if blocking:
        return ",".join(blocking)
    return ""


def duplicate_source_ref_count(metadata_items: list[dict[str, Any]]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for metadata in metadata_items:
        refs = json.dumps(metadata.get("source_refs") or [], sort_keys=True, ensure_ascii=False)
        if not refs:
            continue
        if refs in seen:
            duplicates += 1
        seen.add(refs)
    return duplicates


def missing_source_ref_units(chunks: list[Any], filename: str) -> list[str]:
    missing: list[str] = []
    lower = filename.lower()
    for chunk in chunks:
        metadata = chunk.metadata or {}
        refs = metadata.get("source_refs") or source_refs_from_chunk(chunk)
        if not refs:
            missing.append(chunk.heading)
            continue
        if lower.endswith(".docx") and not any(ref.get("paragraph_index") is not None or ref.get("heading_path") or (ref.get("table_index") is not None and ref.get("row_index") is not None) for ref in refs if isinstance(ref, dict)):
            missing.append(chunk.heading)
    return missing


def attach_refinement_summary_to_document_layer(chunks: list[Any], report: dict[str, Any]) -> list[Any]:
    output = []
    for chunk in chunks:
        metadata = dict(chunk.metadata or {})
        if metadata.get("unit_type") == "full_sop" or metadata.get("retrieval_scope") == "document":
            metadata["refinement_summary"] = {
                "coverage": report.get("coverage", {}),
                "group_count": len(report.get("groups", [])),
                "conflict_count": len(report.get("conflicts", [])),
                "filtered_noise_count": report.get("filtered_noise_count", 0),
                "deduped_count": report.get("deduped_count", 0),
            }
        output.append(replace_chunk_metadata(chunk, metadata))
    return output


def reindex_local_chunks(chunks: list[Any]) -> list[Any]:
    return [
        Chunk(
            chunk_index=index,
            section=chunk.section,
            heading=chunk.heading,
            content=chunk.content,
            token_count=chunk.token_count,
            metadata=chunk.metadata,
        )
        for index, chunk in enumerate(chunks)
    ]


def merge_duplicate_chunks(existing: Any, duplicate: Any) -> Any:
    existing_metadata = dict(existing.metadata or {})
    duplicate_metadata = dict(duplicate.metadata or {})
    existing_type = str(existing_metadata.get("unit_type") or existing.section or "")
    duplicate_type = str(duplicate_metadata.get("unit_type") or duplicate.section or "")
    merged_type = stronger_unit_type(existing_type, duplicate_type)
    merged_metadata = {
        **existing_metadata,
        "unit_type": merged_type,
        "source_refs": merge_source_refs(existing_metadata.get("source_refs"), duplicate_metadata.get("source_refs")),
        "tags": list(dict.fromkeys([*(existing_metadata.get("tags") or []), *(duplicate_metadata.get("tags") or [])])),
        "aliases": list(dict.fromkeys([*(existing_metadata.get("aliases") or []), *(duplicate_metadata.get("aliases") or [])])),
        "merged_duplicate_unit_types": list(dict.fromkeys([*(existing_metadata.get("merged_duplicate_unit_types") or []), existing_type, duplicate_type])),
        "merged_duplicate_titles": list(dict.fromkeys([*(existing_metadata.get("merged_duplicate_titles") or []), existing.heading, duplicate.heading])),
    }
    if duplicate_type in {"candidate_warning", "warning", "security_note", "compliance_note"} or duplicate_metadata.get("inline_warning"):
        merged_metadata["inline_warning"] = True
    return replace_chunk_metadata(existing, merged_metadata)


def stronger_unit_type(left: str, right: str) -> str:
    priority = {
        "policy_rule": 90,
        "exception_rule": 88,
        "threshold_rule": 86,
        "candidate_rule": 70,
        "handling_rule": 68,
        "operational_instruction": 66,
        "candidate_warning": 45,
        "warning": 44,
        "operational_note": 35,
        "candidate_section": 20,
        "text_section": 10,
    }
    return left if priority.get(left, 0) >= priority.get(right, 0) else right


def merge_source_refs(left: Any, right: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for refs in (left, right):
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            key = json.dumps(ref, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            output.append(ref)
            seen.add(key)
    return output


def dedupe_chunk_key(chunk: Any) -> str:
    metadata = chunk.metadata or {}
    source_refs = json.dumps(metadata.get("source_refs") or [], sort_keys=True, ensure_ascii=False)
    if source_refs and metadata.get("unit_type") != "full_sop":
        return f"{metadata.get('unit_type')}:{source_refs}"
    return normalized_key(f"{metadata.get('unit_type') or chunk.section} {chunk.heading} {chunk.content}")[:240]


def content_fingerprint(value: str) -> str:
    return normalized_key(value)[:600]


def is_example_only_chunk(chunk: Any) -> bool:
    text = str(chunk.content or "").strip()
    if not text:
        return False
    examples = parse_examples_from_text(text)
    if not examples:
        return False
    stripped = re.sub(r"(?i)\b(ví dụ|vi du|vd)\s*:?", "", normalized_search_text(text)).strip()
    number_tokens = re.findall(r"\d[\d,.]*", stripped)
    word_tokens = [token for token in stripped.split() if not re.match(r"^\d", token) and token not in {"d", "hoac"}]
    return bool(number_tokens) and len(word_tokens) <= 4


def parse_examples_from_text(text: str) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for line in str(text or "").splitlines():
        examples.extend(parse_example_line(line.strip()))
    return examples


def merge_examples(existing: list[Any], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = [item for item in existing if isinstance(item, dict)]
    seen = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in output}
    for item in incoming:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            output.append(item)
            seen.add(key)
    return output


def attach_notes_to_nearest_parent(chunks: list[Any]) -> list[Any]:
    output = []
    last_parent_id = ""
    for chunk in chunks:
        metadata = dict(chunk.metadata or {})
        unit_type = str(metadata.get("unit_type") or chunk.section or "")
        parent_id = str(
            metadata.get("parent_unit_id")
            or metadata.get("rule_id")
            or metadata.get("workflow_node_id")
            or metadata.get("workflow_id")
            or f"{unit_type}_{chunk.chunk_index}"
        )
        is_note_like = unit_type in {"candidate_warning", "operational_note", "security_note", "macro_script"} or unit_type.endswith("_note") or "script" in unit_type
        if is_note_like and not metadata.get("attached_to"):
            if last_parent_id:
                metadata["attached_to"] = last_parent_id
            else:
                metadata["attachment_status"] = "needs_review_no_parent"
                metadata["review_status"] = "needs_review"
        if not is_note_like and unit_type != "full_sop":
            last_parent_id = parent_id
        metadata["parent_unit_id"] = metadata.get("parent_unit_id") or parent_id
        output.append(replace_chunk_metadata(chunk, metadata))
    return output


def validate_units_for_review(chunks: list[Any], document_type: str) -> list[Any]:
    output = []
    for chunk in chunks:
        metadata = {
            **chunk.metadata,
            "review_status": chunk.metadata.get("review_status") or "needs_review",
            "document_type": chunk.metadata.get("document_type") or document_type,
        }
        output.append(replace_chunk_metadata(chunk, metadata))
    return output


def embed_chunks(source_chunks: list[Any], base_metadata: dict[str, Any], enrichment: dict[str, Any], filename: str) -> list[dict[str, Any]]:
    chunks = []
    document_title = str(base_metadata.get("title") or path_title(filename))
    for chunk in source_chunks:
        unit_type = str(chunk.metadata.get("unit_type") or chunk.section or "text_section")
        extraction_status = str(chunk.metadata.get("extraction_status") or enrichment.get("extraction_status") or "structured")
        review_status = str(chunk.metadata.get("review_status") or "needs_review")
        publish_blocked = bool(chunk.metadata.get("publish_blocked") or extraction_status == "degraded")
        index_eligible = extraction_status in {"structured", "manually_curated"} and review_status == "approved" and not publish_blocked
        parent_unit_id = str(
            chunk.metadata.get("parent_unit_id")
            or chunk.metadata.get("rule_id")
            or chunk.metadata.get("workflow_node_id")
            or chunk.metadata.get("workflow_id")
            or f"{unit_type}_{chunk.chunk_index}"
        )
        section_path = chunk.metadata.get("section_path")
        if not isinstance(section_path, list):
            section_path = [part for part in [chunk.heading or "", chunk.section or ""] if part]
        chunk_metadata = {
            **base_metadata,
            **enrichment,
            "source_filename": filename,
            **chunk.metadata,
            "artifact_type": chunk.metadata.get("artifact_type") or ("draft_unit" if extraction_status != "failed" else "source_evidence"),
            "document_title": document_title,
            "index_eligible": index_eligible,
            "pipeline_stage": chunk.metadata.get("pipeline_stage") or ("plan" if extraction_status == "degraded" else "refine"),
            "section_path": section_path,
            "parent_unit_id": parent_unit_id,
            "publish_state": chunk.metadata.get("publish_state") or ("blocked" if publish_blocked else "draft"),
            "unit_type": unit_type,
        }
        chunks.append(
            {
                "chunk_index": chunk.chunk_index,
                "section": chunk.section,
                "heading": chunk.heading,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "embedding": embed_text(" ".join([chunk.heading, chunk.content])),
                "metadata": chunk_metadata,
            }
        )
    return chunks


def replace_chunk_metadata(chunk: Any, metadata: dict[str, Any]) -> Any:
    from app.text_processing import Chunk

    return Chunk(
        chunk_index=chunk.chunk_index,
        section=chunk.section,
        heading=chunk.heading,
        content=chunk.content,
        token_count=chunk.token_count,
        metadata=metadata,
    )


def text_line_blocks(raw_text: str) -> list[dict[str, Any]]:
    return [
        {"type": "line", "line_start": index, "line_end": index, "index": index - 1, "text": line.strip()}
        for index, line in enumerate(raw_text.splitlines(), start=1)
        if line.strip()
    ]


def pdf_text_blocks(raw_text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current_page = 1
    page_line = 1
    for line in raw_text.splitlines():
        page_match = re.match(r"\[page\s+(\d+)\]", line.strip(), re.IGNORECASE)
        if page_match:
            current_page = int(page_match.group(1))
            page_line = 1
            continue
        text = line.strip()
        if not text:
            continue
        blocks.append({"type": "pdf_line", "page": current_page, "line_start": page_line, "line_end": page_line, "index": len(blocks), "text": text})
        page_line += 1
    return blocks


def paragraph_groups_from_blocks(blocks: list[dict[str, Any]], max_chars: int = 900) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_len = 0
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        item = {**block, "index": int(block.get("index") if block.get("index") is not None else index)}
        starts_new = is_heading_like_text(text) or (current and starts_warning_block(text)) or current_len + len(text) > max_chars
        if current and starts_new:
            groups.append(current)
            current = []
            current_len = 0
        current.append(item)
        current_len += len(text)
    if current:
        groups.append(current)
    return groups


def is_heading_like_text(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 140:
        return False
    return bool(
        re.match(r"^(\d+(?:\.\d+)*[.)]?\s+|[IVX]+[.)]\s+|[A-ZĐ][^.!?]{4,}:$)", stripped)
        or (len(stripped.split()) <= 10 and not stripped.endswith((".", ";", ",")))
    )


def starts_warning_block(text: str) -> bool:
    normalized = normalize_for_signal(text)
    return normalized.startswith(("lưu ý", "luu y", "note", "warning", "cảnh báo", "canh bao")) or normalized.startswith("không gửi mail")


def contains_signal(text: str, signals: list[str]) -> bool:
    normalized = normalize_for_signal(text)
    return any(normalize_for_signal(signal) in normalized for signal in signals)


def normalize_for_signal(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = re.sub(r"\s+", " ", value)
    return value


def sanitize_ai_error(exc: Exception) -> str:
    detail = str(exc).replace("\x00", "").strip()
    if len(detail) > 240:
        detail = detail[:240] + "..."
    return f"{exc.__class__.__name__}:{detail}" if detail else exc.__class__.__name__


def candidate_heading(text: str, unit_type: str, index: int) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line and len(first_line) <= 90:
        return first_line
    prefix = {
        "candidate_action": "Candidate action",
        "candidate_annotation": "Candidate annotation",
        "candidate_audit_rule": "Candidate audit rule",
        "candidate_decision": "Candidate decision",
        "candidate_queue_rule": "Candidate queue rule",
        "candidate_rule": "Candidate rule",
        "candidate_sla": "Candidate SLA",
        "candidate_warning": "Candidate warning",
        "candidate_step": "Candidate step",
        "candidate_workflow_text": "Candidate workflow text",
        "candidate_table_row": "Candidate table row",
    }.get(unit_type, "Candidate section")
    words = first_line.split()[:10] if first_line else text.split()[:10]
    return f"{prefix} {index}: {' '.join(words)}".strip()


def path_title(filename: str) -> str:
    return filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()[:180] or "Full SOP"


def source_ref_for_text_block(filename: str, content_type: str, blocks: list[dict[str, Any]], start_index: int, end_index: int, content: str) -> dict[str, Any]:
    lower = filename.lower()
    selected = [block for block in blocks if start_index <= int(block.get("index", 0)) <= end_index]
    if lower.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        table_block = next((block for block in selected if block.get("type") == "docx_table_row"), None)
        if table_block:
            return docx_table_source_ref(
                filename,
                int(table_block.get("table_index") or 0),
                int(table_block.get("row_index") or 0),
                [str(column) for column in table_block.get("columns", [])],
            )
        return {"source_type": "docx", "source_file": filename, "paragraph_index": start_index, "heading_path": []}
    if lower.endswith(".pdf") or content_type == "application/pdf":
        page = int(selected[0].get("page", 1)) if selected else 1
        return {"source_type": "pdf", "source_file": filename, "page": page}
    line_start = int(selected[0].get("line_start", start_index + 1)) if selected else 1
    line_end = int(selected[-1].get("line_end", end_index + 1)) if selected else max(1, content.count("\n") + 1)
    return {"source_type": "text", "source_file": filename, "line_start": line_start, "line_end": line_end}


def default_pdf_source_ref(filename: str) -> dict[str, Any]:
    return {"source_type": "pdf_diagram", "source_file": filename, "page": 1, "bbox": []}


def source_ref_quality_from_refs(refs: Any) -> str:
    if not isinstance(refs, list) or not refs:
        return "none"
    if any(isinstance(ref, dict) and ref.get("bbox") for ref in refs):
        return "bbox"
    if any(isinstance(ref, dict) and ref.get("sheet") and (ref.get("row_start") or ref.get("row_end")) for ref in refs):
        return "sheet_row"
    if any(isinstance(ref, dict) and ref.get("table_index") is not None and ref.get("row_index") is not None for ref in refs):
        return "table_row"
    if any(isinstance(ref, dict) and ref.get("paragraph_index") is not None for ref in refs):
        return "paragraph_only"
    if any(isinstance(ref, dict) and ref.get("page") for ref in refs):
        return "page_only"
    return "none"


def source_refs_from_chunk(chunk: Any) -> list[dict[str, Any]]:
    metadata = chunk.metadata or {}
    if metadata.get("source_refs"):
        return metadata["source_refs"]
    if metadata.get("sheet_name"):
        return [{"source_type": "excel", "source_file": metadata.get("source_filename", ""), "sheet": metadata.get("sheet_name"), "row_start": metadata.get("row_number"), "row_end": metadata.get("row_number"), "column_names": metadata.get("headers", [])}]
    if metadata.get("page_number") or metadata.get("source_page"):
        return [{"source_type": "pdf", "source_file": metadata.get("source_filename", ""), "page": metadata.get("page_number") or metadata.get("source_page")}]
    return []


def aggregate_source_ref_quality(chunks: list[Any]) -> str:
    qualities = [str(chunk.metadata.get("source_ref_quality") or source_ref_quality_from_refs(chunk.metadata.get("source_refs"))) for chunk in chunks]
    for candidate in ("bbox", "sheet_row", "table_row", "paragraph_only", "page_only", "none"):
        if candidate in qualities:
            return candidate
    return "none"


def stage_artifact(stage: str, artifact_type: str, payload: dict[str, Any], status: str = "completed", error: str = "") -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "error": error,
        "payload": payload,
        "stage": stage,
        "status": status,
    }


def visual_blocks_for_map(visual_layout: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for page in visual_layout.get("pages", []) if isinstance(visual_layout.get("pages"), list) else []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page") or 1)
        for shape in page.get("shape_candidates", []) if isinstance(page.get("shape_candidates"), list) else []:
            if not isinstance(shape, dict):
                continue
            blocks.append(
                {
                    "type": "visual_shape",
                    "page": page_number,
                    "bbox": shape.get("bbox") or [],
                    "index": len(blocks),
                    "text": shape.get("text") or shape.get("shape_type") or "",
                }
            )
        graph = page.get("graph_candidate") if isinstance(page.get("graph_candidate"), dict) else {}
        for edge in graph.get("edge_candidates", []) if isinstance(graph.get("edge_candidates"), list) else []:
            if not isinstance(edge, dict):
                continue
            blocks.append(
                {
                    "type": "visual_connector",
                    "page": page_number,
                    "bbox": edge.get("bbox") or [],
                    "index": len(blocks),
                    "text": f"{edge.get('from_node', '')} --{edge.get('condition', 'next')}--> {edge.get('to_node', '')}",
                }
            )
    return blocks


def visual_layout_payload(visual_layout: dict[str, Any]) -> dict[str, Any]:
    pages = visual_layout.get("pages") if isinstance(visual_layout.get("pages"), list) else []
    return {
        "filename": visual_layout.get("filename", ""),
        "source_type": visual_layout.get("source_type", "pdf_visual_layout"),
        "summary": visual_layout.get("summary", {}),
        "pages": [
            {
                "page": page.get("page"),
                "image_size": page.get("image_size"),
                "text_block_count": len(page.get("text_blocks", [])) if isinstance(page.get("text_blocks"), list) else 0,
                "shape_candidate_count": len(page.get("shape_candidates", [])) if isinstance(page.get("shape_candidates"), list) else 0,
                "connector_candidate_count": len(page.get("connector_candidates", [])) if isinstance(page.get("connector_candidates"), list) else 0,
                "preview_shapes": (page.get("shape_candidates", []) if isinstance(page.get("shape_candidates"), list) else [])[:20],
                "warnings": page.get("warnings", []),
            }
            for page in pages[:3]
            if isinstance(page, dict)
        ],
    }


def visual_graph_payload(visual_layout: dict[str, Any]) -> dict[str, Any]:
    return compact_visual_context(visual_layout)


def source_blocks_payload(filename: str, content_type: str, raw_text: str, blocks: list[dict[str, Any]], raw_context: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    return {
        "block_count": len(blocks),
        "content_type": content_type,
        "filename": filename,
        "docx_table_count": len(raw_context.get("docx_tables", [])) if isinstance(raw_context.get("docx_tables"), list) else 0,
        "preview_blocks": blocks[:60],
        "raw_text_chars": len(raw_text),
        "source_ref_quality": source_ref_quality_from_blocks(blocks),
        "spreadsheet_sheet_count": len(raw_context.get("sheets", [])) if isinstance(raw_context.get("sheets"), list) else 0,
        "warnings": warnings[:20],
    }


def classification_payload(classification: Any) -> dict[str, Any]:
    return {
        "confidence": classification.confidence,
        "document_type": classification.document_type,
        "reasons": classification.warnings,
        "requires_review": classification.requires_review,
        "risk_level": risk_level_for_document_type(classification.document_type),
        "source_type": classification.source_type,
        "signals": classification.warnings,
    }


def ai_structured_payload(source_chunks: list[Any], warnings: list[str]) -> dict[str, Any]:
    return {
        "unit_count": len(source_chunks),
        "unit_types": sorted({str(chunk.metadata.get("unit_type") or chunk.section) for chunk in source_chunks}),
        "warnings": warnings[:30],
    }


def ai_breakdown_payload(breakdowns: list[dict[str, Any]], warnings: list[str], ai_error: str) -> dict[str, Any]:
    attempts = [breakdown for breakdown in breakdowns if isinstance(breakdown, dict)]
    completed = [attempt for attempt in attempts if attempt.get("status") == "completed"]
    failed = [attempt for attempt in attempts if attempt.get("status") == "failed"]
    skipped = [attempt for attempt in attempts if attempt.get("status") == "skipped"]
    return {
        "attempt_count": len(attempts),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "selected_flow": str(completed[-1].get("flow") or "") if completed else "",
        "models": list(dict.fromkeys(str(attempt.get("model") or "") for attempt in attempts if attempt.get("model"))),
        "flows": [str(attempt.get("flow") or "") for attempt in attempts if attempt.get("flow")],
        "warnings": warnings[:60],
        "error": ai_error,
        "attempts": attempts,
    }


def draft_units_payload(source_chunks: list[Any]) -> dict[str, Any]:
    return {
        "unit_count": len(source_chunks),
        "units": [
            {
                "confidence": chunk.metadata.get("confidence"),
                "index": chunk.chunk_index,
                "review_status": chunk.metadata.get("review_status"),
                "source_ref_quality": chunk.metadata.get("source_ref_quality"),
                "title": chunk.heading,
                "unit_type": chunk.metadata.get("unit_type") or chunk.section,
            }
            for chunk in source_chunks[:120]
        ],
    }


def should_create_structuring_plan(document_type: str, raw_text: str, raw_context: dict[str, Any], source_chunks: list[Any]) -> bool:
    sheet_count = len(raw_context.get("sheets", [])) if isinstance(raw_context.get("sheets"), list) else 0
    return (
        document_type in {"policy_table", "workflow_diagram"}
        or (document_type == "policy_rule" and any("high" == str(chunk.metadata.get("risk_level")) for chunk in source_chunks))
        or sheet_count > 1
        or len(raw_text) > 12000
    )


def structuring_plan_payload(classification: Any, source_chunks: list[Any], raw_context: dict[str, Any]) -> dict[str, Any]:
    unit_types = sorted({str(chunk.metadata.get("unit_type") or chunk.section) for chunk in source_chunks})
    sheets = [sheet_name for sheet_name, _rows in raw_context.get("sheets", [])] if isinstance(raw_context.get("sheets"), list) else []
    return {
        "active_vs_historical_candidates": [
            {
                "sheet": sheet,
                "version_scope": version_scope_from_sheet(sheet),
                "effective_from": effective_from_from_sheet(sheet),
            }
            for sheet in sheets
        ],
        "atomic_unit_candidates": unit_types,
        "document_type": classification.document_type,
        "full_sop_candidate": any(unit_type == "full_sop" for unit_type in unit_types),
        "human_approval_required": classification.document_type in {"policy_table", "workflow_diagram", "policy_rule"},
        "metadata_suggestions": {
            "risk_level": risk_level_for_document_type(classification.document_type),
            "source_type": classification.source_type,
        },
        "related_sop_candidates": [],
        "warning_candidates": [chunk.heading for chunk in source_chunks if "warning" in str(chunk.metadata.get("unit_type") or chunk.section) or "note" in str(chunk.metadata.get("unit_type") or chunk.section)][:20],
        "workflow_graph_candidates": [chunk.heading for chunk in source_chunks if str(chunk.metadata.get("unit_type") or chunk.section) == "workflow_graph"][:5],
    }


def verification_report_payload(chunks: list[dict[str, Any]], document_type: str) -> dict[str, Any]:
    hard_blockers: list[str] = []
    warnings: list[str] = []
    metadata_items = [chunk.get("metadata") or {} for chunk in chunks]
    has_full_sop = any(str(metadata.get("unit_type") or "") == "full_sop" or str(metadata.get("retrieval_scope") or "") == "document" for metadata in metadata_items)
    atomic_units = [
        metadata for metadata in metadata_items
        if str(metadata.get("retrieval_scope") or "") != "document"
        and str(metadata.get("unit_type") or "") != "full_sop"
        and not str(metadata.get("unit_type") or "").startswith("candidate_")
    ]
    if not has_full_sop:
        hard_blockers.append("missing_full_sop")
    if document_type in {"policy_rule", "policy_table", "workflow_diagram"} and not atomic_units:
        hard_blockers.append("missing_atomic_units")
    if any(str(metadata.get("review_status") or "needs_review") == "needs_review" for metadata in metadata_items):
        hard_blockers.append("unreviewed_units")
    if any(metadata.get("source_ref_quality") == "page_only" and metadata.get("source_ref_acknowledged") is not True for metadata in metadata_items):
        hard_blockers.append("weak_source_refs_unacknowledged")
    hard_blockers.extend(policy_table_verification_blockers(metadata_items, document_type))
    if any(metadata.get("extraction_status") == "degraded" for metadata in metadata_items):
        hard_blockers.append("degraded_units_require_manual_curation")
    if any(metadata.get("index_eligible") is True and str(metadata.get("review_status")) != "approved" for metadata in metadata_items):
        hard_blockers.append("draft_units_trying_to_index")
    if not any("alias" in json.dumps(metadata, ensure_ascii=False).lower() for metadata in metadata_items):
        warnings.append("weak_aliases")
    if not any("related" in json.dumps(metadata, ensure_ascii=False).lower() for metadata in metadata_items):
        warnings.append("missing_related_sop")
    return {
        "coverage_score": max(0, 100 - len(hard_blockers) * 20 - len(warnings) * 5),
        "hard_blockers": list(dict.fromkeys(hard_blockers)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def policy_table_verification_blockers(metadata_items: list[dict[str, Any]], document_type: str) -> list[str]:
    if document_type not in {"policy_rule", "policy_table"}:
        return []
    is_policy_matrix = any(
        metadata.get("structure_type") == "financial_threshold_matrix"
        or metadata.get("source_ref_quality") == "table_row"
        for metadata in metadata_items
    )
    if not is_policy_matrix:
        return []

    blockers: list[str] = []
    policy_rules = [metadata for metadata in metadata_items if metadata.get("unit_type") == "policy_rule"]
    exception_rules = [metadata for metadata in metadata_items if metadata.get("unit_type") == "exception_rule"]
    expected_policy_count = max([int_or_zero(metadata.get("expected_policy_rule_count")) for metadata in metadata_items] or [0])
    expected_exception_count = max([int_or_zero(metadata.get("expected_exception_rule_count")) for metadata in metadata_items] or [0])
    if expected_policy_count and len(policy_rules) < expected_policy_count:
        blockers.append("missing_policy_rules")
    if expected_exception_count and len(exception_rules) < expected_exception_count:
        blockers.append("missing_exception_rules")
    if policy_rules and any(not metadata.get("rounding_threshold") for metadata in policy_rules):
        blockers.append("missing_threshold_metadata")
    if any(metadata.get("unit_type") in {"policy_rule", "exception_rule", "threshold_rule"} and metadata.get("source_ref_quality") != "table_row" for metadata in metadata_items):
        blockers.append("weak_table_source_refs")
    if any(is_orphan_example_metadata(metadata) for metadata in metadata_items):
        blockers.append("orphan_examples")
    return blockers


def is_orphan_example_metadata(metadata: dict[str, Any]) -> bool:
    unit_type = str(metadata.get("unit_type") or "")
    if unit_type in {"policy_rule", "exception_rule", "threshold_rule", "full_sop"}:
        return False
    text = json.dumps(metadata, ensure_ascii=False).lower()
    return ("->" in text or "=>" in text) and not metadata.get("attached_to")


def int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def source_ref_quality_from_blocks(blocks: list[dict[str, Any]]) -> str:
    if not blocks:
        return "none"
    if any(block.get("bbox") for block in blocks):
        return "bbox"
    if any(block.get("sheet") and block.get("rows") for block in blocks):
        return "sheet_row"
    if any(block.get("type") in {"docx_table_header", "docx_table_row"} for block in blocks):
        return "table_row"
    if any(block.get("paragraph_index") is not None for block in blocks):
        return "paragraph_only"
    if any(block.get("page") for block in blocks):
        return "page_only"
    if any(block.get("line_start") for block in blocks):
        return "paragraph_only"
    return "none"


def risk_level_for_document_type(document_type: str) -> str:
    if document_type in {"policy_rule", "policy_table", "workflow_diagram"}:
        return "high"
    if document_type in {"macro_script", "text_sop"}:
        return "medium"
    return "low"


def first_header_row(rows: list[tuple[int, list[str]]]) -> list[str]:
    for _, values in rows:
        non_empty = [value for value in values if value]
        if len(non_empty) >= 2:
            return values
    return []


def row_is_header(values: list[str], headers: list[str]) -> bool:
    return bool(headers) and [value.strip().lower() for value in values] == [value.strip().lower() for value in headers]


def row_content(values: list[str], headers: list[str]) -> str:
    parts = []
    for index, value in enumerate(values):
        if not value:
            continue
        header = headers[index] if index < len(headers) and headers[index] else f"Column {index + 1}"
        parts.append(f"{header}: {value}")
    return "\n".join(parts)


def effective_from_from_sheet(sheet_name: str) -> str:
    match = re.search(r"(?:từ ngày|tu ngay|from)?\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", sheet_name, re.IGNORECASE)
    if not match:
        return ""
    day, month, year = match.groups()
    if len(year) == 2:
        year = "20" + year
    return f"{year}-{int(month):02d}-{int(day):02d}"


def version_scope_from_sheet(sheet_name: str) -> str:
    normalized = normalize_for_signal(sheet_name)
    if any(term in normalized for term in ["cu", "old", "archive", "archived", "historical", "lich su"]):
        return "historical_candidate"
    if effective_from_from_sheet(sheet_name) or any(term in normalized for term in ["hien tai", "current", "active", "moi"]):
        return "current_candidate"
    return "unknown"


def workflow_step_candidates(raw_text: str) -> list[str]:
    blocks = [line.strip() for line in raw_text.splitlines() if line.strip()]
    candidates = [line for line in blocks if re.match(r"^(\d+(?:\.\d+)*[.)]?|bước\s+\d+|buoc\s+\d+)", line, re.IGNORECASE)]
    if candidates:
        return candidates[:80]
    return [block for block in blocks if contains_signal(block, ["lưu ý", "luu y", "script", "sla", "zt"])][:80]


def preview_document_metadata(
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    raw_text, digest, chunks, warnings, enrichment = prepare_metadata_preview_source(
        filename=filename,
        content_type=content_type,
        data=data,
    )
    suggestion, signals = suggest_metadata(filename, raw_text, chunks, enrichment)
    return {
        "title": suggestion.pop("title"),
        "suggested_metadata": DocumentMetadata(**suggestion),
        "document_type": enrichment["document_type"],
        "source_type": enrichment["source_type"],
        "extraction_confidence": enrichment["extraction_confidence"],
        "chunk_count": len(chunks),
        "warnings": [*warnings, f"checksum:{digest[:12]}"],
        "signals": signals,
    }


def prepare_metadata_preview_source(
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> tuple[str, str, list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    if is_spreadsheet_file(filename.lower(), content_type):
        raw_text, extraction_warnings, source_chunks = extract_spreadsheet(filename.lower(), data)
        warnings.extend(extraction_warnings)
    else:
        raw_text, extraction_warnings = extract_text(filename, content_type, data)
        warnings.extend(extraction_warnings)
        source_chunks = chunk_text(raw_text)

    classification = classify_document(filename, content_type, raw_text)
    warnings.extend(classification.warnings)
    source_chunks = ensure_full_sop_layer(
        source_chunks,
        raw_text,
        filename,
        classification.source_type,
        classification.document_type,
    )

    enrichment = {
        "document_type": classification.document_type,
        "source_type": classification.source_type,
        "review_status": "needs_review",
        "extraction_confidence": classification.confidence,
        "extraction_status": "previewed",
        "extraction_error": "",
        "extraction_warnings": warnings,
    }
    chunks = [
        {
            "chunk_index": chunk.chunk_index,
            "section": chunk.section,
            "heading": chunk.heading,
            "content": chunk.content,
            "token_count": chunk.token_count,
            "metadata": {
                **enrichment,
                "source_filename": filename,
                **chunk.metadata,
            },
        }
        for chunk in source_chunks[:30]
    ]
    return raw_text, checksum(data), chunks, list(dict.fromkeys(warnings)), enrichment


def suggest_metadata(
    filename: str,
    raw_text: str,
    chunks: list[dict[str, Any]],
    enrichment: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    unit_summary = [
        {
            "section": chunk.get("section"),
            "heading": chunk.get("heading"),
            "metadata": chunk.get("metadata", {}),
            "content": str(chunk.get("content", ""))[:500],
        }
        for chunk in chunks[:30]
    ]
    suggestion, signals, warnings = suggest_document_metadata(
        filename,
        raw_text,
        str(enrichment.get("document_type", "unknown")),
        str(enrichment.get("source_type", "upload")),
        unit_summary,
    )
    signals["metadata_warnings"] = warnings
    return suggestion, signals
