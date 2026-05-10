from __future__ import annotations

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
    workflow_units_to_chunks,
)


def prepare_document_version(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    metadata: DocumentMetadata,
) -> tuple[str, str, list[dict[str, Any]], list[str], dict[str, Any]]:
    if is_spreadsheet_file(filename.lower(), content_type):
        raw_text, warnings, _ = extract_spreadsheet(filename.lower(), data)
        llm_units, llm_warnings = extract_rule_table_units(filename, raw_text)
        warnings.extend(llm_warnings)
        if not llm_units:
            raise ValueError("ai_rule_table_extraction_failed:" + ",".join(llm_warnings))
        source_chunks = ai_units_to_chunks(llm_units, filename, "spreadsheet", "policy_table")
    else:
        raw_text, warnings = extract_text(filename, content_type, data)
        source_chunks = []

    classification = classify_document(filename, content_type, raw_text)
    warnings.extend(classification.warnings)
    if not source_chunks:
        if classification.document_type == "policy_rule":
            llm_units, llm_warnings = extract_rule_table_units(filename, raw_text)
            warnings.extend(llm_warnings)
            if not llm_units:
                raise ValueError("ai_policy_rule_extraction_failed:" + ",".join(llm_warnings))
            source_chunks = ai_units_to_chunks(llm_units, filename, classification.source_type, "policy_rule")
        elif classification.document_type == "workflow_diagram":
            page_images, render_warnings = render_pdf_pages_as_data_urls(data) if filename.lower().endswith(".pdf") or content_type == "application/pdf" else ([], [])
            warnings.extend(render_warnings)
            if not page_images:
                raise ValueError("ai_workflow_extraction_failed:pdf_vision_render_required," + ",".join(render_warnings))
            llm_units, llm_warnings = extract_workflow_units(filename, raw_text, page_images=page_images)
            warnings.extend(llm_warnings)
            source_chunks = workflow_units_to_chunks(llm_units, raw_text, filename) if llm_units else []
            if not source_chunks:
                raise ValueError("ai_workflow_extraction_failed:" + ",".join(llm_warnings))
        else:
            source_chunks = chunk_text(raw_text)

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
        "extraction_status": "extracted",
        "extraction_error": "",
        "extraction_warnings": warnings,
    }

    chunks = []

    for chunk in source_chunks:
        chunk_metadata = {
            **metadata.model_dump(),
            **enrichment,
            "source_filename": filename,
            **chunk.metadata,
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

    if not chunks:
        warnings.append("no_chunks_created")

    return raw_text, checksum(data), chunks, list(dict.fromkeys(warnings)), enrichment


def preview_document_metadata(
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    raw_text, digest, chunks, warnings, enrichment = prepare_document_version(
        filename=filename,
        content_type=content_type,
        data=data,
        metadata=DocumentMetadata(source="metadata_preview"),
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
