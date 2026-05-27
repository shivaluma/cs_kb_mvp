from __future__ import annotations

from collections import Counter
from typing import Any

from app.ir.schema import DocumentEvidenceGraph


def observe_document(graph: DocumentEvidenceGraph) -> dict[str, Any]:
    kinds = Counter(element.kind for element in graph.source_elements)
    relation_kinds = Counter(relation.kind for relation in graph.relations)
    primary_type = _primary_type(kinds)
    regions = []
    for container in graph.containers:
        element_ids = [element.element_id for element in graph.source_elements if element.container_id == container.container_id]
        if not element_ids:
            continue
        region_kind = _region_kind(container.kind, kinds)
        regions.append(
            {
                "region_id": container.container_id,
                "kind": region_kind,
                "container_ids": [container.container_id],
                "source_element_ids": element_ids,
                "confidence": _region_confidence(graph, element_ids),
                "warnings": _region_warnings(graph, element_ids),
            }
        )
    return {
        "document_profile": {
            "primary_type": primary_type,
            "secondary_types": sorted(kind for kind in kinds if kind != primary_type),
            "confidence": 0.9 if graph.source_elements else 0.0,
        },
        "element_counts": dict(kinds),
        "relation_counts": dict(relation_kinds),
        "low_confidence_element_ids": [element.element_id for element in graph.source_elements if element.confidence < 0.7],
        "regions": regions,
    }


def _primary_type(kinds: Counter[str]) -> str:
    if kinds.get("graph_node") or kinds.get("graph_edge"):
        return "workflow_diagram"
    if kinds.get("spreadsheet_cell") or kinds.get("table_row"):
        return "spreadsheet_region"
    if kinds.get("table") or kinds.get("table_cell"):
        return "policy_table"
    if kinds.get("heading") or kinds.get("paragraph"):
        return "markdown_section"
    if kinds:
        return "generic_text"
    return "unknown"


def _region_kind(container_kind: str, kinds: Counter[str]) -> str:
    if container_kind == "sheet":
        return "spreadsheet_region"
    if container_kind == "page" and (kinds.get("graph_node") or kinds.get("graph_edge")):
        return "workflow_diagram"
    if container_kind == "document" and kinds.get("heading"):
        return "markdown_section"
    return "generic_text"


def _region_confidence(graph: DocumentEvidenceGraph, element_ids: list[str]) -> float:
    elements = graph.elements_for_ids(element_ids)
    if not elements:
        return 0.0
    return round(sum(float(element.confidence or 0) for element in elements) / len(elements), 4)


def _region_warnings(graph: DocumentEvidenceGraph, element_ids: list[str]) -> list[str]:
    warnings = []
    if any(element.confidence < 0.7 for element in graph.elements_for_ids(element_ids)):
        warnings.append("low_confidence_region")
    return warnings
