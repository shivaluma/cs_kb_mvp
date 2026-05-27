import assert from "node:assert/strict";
import test from "node:test";

import { reviewDetailDisclosureOpen, reviewItemLabel, reviewUnitFacts } from "./extraction-review-editor-model.ts";
import type { ExtractionUnit } from "../types.ts";

test("review unit summary facts avoid raw internal identifiers", () => {
  const unit = extractionUnit({
    confidence: 0.82,
    source_page: 2,
    source_row: 4,
    source_sheet: "Eligibility",
    unit_id: "unit-private-123",
    unit_index: 7,
    unit_type: "policy_rule",
  });

  const facts = reviewUnitFacts(unit);

  assert.deepEqual(facts, ["policy_rule", "82% confidence", "Eligibility", "row 4", "page 2"]);
  assert.ok(!facts.join(" ").includes("unit-private-123"));
  assert.ok(!facts.join(" ").includes("unit 7"));
  assert.equal(reviewItemLabel(unit), "Review item 7");
});

test("advanced edit details stay collapsed until review work needs attention", () => {
  assert.equal(reviewDetailDisclosureOpen({ changed: false, workflowGraphError: "" }), false);
  assert.equal(reviewDetailDisclosureOpen({ changed: true, workflowGraphError: "" }), true);
  assert.equal(reviewDetailDisclosureOpen({ changed: false, workflowGraphError: "Unexpected token" }), true);
});

function extractionUnit(overrides: Partial<ExtractionUnit> = {}): ExtractionUnit {
  return {
    confidence: 0.7,
    content: "Refund after delivery requires CS lead approval.",
    document_id: "doc-1",
    metadata: {},
    review_status: "needs_review",
    title: "Refund approval",
    unit_id: "unit-1",
    unit_index: 1,
    unit_type: "policy_rule",
    version_id: "version-1",
    ...overrides,
  };
}
