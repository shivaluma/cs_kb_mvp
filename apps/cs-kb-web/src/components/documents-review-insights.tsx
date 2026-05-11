import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Copy, FileJson, GitBranch, Loader2, Search, Terminal, TriangleAlert } from "lucide-react";

import { EmptyPanel, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { DocumentSummary, ExtractionJobSummary, ExtractionPipelineInspection, ExtractionStageOutput, VersionSummary, ExtractionUnit } from "@/types";

type ReadinessCheckLike = {
  detail: string;
  label: string;
  passed: boolean;
};

type WorkflowRequirementLike = {
  key: string;
  label: string;
  types: string[];
};

export type PublishTask = {
  action: string;
  detail: string;
  id: string;
  severity: "blocker" | "warning" | "info";
  title: string;
};

type SopQualityIssue = {
  category: "completeness" | "actionability" | "clarity" | "compliance" | "searchability" | "structure" | "metadata";
  issue: string;
  severity: "critical" | "major" | "minor";
  suggestedFix: string;
};

export type SopQualityAudit = {
  issues: SopQualityIssue[];
  riskLevel: "low" | "medium" | "high";
  score: number;
  status: "good_to_publish" | "minor_revision" | "needs_revision" | "not_ready";
  strengths: string[];
  summary: string;
};

export type DraftPreviewResult = {
  matchedSignals: string[];
  score: number;
  unit: ExtractionUnit;
};

const PIPELINE_STAGES = ["map", "classify", "workflow_semantic_refine", "ai_structure", "plan", "reduce", "refine", "verify", "commit"];

export function ExtractionPipelineTrace({ inspection, jobs, loading }: { inspection: ExtractionPipelineInspection | null; jobs: ExtractionJobSummary[]; loading: boolean }) {
  const job = jobs[0];
  const outputs = inspection?.artifacts ?? job?.outputs ?? [];
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const selectedArtifact = outputs.find((output) => output.id === selectedArtifactId) ?? outputs[0] ?? null;
  const stageSummaries = inspection?.stage_summary?.length
    ? inspection.stage_summary
    : PIPELINE_STAGES.map((stage) => {
        const stageOutputs = outputs.filter((output) => output.stage === stage);
        return {
          artifact_types: stageOutputs.map((output) => output.artifact_type),
          errors: stageOutputs.flatMap((output) => (output.error ? [output.error] : [])),
          output_count: stageOutputs.length,
          stage,
          statuses: stageOutputs.map((output) => output.status),
          summary: stageOutputs[0] ? artifactSummary(stageOutputs[0]) : "No artifact captured for this stage.",
          warnings: [],
        };
      });
  const issueSummary = inspection?.issue_summary;
  const markdownEndpoint = inspection?.version_id
    ? `/api/v1/ai/versions/${inspection.version_id}/extraction-pipeline/inspection.md`
    : "";

  useEffect(() => {
    if (!outputs.length) {
      setSelectedArtifactId("");
      return;
    }
    if (!outputs.some((output) => output.id === selectedArtifactId)) {
      setSelectedArtifactId(outputs[0].id);
    }
  }, [outputs, selectedArtifactId]);

  function copyInspectionReport() {
    if (!inspection?.summary_markdown) {
      return;
    }
    void navigator.clipboard?.writeText(inspection.summary_markdown);
  }

  function copySelectedArtifact() {
    if (!selectedArtifact) {
      return;
    }
    void navigator.clipboard?.writeText(JSON.stringify(selectedArtifact, null, 2));
  }

  return (
    <Card className="rounded-xl">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Extraction inspector</CardTitle>
            <CardDescription>Stage trace, artifact payloads, and copyable API report for debugging one document version.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {loading ? <Badge variant="outline"><Loader2 data-icon="inline-start" className="size-3 animate-spin" /> Loading</Badge> : null}
            {inspection || job ? <Badge variant={(inspection?.status ?? job?.status) === "failed" ? "destructive" : (inspection?.status ?? job?.status) === "degraded" ? "outline" : "secondary"}>{inspection?.status ?? job?.status}</Badge> : <Badge variant="outline">no trace</Badge>}
            {inspection?.current_stage || job?.current_stage ? <Badge variant="outline">{inspection?.current_stage ?? job?.current_stage}</Badge> : null}
            {inspection?.job_id ? <Badge variant="outline">{inspection.job_id.slice(0, 8)}</Badge> : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        {!job && !inspection ? (
          <EmptyPanel icon={GitBranch} title="No pipeline trace yet" text="New uploads will persist source blocks, classification, reconcile suggestions, structuring plan, and verification reports here." compact />
        ) : (
          <>
            <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.45fr)]">
              <div className="rounded-xl border bg-muted/15 p-3">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Terminal className="size-4" />
                    API report
                  </div>
                  <Button disabled={!inspection?.summary_markdown} onClick={copyInspectionReport} size="sm" type="button" variant="outline">
                    <Copy data-icon="inline-start" className="size-3.5" />
                    Copy report
                  </Button>
                </div>
                <p className="break-all font-mono text-xs leading-5 text-muted-foreground">
                  {markdownEndpoint || "Select a version with a persisted extraction job."}
                </p>
                {inspection?.summary_markdown ? (
                  <pre className="mt-3 max-h-44 overflow-auto rounded-lg border bg-background p-3 text-xs leading-5 text-muted-foreground">
                    {inspection.summary_markdown}
                  </pre>
                ) : null}
              </div>

              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                <InspectorMetric label="Failed outputs" tone={issueSummary?.failed_output_count ? "danger" : "normal"} value={String(issueSummary?.failed_output_count ?? 0)} />
                <InspectorMetric label="Degraded outputs" tone={issueSummary?.degraded_output_count ? "warning" : "normal"} value={String(issueSummary?.degraded_output_count ?? 0)} />
                <InspectorMetric label="Warnings" tone={issueSummary?.warning_count ? "warning" : "normal"} value={String(issueSummary?.warning_count ?? 0)} />
                <InspectorMetric label="Coverage" tone={(issueSummary?.coverage_score ?? 100) < 70 ? "warning" : "normal"} value={issueSummary?.coverage_score == null ? "-" : `${issueSummary.coverage_score}/100`} />
              </div>
            </div>

            {issueSummary?.hard_blockers?.length ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-destructive">Publish blockers</p>
                  <Badge variant="destructive">{issueSummary.hard_blockers.length}</Badge>
                </div>
                <p className="mt-2 text-xs leading-5 text-destructive/90">{issueSummary.hard_blockers.join(", ")}</p>
              </div>
            ) : null}

            <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-5">
              {stageSummaries.map((stageSummary) => {
                const failed = stageSummary.statuses.includes("failed");
                const degraded = stageSummary.statuses.includes("degraded");
                return (
                  <div className="rounded-lg border bg-muted/10 p-3" key={stageSummary.stage}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{stageSummary.stage.replace(/_/g, " ")}</span>
                      <Badge variant={failed ? "destructive" : degraded ? "outline" : stageSummary.output_count ? "secondary" : "outline"}>
                        {stageSummary.output_count || "none"}
                      </Badge>
                    </div>
                    <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{stageSummary.summary}</p>
                  </div>
                );
              })}
            </div>

            <div className="grid gap-3 xl:grid-cols-[minmax(18rem,0.45fr)_minmax(0,1fr)]">
              <div className="rounded-xl border bg-muted/10 p-2">
                <div className="mb-2 flex items-center gap-2 px-2 py-1 text-xs font-semibold text-muted-foreground">
                  <FileJson className="size-4" />
                  Artifacts
                </div>
                <div className="grid gap-1">
                  {outputs.map((output) => (
                    <button
                      className={`rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/35 ${selectedArtifact?.id === output.id ? "bg-muted/45" : "bg-background"}`}
                      key={output.id}
                      onClick={() => setSelectedArtifactId(output.id)}
                      type="button"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="min-w-0 truncate text-xs font-semibold">{output.artifact_type.replace(/_/g, " ")}</span>
                        <Badge variant={output.status === "failed" ? "destructive" : output.status === "degraded" ? "outline" : "secondary"}>{output.status}</Badge>
                      </div>
                      <p className="mt-1 truncate text-[11px] text-muted-foreground">{output.stage.replace(/_/g, " ")}</p>
                    </button>
                  ))}
                </div>
              </div>
              {selectedArtifact ? (
                <div className="space-y-3">
                  <PipelineArtifactCard output={selectedArtifact} />
                  <div className="rounded-xl border bg-muted/10 p-3">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="text-sm font-semibold">Raw artifact JSON</h3>
                        <p className="mt-1 text-xs text-muted-foreground">Exact payload persisted by the extraction pipeline.</p>
                      </div>
                      <Button onClick={copySelectedArtifact} size="sm" type="button" variant="outline">
                        <Copy data-icon="inline-start" className="size-3.5" />
                        Copy JSON
                      </Button>
                    </div>
                    <pre className="max-h-[34rem] overflow-auto rounded-lg border bg-background p-3 text-xs leading-5 text-muted-foreground">
                      {JSON.stringify(selectedArtifact, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : null}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function InspectorMetric({ label, tone, value }: { label: string; tone: "danger" | "normal" | "warning"; value: string }) {
  return (
    <div className="rounded-xl border bg-muted/15 p-3">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={tone === "danger" ? "mt-1 text-lg font-semibold text-destructive" : tone === "warning" ? "mt-1 text-lg font-semibold text-amber-700" : "mt-1 text-lg font-semibold"}>
        {value}
      </div>
    </div>
  );
}

function PipelineArtifactCard({ output }: { output: ExtractionStageOutput }) {
  const payload = output.payload ?? {};
  const summaryRows = artifactRows(output);
  const statusTone = output.status === "failed" ? "destructive" : output.status === "degraded" ? "outline" : "secondary";
  return (
    <article className="rounded-xl border bg-muted/10 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{output.stage.replace(/_/g, " ")}</Badge>
            <Badge variant={statusTone}>{output.status}</Badge>
          </div>
          <h3 className="mt-2 text-sm font-semibold">{output.artifact_type.replace(/_/g, " ")}</h3>
        </div>
        <span className="text-xs text-muted-foreground">{new Date(output.created_at).toLocaleString()}</span>
      </div>
      {output.error ? (
        <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-2 text-xs leading-5 text-destructive">
          {output.error}
        </div>
      ) : null}
      <div className="mt-3 grid gap-2">
        {summaryRows.map((row) => (
          <div className="grid gap-2 rounded-lg border bg-background p-2 text-xs md:grid-cols-[8rem_minmax(0,1fr)]" key={row.label}>
            <span className="font-medium text-muted-foreground">{row.label}</span>
            <span className="min-w-0 break-words">{row.value}</span>
          </div>
        ))}
      </div>
      {output.artifact_type === "reconcile_suggestions" ? <ReconcileSuggestions payload={payload} /> : null}
      {output.artifact_type.includes("verification") ? <VerificationReport payload={payload} /> : null}
    </article>
  );
}

function ReconcileSuggestions({ payload }: { payload: Record<string, unknown> }) {
  const groups = [
    ["duplicate_title", "Duplicate title"],
    ["related_sop", "Related SOP"],
    ["possible_conflict", "Possible conflict"],
    ["possible_newer_version", "Existing versions"],
  ] as const;
  return (
    <div className="mt-3 grid gap-2">
      {groups.map(([key, label]) => {
        const items = arrayPayload(payload[key]).slice(0, 3);
        if (!items.length) {
          return null;
        }
        return (
          <section className="rounded-lg border bg-background p-2" key={key}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold">{label}</span>
              <Badge variant="outline">{items.length}</Badge>
            </div>
            <div className="mt-2 grid gap-1.5">
              {items.map((item, index) => (
                <p className="text-xs leading-5 text-muted-foreground" key={`${key}-${index}`}>
                  {stringValue(item["title"] ?? item["version_id"] ?? item["document_id"], "candidate")} · {stringValue(item["reason"], "review required")}
                </p>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function VerificationReport({ payload }: { payload: Record<string, unknown> }) {
  const blockers = stringArrayPayload(payload.hard_blockers);
  const warnings = stringArrayPayload(payload.warnings);
  return (
    <div className="mt-3 grid gap-2 md:grid-cols-2">
      <div className="rounded-lg border bg-background p-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold">Hard blockers</span>
          <Badge variant={blockers.length ? "destructive" : "secondary"}>{blockers.length}</Badge>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{blockers.length ? blockers.slice(0, 5).join(", ") : "None"}</p>
      </div>
      <div className="rounded-lg border bg-background p-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold">Warnings</span>
          <Badge variant="outline">{warnings.length}</Badge>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{warnings.length ? warnings.slice(0, 5).join(", ") : "None"}</p>
      </div>
    </div>
  );
}

function artifactRows(output: ExtractionStageOutput) {
  const payload = output.payload ?? {};
  const rows = [
    { label: "summary", value: artifactSummary(output) },
    { label: "artifact", value: output.artifact_type },
  ];
  if (payload.document_type) rows.push({ label: "doc type", value: stringValue(payload.document_type) });
  if (payload.source_ref_quality) rows.push({ label: "source refs", value: stringValue(payload.source_ref_quality) });
  if (payload.unit_count !== undefined) rows.push({ label: "units", value: stringValue(payload.unit_count) });
  if (payload.block_count !== undefined) rows.push({ label: "blocks", value: stringValue(payload.block_count) });
  if (payload.coverage_score !== undefined) rows.push({ label: "coverage", value: `${stringValue(payload.coverage_score)}/100` });
  return rows.slice(0, 6);
}

function artifactSummary(output: ExtractionStageOutput) {
  const payload = output.payload ?? {};
  if (output.artifact_type === "source_blocks") {
    return `${stringValue(payload.block_count, "0")} blocks, ${stringValue(payload.source_ref_quality, "unknown")} source refs`;
  }
  if (output.artifact_type === "classification_result") {
    return `${stringValue(payload.document_type, "unknown")} · ${stringValue(payload.risk_level, "unknown")} risk · confidence ${stringValue(payload.confidence, "n/a")}`;
  }
  if (output.artifact_type === "reconcile_suggestions") {
    const summary = isRecord(payload.summary) ? payload.summary : {};
    return `${stringValue(summary.duplicate_title_count, "0")} duplicates, ${stringValue(summary.related_sop_count, "0")} related, ${stringValue(summary.possible_conflict_count, "0")} conflicts`;
  }
  if (output.artifact_type === "structuring_plan") {
    return `Plan for ${stringValue(payload.document_type, "document")} with ${arrayLength(payload.atomic_unit_candidates)} unit types`;
  }
  if (output.artifact_type.includes("verification")) {
    return `${stringArrayPayload(payload.hard_blockers).length} blockers, ${stringArrayPayload(payload.warnings).length} warnings`;
  }
  if (payload.unit_count !== undefined) {
    return `${stringValue(payload.unit_count)} unit candidates`;
  }
  return output.error || "Artifact captured";
}

export function buildPublishTasks({
  missingWorkflowUnits,
  pageOnlySourceRefUnacknowledged,
  readinessChecks,
  selectedDocument,
  workflowGraphIssueCount,
  workflowGraphIssuesAcknowledged,
  workflowGraphUnit,
}: {
  missingWorkflowUnits: WorkflowRequirementLike[];
  pageOnlySourceRefUnacknowledged: number;
  readinessChecks: ReadinessCheckLike[];
  selectedDocument: DocumentSummary | null;
  workflowGraphIssueCount: number;
  workflowGraphIssuesAcknowledged: boolean;
  workflowGraphUnit?: ExtractionUnit;
}) {
  if (!selectedDocument) {
    return [];
  }
  const tasks: PublishTask[] = readinessChecks
    .filter((check) => !check.passed)
    .map((check) => ({
      action: readinessActionForCheck(check.label),
      detail: check.detail,
      id: `readiness-${check.label}`,
      severity: readinessSeverityForCheck(check.label),
      title: check.label,
    }));

  if (workflowGraphIssueCount > 0 && !workflowGraphIssuesAcknowledged && !tasks.some((task) => task.id === "graph-topology")) {
    tasks.unshift(...workflowGraphTasks(workflowGraphUnit, workflowGraphIssueCount));
  }

  if (missingWorkflowUnits.length > 0 && !tasks.some((task) => task.id === "workflow-required-units")) {
    tasks.push({
      action: "Use Required workflow units to open existing units, convert a candidate, or add a manual curation stub.",
      detail: missingWorkflowUnits.map((unit) => unit.label).join(", "),
      id: "workflow-required-units",
      severity: "blocker",
      title: "Required workflow units are incomplete",
    });
  }

  if (pageOnlySourceRefUnacknowledged > 0 && !tasks.some((task) => task.id === "source-refs")) {
    tasks.push({
      action: "For each page-only PDF/diagram unit, verify against the source viewer and tick source acknowledgement.",
      detail: `${pageOnlySourceRefUnacknowledged} unit(s) only have page-level traceability.`,
      id: "source-refs",
      severity: "blocker",
      title: "Source references need acknowledgement",
    });
  }

  return tasks;
}

function workflowGraphTasks(graphUnit: ExtractionUnit | undefined, issueCount: number): PublishTask[] {
  if (!graphUnit) {
    return [
      {
        action: "Re-extract or manually curate the workflow graph before publish.",
        detail: "Workflow graph unit is missing.",
        id: "graph-missing",
        severity: "blocker",
        title: "Workflow graph missing",
      },
    ];
  }
  const graphWarningsAcknowledged = graphUnit.metadata.graph_validation_acknowledged === true && Boolean(String(graphUnit.metadata.graph_validation_acknowledged_reason ?? "").trim());
  const graphErrors = !graphWarningsAcknowledged && Array.isArray(graphUnit.metadata.graph_validation_errors)
    ? graphUnit.metadata.graph_validation_errors.map(String)
    : [];
  const edgeReviews = graphUnit.metadata.workflow_edge_reviews;
  const reviews = edgeReviews && typeof edgeReviews === "object" && !Array.isArray(edgeReviews)
    ? edgeReviews as Record<string, { reason?: string; status?: string }>
    : {};
  const graph = graphUnit.metadata.workflow_graph;
  const edges = graph && typeof graph === "object" && !Array.isArray(graph)
    ? ((graph as { edges?: Array<{ condition?: string; from_node?: string; to_node?: string }> }).edges ?? [])
    : [];
  const edgeBlockers = edges
    .filter((edge) => isDecisionEdgeLike(edge))
    .map((edge) => {
      const key = `${String(edge.from_node ?? "").trim()}|${String(edge.condition ?? "").trim().toLowerCase()}|${String(edge.to_node ?? "").trim()}`;
      return { edge, key, review: reviews[key] };
    })
    .filter(({ review }) => !review || !["confirmed", "acknowledged"].includes(String(review.status ?? "")) || (review.status === "acknowledged" && !String(review.reason ?? "").trim()));

  const tasks: PublishTask[] = graphErrors.slice(0, 4).map((error, index) => {
    const parts = error.split(":");
    const sourceNode = parts[1] || "unknown node";
    return {
      action: "Fix the graph if the branch is wrong, or use Acknowledge with reason after comparing against the source page.",
      detail: `Source node: ${sourceNode}. Impact: AI/Search may route the agent to the wrong workflow branch. Raw validation: ${error}.`,
      id: `graph-validation-${index}`,
      severity: "blocker",
      title: "Workflow validation error",
    };
  });

  edgeBlockers.slice(0, 6).forEach(({ edge, key, review }) => {
    tasks.push({
      action: review?.status === "rejected" ? "Fix the graph edge, then mark this branch confirmed." : "Confirm branch if correct, or acknowledge with a reason if source is ambiguous.",
      detail: `Source node: ${edge.from_node || "unknown"} → ${edge.to_node || "unknown"} (${edge.condition || "next"}). Impact: this branch cannot safely power SOP lookup until reviewed.`,
      id: `edge-review-${key}`,
      severity: "blocker",
      title: review?.status === "rejected" ? "Rejected workflow branch" : "Decision branch needs review",
    });
  });

  if (!tasks.length) {
    tasks.push({
      action: "Open Workflow graph, compare branches with the source page, then acknowledge with a reason.",
      detail: `${issueCount} graph topology warning(s) remain unacknowledged.`,
      id: "graph-topology",
      severity: "blocker",
      title: "Workflow topology needs human confirmation",
    });
  }
  return tasks;
}

function isDecisionEdgeLike(edge: { condition?: string; from_node?: string }) {
  const condition = normalizeForSearch(String(edge.condition ?? ""));
  return ["yes", "no", "co", "khong", "dung", "sai"].includes(condition) || condition.includes("no response") || condition.includes("khong phan hoi") || normalizeForSearch(String(edge.from_node ?? "")).includes("decision");
}

export function buildSopQualityAudit({
  atomicUnits,
  effectiveDateReviewed,
  fullSopUnit,
  highRiskUnitCount,
  missingWorkflowUnits,
  ownerAssigned,
  pageOnlySourceRefUnacknowledged,
  pendingReviewCount,
  policyRequiresGovernance,
  readinessChecks,
  selectedDocument,
  selectedVersion,
  validationRuleCount,
  workflowGraphIssueCount,
  workflowGraphIssuesAcknowledged,
  workflowGraphUnit,
  workflowRequiresGraph,
}: {
  atomicUnits: ExtractionUnit[];
  effectiveDateReviewed: boolean;
  fullSopUnit?: ExtractionUnit;
  highRiskUnitCount: number;
  missingWorkflowUnits: WorkflowRequirementLike[];
  ownerAssigned: boolean;
  pageOnlySourceRefUnacknowledged: number;
  pendingReviewCount: number;
  policyRequiresGovernance: boolean;
  readinessChecks: ReadinessCheckLike[];
  selectedDocument: DocumentSummary | null;
  selectedVersion?: VersionSummary;
  validationRuleCount: number;
  workflowGraphIssueCount: number;
  workflowGraphIssuesAcknowledged: boolean;
  workflowGraphUnit?: ExtractionUnit;
  workflowRequiresGraph: boolean;
}): SopQualityAudit {
  if (!selectedDocument) {
    return {
      issues: [],
      riskLevel: "low",
      score: 0,
      status: "not_ready",
      strengths: [],
      summary: "No source document selected.",
    };
  }

  const issues: SopQualityIssue[] = [];
  const strengths: string[] = [];
  const documentType = String(selectedDocument.latest_document_type ?? selectedVersion?.document_type ?? "unknown");
  const riskLevel: SopQualityAudit["riskLevel"] =
    highRiskUnitCount > 0 || documentType.includes("policy") || documentType.includes("workflow") ? "high" : validationRuleCount > 0 ? "medium" : "low";

  if (fullSopUnit) {
    strengths.push("Full SOP layer exists");
  } else {
    issues.push({
      category: "completeness",
      issue: "Missing full SOP page",
      severity: "critical",
      suggestedFix: "Create a document-level full_sop layer so CS can read context, training notes, and audit history.",
    });
  }

  if (atomicUnits.length) {
    strengths.push(`${atomicUnits.length} retrieval units`);
  } else {
    issues.push({
      category: "searchability",
      issue: "No atomic retrieval units",
      severity: "critical",
      suggestedFix: "Split the SOP into rule, step, decision, warning, macro, or table-row units before publish.",
    });
  }

  if (pendingReviewCount > 0) {
    issues.push({
      category: "metadata",
      issue: `${pendingReviewCount} unit(s) still need review`,
      severity: "major",
      suggestedFix: "Filter to Needs review, verify against source evidence, then mark reviewed or approve.",
    });
  } else if (atomicUnits.length) {
    strengths.push("Units reviewed");
  }

  if (workflowRequiresGraph && !workflowGraphUnit) {
    issues.push({
      category: "structure",
      issue: "Workflow diagram has no graph",
      severity: "critical",
      suggestedFix: "Re-extract with workflow extraction or manually curate workflow graph/nodes before publishing.",
    });
  }

  if (workflowGraphIssueCount > 0 && !workflowGraphIssuesAcknowledged) {
    issues.push({
      category: "structure",
      issue: "Workflow graph topology warnings are not acknowledged",
      severity: "critical",
      suggestedFix: "Compare graph branches against source arrows and acknowledge only after human review.",
    });
  } else if (workflowGraphUnit) {
    strengths.push("Workflow graph reviewed");
  }

  if (missingWorkflowUnits.length > 0) {
    issues.push({
      category: "actionability",
      issue: `Missing required workflow units: ${missingWorkflowUnits.map((unit) => unit.label).join(", ")}`,
      severity: "major",
      suggestedFix: "Use the Required workflow units panel to convert candidates or create manual curation stubs.",
    });
  }

  if (pageOnlySourceRefUnacknowledged > 0) {
    issues.push({
      category: "compliance",
      issue: "Page-only source references are not acknowledged",
      severity: "major",
      suggestedFix: "For visual/PDF extractions without bbox, verify each unit against the rendered source page.",
    });
  }

  if (policyRequiresGovernance && !effectiveDateReviewed) {
    issues.push({
      category: "metadata",
      issue: "Policy/rule document has no effective date signal",
      severity: "major",
      suggestedFix: "Add or confirm effective_from before publish so agents do not use stale policy.",
    });
  } else if (effectiveDateReviewed) {
    strengths.push("Effective date signal");
  }

  if (!ownerAssigned) {
    issues.push({
      category: "metadata",
      issue: "Owner team is missing",
      severity: "major",
      suggestedFix: "Assign owner_team to make future review, rollback, and policy escalation accountable.",
    });
  } else {
    strengths.push("Owner assigned");
  }

  if (!hasSearchMetadata(selectedDocument, atomicUnits)) {
    issues.push({
      category: "searchability",
      issue: "Search metadata is thin",
      severity: "minor",
      suggestedFix: "Add tags, aliases, case reasons, or explicit user query terms for better lookup grouping.",
    });
  } else {
    strengths.push("Search metadata present");
  }

  const weakTitles = atomicUnits.filter((unit) => titleLooksLikeContent(unit)).length;
  if (weakTitles > 0) {
    issues.push({
      category: "clarity",
      issue: `${weakTitles} unit title(s) look like copied content`,
      severity: "minor",
      suggestedFix: "Rewrite titles as short operator labels, for example condition/action names instead of full paragraphs.",
    });
  }

  const actionWeakUnits = atomicUnits.filter((unit) => !unitLooksActionable(unit)).length;
  if (actionWeakUnits > 0 && atomicUnits.length > 0) {
    issues.push({
      category: "actionability",
      issue: `${actionWeakUnits} atomic unit(s) may not tell CS what to do next`,
      severity: "minor",
      suggestedFix: "For each rule/step, preserve source text but make the curated content expose condition, action, exception, or warning clearly.",
    });
  }

  const failedReadinessCount = readinessChecks.filter((check) => !check.passed).length;
  let score = 100 - failedReadinessCount * 6;
  issues.forEach((issue) => {
    score -= issue.severity === "critical" ? 16 : issue.severity === "major" ? 9 : 4;
  });
  score = Math.max(0, Math.min(100, score));
  const criticalCount = issues.filter((issue) => issue.severity === "critical").length;
  const status: SopQualityAudit["status"] =
    criticalCount > 0 || score < 50 ? "not_ready" : score < 75 ? "needs_revision" : issues.length ? "minor_revision" : "good_to_publish";

  return {
    issues,
    riskLevel,
    score,
    status,
    strengths,
    summary:
      status === "good_to_publish"
        ? "The SOP has a readable parent layer, searchable units, review coverage, and enough governance metadata for publish."
        : "This audit highlights operational blockers that would make SOP lookup, AI citation, or governance weaker after publish.",
  };
}

export function rankDraftPreviewUnits(query: string, units: ExtractionUnit[]) {
  const normalizedQuery = normalizeForSearch(query);
  if (!normalizedQuery) {
    return [];
  }
  const tokens = normalizedQuery.split(" ").filter((token) => token.length >= 2);
  return units
    .map((unit) => {
      const title = normalizeForSearch(unit.title);
      const content = normalizeForSearch(unit.content);
      const metadata = normalizeForSearch(JSON.stringify(unit.metadata ?? {}));
      const type = normalizeForSearch(unit.unit_type);
      const matchedSignals: string[] = [];
      let score = 0;

      if (title.includes(normalizedQuery)) {
        score += 12;
        matchedSignals.push("exact title");
      }
      if (content.includes(normalizedQuery)) {
        score += 8;
        matchedSignals.push("exact content");
      }
      if (metadata.includes(normalizedQuery)) {
        score += 5;
        matchedSignals.push("metadata");
      }

      tokens.forEach((token) => {
        if (title.includes(token)) {
          score += 2.8;
        }
        if (content.includes(token)) {
          score += 1.4;
        }
        if (metadata.includes(token)) {
          score += 1.2;
        }
        if (type.includes(token)) {
          score += 0.8;
        }
      });

      if (unit.review_status === "approved") {
        score += 1.5;
        matchedSignals.push("approved");
      } else if (unit.review_status === "reviewed") {
        score += 0.8;
        matchedSignals.push("reviewed");
      }
      if (unit.source_page || unit.source_sheet) {
        score += 0.5;
      }
      if (unit.confidence < 0.7) {
        score -= 0.5;
      }

      return {
        matchedSignals: matchedSignals.length ? matchedSignals : ["token match"],
        score,
        unit,
      };
    })
    .filter((result) => result.score > 1)
    .sort((left, right) => right.score - left.score || left.unit.unit_index - right.unit.unit_index)
    .slice(0, 6);
}

export function PublishTaskList({ ready, tasks }: { ready: boolean; tasks: PublishTask[] }) {
  return (
    <Card className="rounded-xl">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Publish task list</CardTitle>
            <CardDescription>Action-first view of what blocks or weakens this SOP before publish.</CardDescription>
          </div>
          <Badge variant={ready ? "secondary" : "destructive"}>{ready ? "ready" : `${tasks.length} task${tasks.length === 1 ? "" : "s"}`}</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 pt-4">
        {tasks.length ? (
          tasks.map((task) => (
            <article className="grid gap-3 rounded-xl border bg-muted/10 p-3 md:grid-cols-[8rem_minmax(0,1fr)]" key={task.id}>
              <div>
                <Badge variant={task.severity === "blocker" ? "destructive" : task.severity === "warning" ? "outline" : "secondary"}>
                  {task.severity}
                </Badge>
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold">{task.title}</h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{task.detail}</p>
                <p className="mt-2 text-xs font-medium text-foreground">Next: {task.action}</p>
              </div>
            </article>
          ))
        ) : (
          <div className="rounded-xl border bg-secondary/30 p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 size-4 text-foreground" />
              <div>
                <p className="text-sm font-semibold">No publish blockers detected</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  Publish can proceed if the source evidence was actually reviewed. Retrieval indexes still only use published approved units.
                </p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SopQualityAuditPanel({ audit }: { audit: SopQualityAudit }) {
  const scoreTone = audit.status === "good_to_publish" || audit.status === "minor_revision" ? "secondary" : audit.status === "needs_revision" ? "outline" : "destructive";
  return (
    <Card className="rounded-xl">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>SOP quality audit</CardTitle>
            <CardDescription>Heuristic review from current draft metadata, not a policy rewrite.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={scoreTone}>{audit.score}/100</Badge>
            <Badge variant="outline">{audit.status.replace(/_/g, " ")}</Badge>
            <Badge variant={audit.riskLevel === "high" ? "destructive" : "outline"}>{audit.riskLevel} risk</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        <p className="text-sm leading-6 text-muted-foreground">{audit.summary}</p>
        {audit.strengths.length ? (
          <div className="flex flex-wrap gap-2">
            {audit.strengths.slice(0, 5).map((strength) => (
              <Badge key={strength} variant="secondary">{strength}</Badge>
            ))}
          </div>
        ) : null}
        {audit.issues.length ? (
          <div className="grid gap-2">
            {audit.issues.slice(0, 6).map((issue, index) => (
              <article className="rounded-lg border bg-muted/10 p-3" key={`${issue.category}-${issue.issue}-${index}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={issue.severity === "critical" ? "destructive" : "outline"}>{issue.severity}</Badge>
                  <Badge variant="outline">{issue.category}</Badge>
                </div>
                <p className="mt-2 text-sm font-medium">{issue.issue}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{issue.suggestedFix}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border bg-secondary/30 p-3 text-sm">No structural quality issues detected from the current draft.</div>
        )}
      </CardContent>
    </Card>
  );
}

export function DraftRetrievalPreview({
  selectedDocument,
  units,
}: {
  selectedDocument: DocumentSummary | null;
  units: ExtractionUnit[];
}) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const isPreviewUpdating = query.trim() !== debouncedQuery.trim();
  const queries = useMemo(
    () => debouncedQuery.split(/\n|;/).map((item) => item.trim()).filter(Boolean).slice(0, 10),
    [debouncedQuery],
  );
  const queryGroups = useMemo(
    () => queries.map((item) => ({
      query: item,
      results: rankDraftPreviewUnits(item, units),
    })),
    [queries, units],
  );
  const matchCount = useMemo(() => queryGroups.reduce((sum, item) => sum + item.results.length, 0), [queryGroups]);

  useEffect(() => {
    const debounceTimer = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(debounceTimer);
  }, [query]);

  return (
    <Card className="rounded-xl">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Draft retrieval preview</CardTitle>
            <CardDescription>Test 5-10 real CS queries before this SOP reaches production search.</CardDescription>
          </div>
          <Badge variant="outline">{isPreviewUpdating ? "updating..." : matchCount ? `${matchCount} matches` : "preview only"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <textarea
            className="min-h-24 w-full resize-y rounded-md border bg-background py-2 pl-9 pr-3 text-sm leading-6 shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            disabled={!selectedDocument}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={"SLA chat social\nkhông có SĐT tạo case\nchuyển SI OB"}
            value={query}
          />
        </div>
        <div className="rounded-lg border bg-muted/15 p-3 text-xs leading-5 text-muted-foreground">
          Draft preview is admin-only. Agent lookup and SOP Chat still require published approved structured units.
        </div>
        {!selectedDocument ? (
          <EmptyPanel icon={Search} title="Select a document" text="Pick a source document to preview retrieval against its draft units." compact />
        ) : !query.trim() ? (
          <EmptyPanel icon={Search} title="Enter test queries" text="Use one real CS phrase per line, including typos, case reasons, and policy keywords." compact />
        ) : isPreviewUpdating && !debouncedQuery.trim() ? (
          <EmptyPanel icon={Search} title="Waiting for input pause" text="Preview runs after typing pauses to keep the review page responsive." compact />
        ) : matchCount ? (
          <div className="grid gap-3">
            {queryGroups.map((group) => (
              <section className="rounded-xl border bg-muted/10 p-3" key={group.query}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">Query: {group.query}</h3>
                  <Badge variant={group.results.length ? "secondary" : "destructive"}>{group.results.length ? `${group.results.length} matches` : "no match"}</Badge>
                </div>
                {group.results.length ? (
                  <div className="mt-3 grid gap-2">
                    {group.results.slice(0, 3).map((result) => (
                      <article className="rounded-lg border bg-background p-3" key={`${group.query}-${result.unit.unit_id}`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="secondary">{result.unit.unit_type}</Badge>
                            <StatusBadge status={result.unit.review_status} />
                            <Badge variant="outline">score {result.score.toFixed(1)}</Badge>
                          </div>
                          <span className="font-mono text-[10px] text-muted-foreground">unit {result.unit.unit_index}</span>
                        </div>
                        <h4 className="mt-2 line-clamp-2 text-sm font-semibold">{result.unit.title}</h4>
                        <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{result.unit.content}</p>
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {result.matchedSignals.slice(0, 4).map((signal) => (
                            <Badge key={signal} variant="outline">{signal}</Badge>
                          ))}
                          {sourceRefLabel(result.unit) ? <Badge variant="outline">{sourceRefLabel(result.unit)}</Badge> : null}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">Likely searchability gap: add aliases/tags, split a clearer unit, or improve unit title.</p>
                )}
              </section>
            ))}
          </div>
        ) : (
          <EmptyPanel icon={TriangleAlert} title="No draft match" text="This is likely a searchability gap: add aliases/tags, split a clearer unit, or improve the unit title." compact />
        )}
      </CardContent>
    </Card>
  );
}

function readinessActionForCheck(label: string) {
  const actions: Record<string, string> = {
    "Atomic retrieval units": "Create or convert searchable atomic units from the source evidence.",
    "Atomic units reviewed": "Filter to Needs review, then mark reviewed or approve after checking source evidence.",
    "Effective date reviewed": "Add or confirm effective_from on the document or relevant high-risk units.",
    "Full SOP page": "Re-extract or manually create a full_sop document layer before publish.",
    "High-risk warning acknowledged": "Add/review risk, validation, warning, or security units from source evidence.",
    "Owner assigned": "Set owner_team so future changes have operational ownership.",
    "Required workflow units": "Complete required workflow units from the dedicated workflow panel.",
    "Selected version": "Inspect the draft version that should be published.",
    "Source refs acknowledged": "Verify page-only source refs in the source viewer and acknowledge them.",
    "Workflow graph reviewed": "Review graph branches, resolve or acknowledge topology warnings, then approve the graph unit.",
  };
  return actions[label] ?? "Resolve this readiness check before publishing.";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function arrayPayload(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function arrayLength(value: unknown) {
  return Array.isArray(value) ? value.length : 0;
}

function stringArrayPayload(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function stringValue(value: unknown, fallback = "") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function readinessSeverityForCheck(label: string): PublishTask["severity"] {
  if (["Owner assigned", "Effective date reviewed", "High-risk warning acknowledged"].includes(label)) {
    return "warning";
  }
  return "blocker";
}

function hasSearchMetadata(document: DocumentSummary, units: ExtractionUnit[]) {
  const documentHaystack = JSON.stringify(document.metadata ?? {}).toLowerCase();
  if (["tag", "alias", "case_reason", "case reason"].some((signal) => documentHaystack.includes(signal))) {
    return true;
  }
  return units.some((unit) => {
    const haystack = JSON.stringify(unit.metadata ?? {}).toLowerCase();
    return ["tag", "alias", "case_reason", "case reason"].some((signal) => haystack.includes(signal));
  });
}

function titleLooksLikeContent(unit: ExtractionUnit) {
  const title = normalizeForSearch(unit.title);
  const content = normalizeForSearch(unit.content);
  return title.length > 90 || (title.length > 35 && content.startsWith(title.slice(0, Math.min(title.length, 60))));
}

function unitLooksActionable(unit: ExtractionUnit) {
  const haystack = normalizeForSearch(`${unit.unit_type} ${unit.title} ${unit.content}`);
  if (["warning", "security_note", "compliance_note", "operational_note", "related_document"].includes(unit.unit_type)) {
    return true;
  }
  return ["neu", "thi", "can", "phai", "khong duoc", "duoc", "xu ly", "kiem tra", "chuyen", "tao", "phan hoi", "xac minh", "gui"].some((token) => haystack.includes(token));
}

function normalizeForSearch(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9?]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function sourceRefLabel(unit: ExtractionUnit) {
  if (unit.source_sheet) {
    return unit.source_row ? `${unit.source_sheet} row ${unit.source_row}` : unit.source_sheet;
  }
  if (unit.source_page) {
    return `page ${unit.source_page}`;
  }
  return "";
}
