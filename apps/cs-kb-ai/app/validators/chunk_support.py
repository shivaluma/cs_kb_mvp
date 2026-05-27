from __future__ import annotations

from typing import Any

from app.ir.schema import EvidenceChunk
from app.validators.evidence import ValidationResult


def validate_chunks_supported(chunks: list[Any]) -> ValidationResult:
    critical: list[str] = []
    warnings: list[str] = []
    checked = 0
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", None)
        chunk_id = getattr(chunk, "chunk_id", None)
        source_element_ids = getattr(chunk, "source_element_ids", None)
        evidence_hash = getattr(chunk, "evidence_hash", None)
        publish_eligible = getattr(chunk, "publish_eligible", None)
        blocked_reasons = getattr(chunk, "blocked_reasons", None)
        if isinstance(metadata, dict):
            if metadata.get("source_evidence_only") is True:
                continue
            chunk_id = chunk_id or str(metadata.get("unit_id") or metadata.get("parent_unit_id") or getattr(chunk, "heading", "chunk"))
            source_element_ids = metadata.get("source_element_ids")
            evidence_hash = metadata.get("evidence_hash")
            publish_eligible = metadata.get("publish_eligible", True)
            blocked_reasons = metadata.get("blocked_reasons") or []
        elif isinstance(chunk, EvidenceChunk):
            chunk_id = chunk.chunk_id
        checked += 1
        if not source_element_ids:
            critical.append(f"{chunk_id}:missing_source_elements")
        if not evidence_hash:
            critical.append(f"{chunk_id}:missing_evidence_hash")
        if publish_eligible is False:
            warnings.append(f"{chunk_id}:publish_ineligible")
        if blocked_reasons:
            warnings.extend(f"{chunk_id}:{reason}" for reason in blocked_reasons)
    return ValidationResult(
        passed=not critical,
        warnings=list(dict.fromkeys(warnings)),
        critical_warnings=list(dict.fromkeys(critical)),
        details={"chunk_count": checked},
    )
