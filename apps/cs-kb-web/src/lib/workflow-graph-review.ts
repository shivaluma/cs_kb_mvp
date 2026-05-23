export type BadgeTone = "destructive" | "outline" | "secondary";

export type WorkflowMissingConfirmedEdgesInput = {
  confirmedEdgeCount: number;
  hasGraphUnit: boolean;
};

export type WorkflowTopologyIssueCountInput = WorkflowMissingConfirmedEdgesInput & {
  lowConfidence: boolean;
  uncertainEdgeCount: number;
  validationIssueCount: number;
};

export type WorkflowDecisionBranchState = {
  blockingCount: number;
  confirmedEdgeCount: number;
};

export type WorkflowDecisionReviewProgress = {
  confirmedEdgeCount: number;
  reviewed: number;
  total: number;
};

export type WorkflowTopologyAcknowledgementState = WorkflowMissingConfirmedEdgesInput & {
  acknowledgementSaved: boolean;
  issueCount: number;
};

export function workflowMissingConfirmedEdges(input: WorkflowMissingConfirmedEdgesInput) {
  return input.hasGraphUnit && input.confirmedEdgeCount === 0;
}

export function workflowTopologyIssueCount(input: WorkflowTopologyIssueCountInput) {
  return (
    input.validationIssueCount +
    input.uncertainEdgeCount +
    (input.lowConfidence ? 1 : 0) +
    (workflowMissingConfirmedEdges(input) ? 1 : 0)
  );
}

export function workflowTopologyWarningsAcknowledged(input: WorkflowTopologyAcknowledgementState) {
  return !workflowMissingConfirmedEdges(input) && (input.issueCount === 0 || input.acknowledgementSaved);
}

export function workflowDecisionBranchBadge(input: WorkflowDecisionBranchState): { label: string; variant: BadgeTone } {
  if (input.confirmedEdgeCount === 0) {
    return { label: "no confirmed branches", variant: "destructive" };
  }
  if (input.blockingCount > 0) {
    return { label: `${input.blockingCount} branch review(s)`, variant: "destructive" };
  }
  return { label: "branches reviewed", variant: "secondary" };
}

export function workflowDecisionBranchInstruction(input: WorkflowDecisionBranchState) {
  if (input.confirmedEdgeCount === 0) {
    return "No confirmed graph edges were extracted. Re-extract or manually curate the workflow topology before this graph can be treated as reviewed.";
  }
  if (input.blockingCount > 0) {
    return "Confirm clear Yes/No edges, or acknowledge ambiguous edges using the saved topology reason.";
  }
  return "Done. Required decision edges are confirmed or acknowledged.";
}

export function workflowDecisionReviewProgressLabel(input: WorkflowDecisionReviewProgress) {
  if (input.confirmedEdgeCount === 0) {
    return "no confirmed edges";
  }
  return `${input.reviewed}/${input.total} reviewed`;
}
