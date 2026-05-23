from __future__ import annotations

import re
from typing import Any

from app.ir.schema import DocumentEvidenceGraph, EvidenceChunk, SemanticUnit, SourceElement, stable_hash
from app.reasoning.extract import extract_semantic_units
from app.text_processing import Chunk, tokenize


def build_evidence_bound_chunks(
    *,
    graph: DocumentEvidenceGraph | None,
    semantic_units: list[SemanticUnit],
) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for unit in semantic_units:
        source_ids = list(dict.fromkeys(unit.source_element_ids))
        evidence_hash = graph.evidence_hash(source_ids) if graph is not None else ""
        blocked_reasons = []
        if not source_ids:
            blocked_reasons.append("missing_source_elements")
        if not evidence_hash:
            blocked_reasons.append("missing_evidence_hash")
        chunks.append(
            EvidenceChunk(
                chunk_id=unit.unit_id,
                chunk_type=unit.unit_type,
                text=str(unit.fields.get("content") or unit.fields.get("text") or ""),
                source_unit_ids=[unit.unit_id],
                source_element_ids=source_ids,
                evidence_hash=evidence_hash,
                confidence=unit.confidence,
                publish_eligible=not blocked_reasons and unit.validation_status != "failed",
                blocked_reasons=blocked_reasons,
                metadata={"validation_status": "passed" if not blocked_reasons else "blocked"},
            )
        )
    return chunks


def legacy_chunks_from_evidence(
    graph: DocumentEvidenceGraph,
    *,
    document_type: str,
    source_type: str,
    existing_count: int = 0,
) -> list[Chunk]:
    units = extract_semantic_units(graph)
    evidence_chunks = build_evidence_bound_chunks(graph=graph, semantic_units=units)
    output: list[Chunk] = []
    for evidence_chunk in evidence_chunks:
        if not evidence_chunk.text.strip():
            continue
        elements = graph.elements_for_ids(evidence_chunk.source_element_ids)
        source_refs = merge_source_refs_from_elements(elements)
        unit_type = _legacy_unit_type(evidence_chunk.chunk_type, document_type, elements)
        heading = _heading(evidence_chunk.text, unit_type)
        metadata = {
            "unit_id": evidence_chunk.chunk_id,
            "unit_type": unit_type,
            "document_type": document_type,
            "source_type": source_type,
            "retrieval_scope": "unit",
            "source_element_ids": evidence_chunk.source_element_ids,
            "evidence_hash": evidence_chunk.evidence_hash,
            "confidence": evidence_chunk.confidence,
            "publish_eligible": evidence_chunk.publish_eligible,
            "blocked_reasons": evidence_chunk.blocked_reasons,
            "validation_status": "passed" if evidence_chunk.publish_eligible else "blocked",
            "source_refs": source_refs,
            "source_ref_quality": _source_ref_quality(source_refs),
            "section_path": _section_path(elements, heading),
            "source_text": evidence_chunk.text,
            "retrieval_text": _retrieval_text(evidence_chunk.text, elements, unit_type),
        }
        if not evidence_chunk.publish_eligible:
            metadata.update(
                {
                    "publish_blocked": True,
                    "publish_blocked_reason": ",".join(evidence_chunk.blocked_reasons) or "missing_source_evidence",
                }
            )
        output.append(
            Chunk(
                chunk_index=existing_count + len(output),
                section=unit_type,
                heading=heading,
                content=evidence_chunk.text,
                token_count=len(tokenize(evidence_chunk.text)),
                metadata=metadata,
            )
        )
    return output


def attach_evidence_metadata_to_legacy_chunks(
    chunks: list[Any],
    graph: DocumentEvidenceGraph,
    *,
    block_missing: bool = True,
) -> list[Any]:
    output = []
    for chunk in chunks:
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        if metadata.get("source_evidence_only") is True:
            output.append(chunk)
            continue
        source_element_ids = metadata.get("source_element_ids")
        if not isinstance(source_element_ids, list) or not source_element_ids:
            source_element_ids = match_chunk_to_source_elements(chunk, graph)
        source_element_ids = list(dict.fromkeys(str(item) for item in source_element_ids if str(item).strip()))
        evidence_hash = graph.evidence_hash(source_element_ids)
        source_refs = metadata.get("source_refs")
        if not isinstance(source_refs, list) or not source_refs:
            source_refs = merge_source_refs_from_elements(graph.elements_for_ids(source_element_ids))
        blocked_reasons = list(metadata.get("blocked_reasons") or [])
        if not source_element_ids and "missing_source_elements" not in blocked_reasons:
            blocked_reasons.append("missing_source_elements")
        if not evidence_hash and "missing_evidence_hash" not in blocked_reasons:
            blocked_reasons.append("missing_evidence_hash")
        publish_eligible = not blocked_reasons
        next_metadata = {
            **metadata,
            "source_element_ids": source_element_ids,
            "evidence_hash": evidence_hash,
            "source_refs": source_refs,
            "source_ref_quality": metadata.get("source_ref_quality") or _source_ref_quality(source_refs),
            "publish_eligible": publish_eligible,
            "blocked_reasons": blocked_reasons,
            "validation_status": "passed" if publish_eligible else "blocked",
        }
        if block_missing and blocked_reasons:
            next_metadata.update(
                {
                    "publish_blocked": True,
                    "publish_blocked_reason": metadata.get("publish_blocked_reason") or ",".join(blocked_reasons),
                }
            )
        output.append(_replace_chunk_metadata(chunk, next_metadata))
    return output


def match_chunk_to_source_elements(chunk: Any, graph: DocumentEvidenceGraph) -> list[str]:
    metadata = dict(getattr(chunk, "metadata", {}) or {})
    refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    if refs:
        ref_matches = [
            element.element_id
            for element in graph.source_elements
            if any(_source_ref_matches_element(ref, element) for ref in refs if isinstance(ref, dict))
        ]
        if ref_matches:
            return ref_matches
    unit_type = str(metadata.get("unit_type") or getattr(chunk, "section", "") or "")
    if unit_type == "full_sop":
        return [element.element_id for element in graph.source_elements if element.text.strip()][:120]
    content = _normalize_text(str(getattr(chunk, "content", "") or ""))
    if not content:
        return []
    matches = []
    for element in graph.source_elements:
        element_text = _normalize_text(element.text)
        if not element_text:
            continue
        if element_text in content or (len(content) <= 240 and content in element_text):
            matches.append(element.element_id)
    return matches[:80]


def merge_source_refs_from_elements(elements: list[SourceElement]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for element in elements:
        element_refs = element.metadata.get("source_refs") if isinstance(element.metadata.get("source_refs"), list) else []
        if element_refs:
            refs.extend(ref for ref in element_refs if isinstance(ref, dict))
            continue
        locator = {key: value for key, value in element.provenance.source_locator.items() if value not in (None, "", [])}
        if locator:
            refs.append(locator)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        key = stable_hash(ref)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def _source_ref_matches_element(ref: dict[str, Any], element: SourceElement) -> bool:
    locator = element.provenance.source_locator
    source_type = str(ref.get("source_type") or "")
    locator_type = str(locator.get("source_type") or "")
    if source_type and locator_type and source_type != locator_type:
        if not ({source_type, locator_type} <= {"markdown", "text"}):
            return False
    if ref.get("sheet") and ref.get("sheet") != (locator.get("sheet") or locator.get("sheet_name")):
        return False
    if ref.get("cell_ref") and ref.get("cell_ref") != locator.get("cell_ref"):
        return False
    if ref.get("paragraph_index") is not None:
        return ref.get("paragraph_index") == locator.get("paragraph_index")
    if ref.get("table_index") is not None and ref.get("row_index") is not None:
        return ref.get("table_index") == locator.get("table_index") and ref.get("row_index") == locator.get("row_index")
    if ref.get("row_start") is not None:
        row = locator.get("row_start") or locator.get("row_index")
        return int(ref.get("row_start") or 0) <= int(row or -1) <= int(ref.get("row_end") or ref.get("row_start") or 0)
    if ref.get("line_start") is not None:
        line = locator.get("line_start")
        return int(ref.get("line_start") or 0) <= int(line or -1) <= int(ref.get("line_end") or ref.get("line_start") or 0)
    if ref.get("page") is not None:
        if int(ref.get("page") or 0) != int(locator.get("page") or element.page_number or 0):
            return False
        ref_bbox = ref.get("bbox")
        locator_bbox = locator.get("bbox") or element.bbox
        if ref_bbox and locator_bbox:
            return ref_bbox == locator_bbox
        return True
    return False


def _legacy_unit_type(chunk_type: str, document_type: str, elements: list[SourceElement]) -> str:
    if chunk_type in {"workflow_step", "workflow_edge", "workflow_path", "decision_branch", "markdown_section", "policy_table"}:
        return chunk_type
    if document_type == "policy_table" and any(element.kind == "table_row" for element in elements):
        return "policy_table"
    if any(element.kind == "table_row" and element.sheet_name for element in elements):
        return "spreadsheet_region"
    if any(element.kind == "heading" for element in elements):
        return "markdown_section"
    return "text_section"


def _heading(text: str, unit_type: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first[:180] or unit_type.replace("_", " ").title()


def _retrieval_text(text: str, elements: list[SourceElement], unit_type: str) -> str:
    prefixes = []
    for element in elements:
        if element.sheet_name:
            prefixes.append(f"Sheet {element.sheet_name}")
        section_path = element.metadata.get("section_path")
        if isinstance(section_path, list) and section_path:
            prefixes.append(" > ".join(str(part) for part in section_path))
    prefix = " | ".join(list(dict.fromkeys(prefixes))[:3])
    return f"{unit_type}. {prefix}. {text}".strip(". ")


def _section_path(elements: list[SourceElement], heading: str) -> list[str]:
    for element in elements:
        path = element.metadata.get("section_path")
        if isinstance(path, list) and path:
            return [str(item) for item in path if str(item).strip()]
    return [heading] if heading else []


def _source_ref_quality(refs: list[dict[str, Any]]) -> str:
    if not refs:
        return "none"
    if any(ref.get("bbox") for ref in refs):
        return "bbox"
    if any(ref.get("sheet") and (ref.get("row_start") or ref.get("cell_ref")) for ref in refs):
        return "sheet_row"
    if any(ref.get("table_index") is not None and ref.get("row_index") is not None for ref in refs):
        return "table_row"
    if any(ref.get("paragraph_index") is not None for ref in refs):
        return "paragraph_only"
    if any(ref.get("line_start") is not None for ref in refs):
        return "line_span"
    if any(ref.get("page") for ref in refs):
        return "page_only"
    return "structured"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _replace_chunk_metadata(chunk: Any, metadata: dict[str, Any]) -> Any:
    return Chunk(
        chunk_index=chunk.chunk_index,
        section=chunk.section,
        heading=chunk.heading,
        content=chunk.content,
        token_count=chunk.token_count,
        metadata=metadata,
    )
