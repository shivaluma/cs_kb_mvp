from __future__ import annotations

import json
import re
from typing import Any

from app.embedding import embed_text
from app.openrouter import extract_rule_table_units, extract_workflow_units, suggest_document_metadata
from app.schemas import DocumentMetadata
from app.text_processing import (
    ai_units_to_chunks,
    checksum,
    chunk_text,
    classify_document,
    ensure_full_sop_layer,
    extract_spreadsheet,
    extract_text,
    is_spreadsheet_file,
    render_pdf_pages_as_data_urls,
    spreadsheet_rows,
    tokenize,
    workflow_units_to_chunks,
)
from app.visual_layout import compact_visual_context, extract_pdf_visual_layout


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

    source_chunks: list[Any] = []
    ai_error = ""
    if classification.document_type in {"policy_rule", "policy_table", "workflow_diagram"}:
        source_chunks, ai_warnings, ai_error = try_ai_structuring(
            filename=filename,
            content_type=content_type,
            data=data,
            raw_text=raw_text,
            classification=classification,
            visual_layout=visual_layout,
        )
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
) -> tuple[list[Any], list[str], str]:
    warnings: list[str] = []
    try:
        if classification.document_type in {"policy_rule", "policy_table"}:
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
            visual_context = compact_visual_context(visual_layout) if visual_layout else None
            if visual_context:
                warnings.append("visual_graph_context_supplied_to_llm")
            llm_units, llm_warnings = extract_workflow_units(filename, raw_text, page_images=page_images, visual_context=visual_context)
            warnings.extend(llm_warnings)
            chunks = workflow_units_to_chunks(llm_units, raw_text, filename) if llm_units else []
            if not chunks:
                return [], warnings, f"ai_workflow_structuring_failed:{','.join(llm_warnings)}"
            return mark_structured_chunks(chunks), warnings, ""
    except Exception as exc:
        return [], warnings, f"ai_structuring_exception:{sanitize_ai_error(exc)}"
    return [], warnings, ""


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
        if has_rule:
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
                    "source_refs": [source_ref_for_text_block(filename, content_type, blocks, group[0]["index"], group[-1]["index"], text)],
                },
                classification,
                ai_error,
            )
        )
        if has_warning and unit_type != "candidate_warning":
            chunks.append(
                degraded_chunk(
                    len(chunks),
                    "candidate_warning",
                    candidate_heading(text, "candidate_warning", group_index),
                    text,
                    {
                        "unit_type": "candidate_warning",
                        "retrieval_scope": "unit",
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


def build_degraded_workflow_draft(filename: str, raw_text: str, blocks: list[dict[str, Any]], raw_context: dict[str, Any], classification: Any, ai_error: str) -> list[Any]:
    visual_layout = raw_context.get("visual_layout") if isinstance(raw_context.get("visual_layout"), dict) else {}
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
        starts_new = is_heading_like_text(text) or current_len + len(text) > max_chars
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
        "candidate_rule": "Candidate rule",
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
    for candidate in ("bbox", "sheet_row", "paragraph_only", "page_only", "none"):
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


def source_ref_quality_from_blocks(blocks: list[dict[str, Any]]) -> str:
    if not blocks:
        return "none"
    if any(block.get("bbox") for block in blocks):
        return "bbox"
    if any(block.get("sheet") and block.get("rows") for block in blocks):
        return "sheet_row"
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
