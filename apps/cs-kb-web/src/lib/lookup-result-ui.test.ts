import assert from "node:assert/strict";
import test from "node:test";

import { sopResultActionLabel, sopResultFacts, sopResultMatchHint } from "./lookup-result-ui.ts";
import type { SearchResult } from "../types.ts";

test("SOP result presentation uses SOP language and hides internal relevance values by default", () => {
  const item = searchResult({
    chunk_type: "policy_rule",
    confidence: 0.94,
    risk_level: "high",
    score: 0.8123,
    section_path: ["Refund", "After delivery"],
  });

  assert.equal(sopResultActionLabel(), "Open in SOP");
  assert.deepEqual(sopResultFacts(item), ["v3", "Refund", "BF", "updated May 22, 2026"]);
  assert.equal(sopResultFacts(item).join(" ").includes("94"), false);
  assert.equal(sopResultFacts(item).join(" ").includes("policy_rule"), false);
  assert.equal(sopResultMatchHint(item), "Matched Refund / After delivery");
});

test("debug SOP result facts can include retrieval diagnostics", () => {
  const item = searchResult({ chunk_type: "policy_rule", score: 0.8123 });

  assert.deepEqual(sopResultFacts(item, { debug: true }).slice(-2), ["policy_rule", "score 0.8123"]);
});

function searchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    audience: ["agent"],
    category: "Refund",
    confidence: 0.7,
    current_version_id: "version-1",
    snippet: "Refund after delivery requires CS lead approval.",
    sop_id: "sop-1",
    tags: [],
    title: "Refund SOP",
    updated_at: "2026-05-22T00:00:00Z",
    version: 3,
    vertical: "BF",
    ...overrides,
  } as SearchResult;
}
