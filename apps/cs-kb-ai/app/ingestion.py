from __future__ import annotations

from typing import Any

from app.embedding import embed_text
from app.schemas import DocumentMetadata
from app.text_processing import checksum, chunk_text, extract_text


def prepare_document_version(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    metadata: DocumentMetadata,
) -> tuple[str, str, list[dict[str, Any]], list[str]]:
    raw_text, warnings = extract_text(filename, content_type, data)
    chunks = []

    for chunk in chunk_text(raw_text):
        chunk_metadata = {
            **metadata.model_dump(),
            "source_filename": filename,
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

    return raw_text, checksum(data), chunks, warnings
