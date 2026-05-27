import type { ExtractionUnit } from "../types.ts";

export function reviewUnitFacts(unit: ExtractionUnit) {
  return [
    unit.unit_type,
    `${Math.round(unit.confidence * 100)}% confidence`,
    unit.source_sheet,
    unit.source_row ? `row ${unit.source_row}` : null,
    unit.source_page ? `page ${unit.source_page}` : null,
  ].filter((item): item is string => Boolean(item));
}

export function reviewItemLabel(unit: ExtractionUnit) {
  return `Review item ${unit.unit_index}`;
}

export function reviewDetailDisclosureOpen({
  changed,
  workflowGraphError,
}: {
  changed: boolean;
  workflowGraphError: string;
}) {
  return changed || workflowGraphError.trim().length > 0;
}
