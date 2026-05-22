import assert from "node:assert/strict";
import test from "node:test";

import { chatWarningLabels } from "./chat-warnings.ts";

test("chat warning labels hide retrieval diagnostics from normal users", () => {
  const labels = chatWarningLabels(
    [
      "grounded_published_sop_units_only",
      "query_understanding_failed:ValueError",
      "index_query_understanding_failed:ValueError",
      "no_reliable_source",
      "conflict_detected:primary_policy_conflict",
      "matched_source_has_unresolved_dependency",
      "no_approved_relation_expansion",
      "openrouter_grounded_answer_used",
    ],
    false,
  );

  assert.deepEqual(labels.userWarnings, [
    "Answer is limited to published SOP evidence.",
    "Not enough published SOP evidence.",
    "SOP guidance may conflict. Review with owner/QA.",
    "Source references an unapproved related SOP. Do not use that related document unless the relation is approved.",
  ]);
  assert.deepEqual(labels.debugWarnings, []);
});

test("chat warning labels keep raw diagnostics available in debug mode", () => {
  const labels = chatWarningLabels(
    [
      "query_understanding_failed:ValueError",
      "index_query_understanding_failed:ValueError",
      "matched_source_has_unresolved_dependency",
    ],
    true,
  );

  assert.deepEqual(labels.userWarnings, [
    "Source references an unapproved related SOP. Do not use that related document unless the relation is approved.",
  ]);
  assert.ok(labels.debugWarnings.includes("query understanding failed:ValueError"));
  assert.ok(labels.debugWarnings.includes("index query understanding failed:ValueError"));
});
