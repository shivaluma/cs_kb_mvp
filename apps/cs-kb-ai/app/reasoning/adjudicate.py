from __future__ import annotations

from typing import Any

from app.ir.schema import DocumentEvidenceGraph


def adjudicate_disagreements(graph: DocumentEvidenceGraph) -> dict[str, Any]:
    unresolved = []
    for relation in graph.relations:
        if relation.metadata.get("parser_disagreement") == "unresolved":
            unresolved.append(relation.relation_id)
    low_confidence = [element.element_id for element in graph.source_elements if element.confidence < 0.5]
    return {
        "status": "blocked" if unresolved else "passed",
        "unresolved_parser_disagreements": unresolved,
        "low_confidence_element_ids": low_confidence,
        "warnings": ["parser_disagreement_unresolved"] if unresolved else [],
    }
