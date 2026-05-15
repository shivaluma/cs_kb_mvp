import { useEffect, useMemo, useState } from "react";
import {
  IconCircleCheck as CheckCircle2,
  IconRotate as RotateCcw,
  IconDeviceFloppy as Save
} from "@tabler/icons-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ExtractionUnit, ExtractionUnitUpdate } from "@/types";

const UNIT_TYPES = [
  "full_sop",
  "workflow_overview",
  "workflow_graph",
  "verification_dependency",
  "decision_point",
  "decision_rule",
  "workflow_step",
  "operational_instruction",
  "routing_rule",
  "policy_rule",
  "sla_rule",
  "escalation_rule",
  "case_creation_rule",
  "handoff_rule",
  "macro_table",
  "macro_script",
  "wording_rule",
  "operational_note",
  "security_note",
  "compliance_note",
  "compliance_rule",
  "warning",
  "example",
  "related_document",
  "issue_router_unit",
  "quick_action_rule",
  "sop_reference",
  "tool_link",
  "vip_overlay_rule",
  "product_update_note",
  "validation_rule",
  "handling_rule",
  "follow_up_rule",
  "rule_table_row",
  "text_section",
  "candidate_section",
  "candidate_rule",
  "candidate_warning",
  "candidate_table_row",
  "candidate_workflow_text",
  "candidate_step",
];

type Draft = {
  title: string;
  content: string;
  unitType: string;
  confidence: string;
  reviewStatus: ExtractionUnit["review_status"];
  riskLevel: string;
  reviewFrequency: string;
  lastReviewedAt: string;
  nextReviewDue: string;
  effectiveFrom: string;
  sourceRefAcknowledged: boolean;
  workflowGraphJson: string;
};

export function ExtractionReviewEditor({
  defaultEffectiveFrom,
  documentGovernance,
  disabled,
  onSave,
  saving,
  unit,
}: {
  defaultEffectiveFrom?: string;
  documentGovernance?: {
    riskLevel: string;
    reviewFrequency: string;
    lastReviewedAt: string;
    nextReviewDue: string;
  };
  disabled: boolean;
  onSave: (unit: ExtractionUnit, update: ExtractionUnitUpdate) => void;
  saving: boolean;
  unit: ExtractionUnit;
}) {
  const initialDraft = useMemo(() => unitToDraft(unit), [unit]);
  const [draft, setDraft] = useState<Draft>(initialDraft);
  const normalizedSearchLabel = meaningfulSearchLabel(draft.title, draft.content, draft.unitType);
  const searchLabelWillNormalize = normalizedSearchLabel !== draft.title.trim();

  useEffect(() => {
    setDraft(initialDraft);
  }, [initialDraft]);

  const changed = JSON.stringify(draft) !== JSON.stringify(initialDraft) || normalizedSearchLabel !== initialDraft.title.trim();
  const workflowGraphError = workflowGraphJsonError(draft.workflowGraphJson);
  const valid = normalizedSearchLabel.length > 0 && draft.content.trim().length > 0 && Number.isFinite(Number(draft.confidence)) && !workflowGraphError;
  const confidence = Math.max(0, Math.min(Number(draft.confidence) || 0, 1));

  function buildUpdate(reviewStatus = draft.reviewStatus): ExtractionUnitUpdate {
    const workflowGraph = parseWorkflowGraphJson(draft.workflowGraphJson);
    const workflowGraphPatch = workflowGraph ? workflowGraphMetadataPatch(workflowGraph) : {};
    const autoReviewing = reviewStatus === "reviewed" || reviewStatus === "approved";
    const effectiveFrom = draft.effectiveFrom || defaultEffectiveFrom || "";
    return {
      title: normalizedSearchLabel,
      content: draft.content.trim(),
      unit_type: draft.unitType,
      confidence,
      review_status: reviewStatus,
      actor: "cs-ops-ui",
      metadata: {
        ...unit.metadata,
        risk_level: draft.riskLevel,
        review_frequency: draft.reviewFrequency,
        last_reviewed_at: draft.lastReviewedAt,
        next_review_due: draft.nextReviewDue,
        effective_from: effectiveFrom,
        source_ref_acknowledged: autoReviewing && unit.metadata.source_ref_quality === "page_only" ? true : draft.sourceRefAcknowledged,
        ...workflowGraphPatch,
      },
    };
  }

  function save() {
    onSave(unit, buildUpdate());
  }

  function transitionReviewStatus(reviewStatus: ExtractionUnit["review_status"]) {
    onSave(unit, {
      ...buildUpdate(reviewStatus),
      review_status: reviewStatus,
    });
  }

  return (
    <article
      className={cn("rounded-xl border bg-card p-4", changed && "border-primary/60 bg-primary/5", disabled && "bg-muted/20")}
      data-testid={`extraction-unit-${unit.unit_id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{unit.unit_type}</Badge>
          <Badge variant={unit.review_status === "approved" ? "secondary" : unit.review_status === "reviewed" ? "outline" : "destructive"}>
            {unit.review_status}
          </Badge>
          <Badge variant="outline">{Math.round(unit.confidence * 100)}% confidence</Badge>
          {unit.source_sheet ? <Badge variant="outline">{unit.source_sheet}</Badge> : null}
          {unit.source_row ? <Badge variant="outline">row {unit.source_row}</Badge> : null}
          {unit.source_page ? <Badge variant="outline">page {unit.source_page}</Badge> : null}
          {disabled ? <Badge variant="outline">read-only published version</Badge> : null}
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">unit {unit.unit_index}</span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_11rem_9rem]">
        <div className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Search label
          <Input
            disabled={disabled}
            onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
            placeholder="Short label for cards and search"
            value={draft.title}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] leading-4 text-muted-foreground">
            <span>
              {searchLabelWillNormalize
                ? `Will save as: ${normalizedSearchLabel}`
                : "Used for source cards and retrieval weighting."}
            </span>
            {searchLabelWillNormalize && !disabled ? (
              <Button
                className="h-6 px-2 text-[11px]"
                onClick={() => setDraft((current) => ({ ...current, title: normalizedSearchLabel }))}
                type="button"
                variant="ghost"
              >
                Use generated label
              </Button>
            ) : null}
          </div>
        </div>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Unit type
          <Select
            disabled={disabled}
            onValueChange={(unitType) => setDraft((current) => ({ ...current, unitType }))}
            value={draft.unitType}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {UNIT_TYPES.map((type) => (
                <SelectItem key={type} value={type}>{type}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Confidence
          <Input
            disabled={disabled}
            max="1"
            min="0"
            onChange={(event) => setDraft((current) => ({ ...current, confidence: event.target.value }))}
            step="0.01"
            type="number"
            value={draft.confidence}
          />
        </label>
      </div>

      <label className="mt-3 grid gap-1.5 text-xs font-medium text-muted-foreground">
        Unit content
        <textarea
          className="min-h-28 rounded-xl border border-input bg-background px-3 py-2 text-sm leading-6 shadow-xs outline-none transition-[border-color,box-shadow] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={disabled}
          onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
          value={draft.content}
        />
      </label>

      {unit.metadata.workflow_graph ? (
        <label className="mt-3 grid gap-1.5 text-xs font-medium text-muted-foreground">
          Workflow graph JSON
          <textarea
            className={cn(
              "min-h-44 rounded-xl border border-input bg-background px-3 py-2 font-mono text-xs leading-5 shadow-xs outline-none transition-[border-color,box-shadow] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50",
              workflowGraphError && "border-destructive focus-visible:border-destructive focus-visible:ring-destructive/20",
            )}
            disabled={disabled}
            onChange={(event) => setDraft((current) => ({ ...current, workflowGraphJson: event.target.value }))}
            spellCheck={false}
            value={draft.workflowGraphJson}
          />
          <span className={cn("text-[11px] leading-4 text-muted-foreground", workflowGraphError && "text-destructive")}>
            {workflowGraphError || "Edit nodes, edges, annotations, and validation errors. Invalid JSON cannot be saved."}
          </span>
        </label>
      ) : null}

      {unit.metadata.source_ref_quality === "page_only" ? (
        <div className="mt-3 rounded-xl border border-amber-300/70 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          <p className="font-medium">Page-only source reference</p>
          <p className="mt-1 text-xs leading-5">
            This PDF/diagram unit has page-level trace only, no bbox. Publish requires CS Ops to verify this unit against the source page.
          </p>
          <label className="mt-2 flex items-center gap-2 text-xs font-medium">
            <input
              checked={draft.sourceRefAcknowledged}
              className="size-4 rounded border-input"
              disabled={disabled}
              onChange={(event) => setDraft((current) => ({ ...current, sourceRefAcknowledged: event.target.checked }))}
              type="checkbox"
            />
            I verified this unit against the source page
          </label>
        </div>
      ) : null}

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Review status
          <Select
            disabled={disabled}
            onValueChange={(reviewStatus) => setDraft((current) => ({ ...current, reviewStatus: reviewStatus as ExtractionUnit["review_status"] }))}
            value={draft.reviewStatus}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="needs_review">needs_review</SelectItem>
              <SelectItem value="reviewed">reviewed</SelectItem>
              <SelectItem value="approved">approved</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Risk level
          <Select
            disabled={disabled}
            onValueChange={(riskLevel) => setDraft((current) => ({ ...current, riskLevel: riskLevel === "inherit" ? "" : riskLevel }))}
            value={draft.riskLevel || "inherit"}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="inherit">{inheritedLabel(documentGovernance?.riskLevel)}</SelectItem>
              <SelectItem value="low">low</SelectItem>
              <SelectItem value="medium">medium</SelectItem>
              <SelectItem value="high">high</SelectItem>
              <SelectItem value="critical">critical</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Effective from
          <Input
            disabled={disabled}
            onChange={(event) => setDraft((current) => ({ ...current, effectiveFrom: event.target.value }))}
            placeholder="2025-04-22"
            value={draft.effectiveFrom}
          />
        </label>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Review frequency
          <Select
            disabled={disabled}
            onValueChange={(reviewFrequency) => setDraft((current) => ({ ...current, reviewFrequency: reviewFrequency === "inherit" ? "" : reviewFrequency }))}
            value={draft.reviewFrequency || "inherit"}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="inherit">{inheritedLabel(documentGovernance?.reviewFrequency)}</SelectItem>
              <SelectItem value="quarterly">quarterly</SelectItem>
              <SelectItem value="semiannual">semiannual</SelectItem>
              <SelectItem value="annual">annual</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Last reviewed
          <Input
            disabled={disabled}
            onChange={(event) => setDraft((current) => ({ ...current, lastReviewedAt: event.target.value }))}
            placeholder={documentGovernance?.lastReviewedAt ? `inherits ${documentGovernance.lastReviewedAt}` : "YYYY-MM-DD"}
            value={draft.lastReviewedAt}
          />
        </label>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Next review due
          <Input
            disabled={disabled}
            onChange={(event) => setDraft((current) => ({ ...current, nextReviewDue: event.target.value }))}
            placeholder={documentGovernance?.nextReviewDue ? `inherits ${documentGovernance.nextReviewDue}` : "YYYY-MM-DD"}
            value={draft.nextReviewDue}
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs leading-5 text-muted-foreground">
          {disabled
            ? "Published versions are immutable. Create a new draft version to edit."
            : changed
              ? "Unsaved changes will refresh the embedding after save."
              : "No unsaved changes. Use review actions to move this unit through curation."}
        </p>
        <div className="flex items-center gap-2">
          {draft.reviewStatus === "reviewed" || draft.reviewStatus === "approved" ? (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <CheckCircle2 className="size-3.5" />
              reviewed
            </span>
          ) : null}
          {!disabled && unit.review_status === "needs_review" ? (
            <Button
              data-testid={`extraction-unit-${unit.unit_id}-mark-reviewed`}
              disabled={saving || !valid}
              onClick={() => transitionReviewStatus("reviewed")}
              size="sm"
              type="button"
              variant="outline"
            >
              Mark reviewed
            </Button>
          ) : null}
          {!disabled && unit.review_status !== "approved" ? (
            <Button
              data-testid={`extraction-unit-${unit.unit_id}-approve`}
              disabled={saving || !valid}
              onClick={() => transitionReviewStatus("approved")}
              size="sm"
              type="button"
              variant="outline"
            >
              Approve
            </Button>
          ) : null}
          <Button
            data-testid={`extraction-unit-${unit.unit_id}-reset`}
            disabled={!changed || saving}
            onClick={() => setDraft(initialDraft)}
            size="sm"
            type="button"
            variant="outline"
          >
            <RotateCcw data-icon="inline-start" className="size-4" />
            Reset
          </Button>
          <Button
            data-testid={`extraction-unit-${unit.unit_id}-save`}
            disabled={disabled || !changed || !valid || saving}
            onClick={save}
            size="sm"
            type="button"
          >
            <Save data-icon="inline-start" className="size-4" />
            {saving ? "Saving" : "Save changes"}
          </Button>
        </div>
      </div>
    </article>
  );
}

function unitToDraft(unit: ExtractionUnit): Draft {
  return {
    title: unit.title,
    content: unit.content,
    unitType: unit.unit_type,
    confidence: String(unit.confidence || 0),
    reviewStatus: unit.review_status,
    riskLevel: String(unit.metadata.risk_level ?? ""),
    reviewFrequency: String(unit.metadata.review_frequency ?? ""),
    lastReviewedAt: String(unit.metadata.last_reviewed_at ?? ""),
    nextReviewDue: String(unit.metadata.next_review_due ?? ""),
    effectiveFrom: String(unit.metadata.effective_from ?? ""),
    sourceRefAcknowledged: unit.metadata.source_ref_acknowledged === true,
    workflowGraphJson: unit.metadata.workflow_graph ? JSON.stringify(unit.metadata.workflow_graph, null, 2) : "",
  };
}

function meaningfulSearchLabel(label: string, content: string, unitType: string) {
  const cleanLabel = compactText(label);
  const cleanContent = compactText(content);
  if (!isWeakSearchLabel(cleanLabel, cleanContent)) {
    return cleanLabel.slice(0, 180);
  }
  return generatedSearchLabel(cleanContent, unitType).slice(0, 180);
}

function isWeakSearchLabel(label: string, content: string) {
  const cleanLabel = compactText(label);
  if (!cleanLabel) {
    return true;
  }
  const normalizedLabel = normalizeSearchText(cleanLabel);
  const normalizedContent = normalizeSearchText(content);
  if (/^(?:buoc\s*)?\d{1,3}(?:\.\d{1,3})*\.?$/.test(normalizedLabel)) {
    return true;
  }
  if (["yes", "no", "start", "end", "row", "dong", "link"].includes(normalizedLabel)) {
    return true;
  }
  if (cleanLabel.length > 110) {
    return true;
  }
  if (normalizedContent && normalizedLabel.length >= 8 && normalizedContent.startsWith(normalizedLabel)) {
    return true;
  }
  return false;
}

function generatedSearchLabel(content: string, unitType: string) {
  const [stepCode, body] = splitLeadingStep(content);
  const summary = trimWords(firstSentence(body || content), 10);
  if (stepCode && summary) {
    return unitType.includes("decision") || summary.endsWith("?")
      ? `Điều kiện ${stepCode}: ${summary}`
      : `Bước ${stepCode}: ${summary}`;
  }
  const prefix = unitTypeLabel(unitType);
  return summary && !normalizeSearchText(summary).startsWith(normalizeSearchText(prefix))
    ? `${prefix}: ${summary}`
    : summary || prefix;
}

function splitLeadingStep(content: string): [string, string] {
  const match = content.match(/^\s*(?:bước\s*)?(\d{1,3}(?:\.\d{1,3})*)[.)]?\s*/i);
  if (!match) {
    return ["", content];
  }
  return [match[1] ?? "", content.slice(match[0].length).trim()];
}

function firstSentence(value: string) {
  return compactText(value).split(/[.;\n]/, 1)[0] ?? compactText(value);
}

function trimWords(value: string, limit: number) {
  const words = compactText(value).split(/\s+/).filter(Boolean);
  return words.slice(0, limit).join(" ");
}

function unitTypeLabel(unitType: string) {
  const labels: Record<string, string> = {
    decision_point: "Điều kiện",
    decision_rule: "Điều kiện",
    workflow_step: "Bước xử lý",
    operational_instruction: "Hướng dẫn",
    routing_rule: "Điều hướng",
    policy_rule: "Quy định",
    handling_rule: "Xử lý",
    macro_table: "Bảng macro",
    macro_script: "Script",
    wording_rule: "Wording",
    sla_rule: "SLA",
    handoff_rule: "Handoff",
    compliance_rule: "Tuân thủ",
    warning: "Cảnh báo",
    example: "Ví dụ",
    operational_note: "Lưu ý",
    related_document: "Tài liệu liên quan",
  };
  return labels[unitType] ?? (compactText(unitType.replace(/_/g, " ")) || "Search label");
}

function compactText(value: string) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeSearchText(value: string) {
  return compactText(value)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9?]+/g, " ")
    .trim();
}

function inheritedLabel(value?: string) {
  return value ? `inherit: ${value}` : "inherit from document";
}

function parseWorkflowGraphJson(value: string) {
  if (!value.trim()) {
    return null;
  }
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function workflowGraphJsonError(value: string) {
  if (!value.trim()) {
    return "";
  }
  try {
    JSON.parse(value);
    return "";
  } catch (error) {
    return error instanceof Error ? error.message : "Invalid JSON";
  }
}

function workflowGraphMetadataPatch(workflowGraph: Record<string, unknown>) {
  const validationErrors = Array.isArray(workflowGraph.validation_errors) ? workflowGraph.validation_errors : [];
  const uncertainEdges = Array.isArray(workflowGraph.uncertain_edges) ? workflowGraph.uncertain_edges : [];
  return {
    workflow_graph: workflowGraph,
    graph_confidence: Number(workflowGraph.graph_confidence ?? 0),
    requires_human_review: Boolean(workflowGraph.requires_human_review ?? true),
    review_reason: String(workflowGraph.review_reason ?? ""),
    graph_validation_errors: validationErrors,
    graph_validation_error_count: validationErrors.length,
    uncertain_edges: uncertainEdges,
    uncertain_edges_count: uncertainEdges.length,
  };
}
