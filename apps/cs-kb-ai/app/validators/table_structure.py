from __future__ import annotations

from app.ir.schema import DocumentEvidenceGraph
from app.validators.evidence import ValidationResult


def validate_table_structure(graph: DocumentEvidenceGraph) -> ValidationResult:
    table_cells = [element for element in graph.source_elements if element.kind in {"table_cell", "spreadsheet_cell"}]
    warnings = []
    if table_cells and not any(element.metadata.get("header_path") for element in table_cells):
        warnings.append("table_header_association_not_verified")
    return ValidationResult(passed=True, warnings=warnings, details={"table_cell_count": len(table_cells)})
