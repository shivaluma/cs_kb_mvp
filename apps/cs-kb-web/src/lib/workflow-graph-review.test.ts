import assert from "node:assert/strict";
import test from "node:test";

import {
  workflowDecisionBranchBadge,
  workflowDecisionBranchInstruction,
  workflowDecisionReviewProgressLabel,
  workflowMissingConfirmedEdges,
  workflowTopologyWarningsAcknowledged,
  workflowTopologyIssueCount,
} from "./workflow-graph-review.ts";

test("workflow graph with a graph unit but zero confirmed edges is a blocking review state", () => {
  assert.equal(workflowMissingConfirmedEdges({ confirmedEdgeCount: 0, hasGraphUnit: true }), true);
  assert.equal(workflowMissingConfirmedEdges({ confirmedEdgeCount: 2, hasGraphUnit: true }), false);
  assert.equal(workflowMissingConfirmedEdges({ confirmedEdgeCount: 0, hasGraphUnit: false }), false);
});

test("zero confirmed edges does not render as branches reviewed", () => {
  assert.deepEqual(workflowDecisionBranchBadge({ blockingCount: 0, confirmedEdgeCount: 0 }), {
    label: "no confirmed branches",
    variant: "destructive",
  });
  assert.equal(
    workflowDecisionBranchInstruction({ blockingCount: 0, confirmedEdgeCount: 0 }),
    "No confirmed graph edges were extracted. Re-extract or manually curate the workflow topology before this graph can be treated as reviewed.",
  );
  assert.equal(workflowDecisionReviewProgressLabel({ confirmedEdgeCount: 0, reviewed: 0, total: 0 }), "no confirmed edges");
});

test("missing confirmed graph edges contributes a topology issue", () => {
  assert.equal(
    workflowTopologyIssueCount({
      confirmedEdgeCount: 0,
      hasGraphUnit: true,
      lowConfidence: false,
      uncertainEdgeCount: 0,
      validationIssueCount: 0,
    }),
    1,
  );
  assert.equal(
    workflowTopologyIssueCount({
      confirmedEdgeCount: 4,
      hasGraphUnit: true,
      lowConfidence: true,
      uncertainEdgeCount: 2,
      validationIssueCount: 3,
    }),
    6,
  );
});

test("saved topology acknowledgement cannot clear a graph with no confirmed edges", () => {
  assert.equal(
    workflowTopologyWarningsAcknowledged({
      acknowledgementSaved: true,
      confirmedEdgeCount: 0,
      hasGraphUnit: true,
      issueCount: 1,
    }),
    false,
  );
  assert.equal(
    workflowTopologyWarningsAcknowledged({
      acknowledgementSaved: true,
      confirmedEdgeCount: 4,
      hasGraphUnit: true,
      issueCount: 2,
    }),
    true,
  );
});
