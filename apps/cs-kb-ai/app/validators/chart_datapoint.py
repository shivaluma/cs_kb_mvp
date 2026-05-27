from __future__ import annotations

from app.ir.schema import DocumentEvidenceGraph
from app.validators.evidence import ValidationResult


def validate_chart_datapoints(graph: DocumentEvidenceGraph) -> ValidationResult:
    critical = []
    datapoints = [element for element in graph.source_elements if element.kind == "chart_datapoint"]
    for element in datapoints:
        if not (element.metadata.get("series_label") and element.metadata.get("category_label")):
            critical.append(f"{element.element_id}:missing_chart_labels")
    return ValidationResult(passed=not critical, critical_warnings=critical, details={"chart_datapoint_count": len(datapoints)})
