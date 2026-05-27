from __future__ import annotations

from app.ir.schema import DocumentEvidenceGraph, SemanticUnit


def extract_semantic_units(graph: DocumentEvidenceGraph) -> list[SemanticUnit]:
    units: list[SemanticUnit] = []
    for element in graph.source_elements:
        if element.kind in {"spreadsheet_cell", "graph_edge"}:
            continue
        unit_type = _unit_type_for_element(element.kind, graph.metadata.get("document_type", ""))
        units.append(
            SemanticUnit(
                unit_id=f"unit_{element.element_id}",
                unit_type=unit_type,
                fields={
                    "title": _title_for_element(element.text, unit_type),
                    "content": element.text,
                    "source_refs": element.metadata.get("source_refs") or [],
                },
                source_element_ids=[element.element_id],
                confidence=element.confidence,
                validation_status="pending",
                warnings=[],
            )
        )
    return units


def _unit_type_for_element(element_kind: str, document_type: str) -> str:
    if element_kind == "graph_node":
        return "workflow_step"
    if element_kind == "table_row":
        return "spreadsheet_region" if document_type != "policy_table" else "policy_table"
    if element_kind == "heading":
        return "markdown_section"
    if element_kind in {"paragraph", "list_item", "text"}:
        return "generic_fact"
    return "unknown"


def _title_for_element(text: str, unit_type: str) -> str:
    first_line = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    return first_line[:160] or unit_type.replace("_", " ").title()
