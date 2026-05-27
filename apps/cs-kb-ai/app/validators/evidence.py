from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ir.schema import SemanticUnit


@dataclass
class ValidationResult:
    passed: bool
    warnings: list[str] = field(default_factory=list)
    critical_warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "warnings": self.warnings,
            "critical_warnings": self.critical_warnings,
            "details": self.details,
        }


def validate_semantic_units_supported(units: list[SemanticUnit]) -> ValidationResult:
    critical: list[str] = []
    warnings: list[str] = []
    for unit in units:
        if not unit.source_element_ids:
            critical.append(f"{unit.unit_id}:missing_source_elements")
        if unit.validation_status == "failed":
            critical.append(f"{unit.unit_id}:validation_failed")
        if unit.confidence < 0.5:
            warnings.append(f"{unit.unit_id}:low_confidence")
    return ValidationResult(
        passed=not critical,
        warnings=list(dict.fromkeys(warnings)),
        critical_warnings=list(dict.fromkeys(critical)),
        details={"unit_count": len(units)},
    )
