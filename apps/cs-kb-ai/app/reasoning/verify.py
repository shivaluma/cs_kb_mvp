from __future__ import annotations

from app.ir.schema import SemanticUnit
from app.validators.evidence import ValidationResult, validate_semantic_units_supported


def verify_semantic_units(units: list[SemanticUnit]) -> ValidationResult:
    result = validate_semantic_units_supported(units)
    for unit in units:
        unit.validation_status = "passed" if unit.source_element_ids else "blocked"
        if not unit.source_element_ids and "missing_source_elements" not in unit.warnings:
            unit.warnings.append("missing_source_elements")
    return result
