from __future__ import annotations

from app.ir.schema import DocumentEvidenceGraph
from app.validators.evidence import ValidationResult


def validate_spreadsheet_semantics(graph: DocumentEvidenceGraph) -> ValidationResult:
    critical = []
    spreadsheet_elements = [element for element in graph.source_elements if element.kind in {"spreadsheet_cell", "table_row"}]
    for element in spreadsheet_elements:
        locator = element.provenance.source_locator
        if not (locator.get("sheet") or locator.get("sheet_name")):
            critical.append(f"{element.element_id}:missing_sheet_locator")
        if element.kind == "spreadsheet_cell" and not locator.get("cell_ref"):
            critical.append(f"{element.element_id}:missing_cell_ref")
    return ValidationResult(passed=not critical, critical_warnings=list(dict.fromkeys(critical)), details={"spreadsheet_element_count": len(spreadsheet_elements)})
