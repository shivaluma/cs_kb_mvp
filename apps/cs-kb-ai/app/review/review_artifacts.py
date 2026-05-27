from __future__ import annotations

from typing import Any

from app.ir.schema import DocumentEvidenceGraph


def evidence_graph_artifact(graph: DocumentEvidenceGraph, profile: dict[str, Any]) -> dict[str, Any]:
    payload = graph.to_dict()
    return {
        "summary": {
            "container_count": len(graph.containers),
            "source_element_count": len(graph.source_elements),
            "relation_count": len(graph.relations),
            "document_type": graph.metadata.get("document_type", ""),
            "source_type": graph.metadata.get("source_type", ""),
        },
        "profile": profile,
        "graph": payload,
    }


def evidence_validation_artifact(validation: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = validation.to_dict() if hasattr(validation, "to_dict") else dict(validation or {})
    if extra:
        payload["extra"] = extra
    return payload
