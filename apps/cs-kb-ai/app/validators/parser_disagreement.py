from __future__ import annotations

from app.ir.schema import DocumentEvidenceGraph
from app.validators.evidence import ValidationResult


def validate_parser_disagreements(graph: DocumentEvidenceGraph) -> ValidationResult:
    critical = [
        relation.relation_id
        for relation in graph.relations
        if relation.metadata.get("parser_disagreement") == "unresolved"
    ]
    return ValidationResult(
        passed=not critical,
        critical_warnings=[f"{relation_id}:unresolved_parser_disagreement" for relation_id in critical],
        details={"unresolved_count": len(critical)},
    )
