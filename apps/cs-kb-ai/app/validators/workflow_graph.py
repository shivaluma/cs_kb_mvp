from __future__ import annotations

from app.ir.schema import DocumentEvidenceGraph
from app.validators.evidence import ValidationResult


def validate_workflow_graph(graph: DocumentEvidenceGraph) -> ValidationResult:
    critical: list[str] = []
    warnings: list[str] = []
    edge_count = 0
    for element in graph.source_elements:
        if element.kind != "graph_edge":
            continue
        edge_count += 1
        refs = element.metadata.get("source_refs") if isinstance(element.metadata.get("source_refs"), list) else []
        if not any(_has_page_bbox(ref) for ref in refs):
            critical.append("workflow_edge_missing_source_ref")
        if element.metadata.get("from_node_id") and element.metadata.get("to_node_id"):
            continue
        critical.append("workflow_edge_unresolved_endpoint")
    unknown_edges = [
        relation.relation_id
        for relation in graph.relations
        if relation.kind == "flows_to" and relation.metadata.get("missing_edge_evidence")
    ]
    if unknown_edges:
        critical.append("workflow_unknown_edges")
    return ValidationResult(
        passed=not critical,
        warnings=list(dict.fromkeys(warnings)),
        critical_warnings=list(dict.fromkeys(critical)),
        details={"edge_count": edge_count, "unknown_edges": unknown_edges},
    )


def _has_page_bbox(ref: object) -> bool:
    if not isinstance(ref, dict):
        return False
    bbox = ref.get("bbox")
    return bool(ref.get("page") and isinstance(bbox, list) and len(bbox) >= 4)
