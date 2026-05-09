from __future__ import annotations

from typing import Any

from app.embedding import embed_text
from app.openrouter import extract_workflow_units
from app.schemas import DocumentMetadata
from app.text_processing import (
    checksum,
    chunk_text,
    classify_document,
    extract_spreadsheet,
    extract_text,
    extract_workflow_chunks,
    is_spreadsheet_file,
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
        raw_text, warnings, source_chunks = extract_spreadsheet(filename.lower(), data)
    else:
        raw_text, warnings = extract_text(filename, content_type, data)
        source_chunks = []

    classification = classify_document(filename, content_type, raw_text)
    warnings.extend(classification.warnings)
    if not source_chunks:
        if classification.document_type == "workflow_diagram":
            llm_units, llm_warnings = extract_workflow_units(filename, raw_text)
            warnings.extend(llm_warnings)
            source_chunks = workflow_units_to_chunks(llm_units, raw_text, filename) if llm_units else []
            if not source_chunks:
                warnings.append("workflow_heuristic_extraction_used")
                source_chunks = extract_workflow_chunks(raw_text, filename)
        else:
            source_chunks = chunk_text(raw_text)

    enrichment = {
        "document_type": classification.document_type,
        "source_type": classification.source_type,
        "review_status": "needs_review",
        "extraction_confidence": classification.confidence,
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
