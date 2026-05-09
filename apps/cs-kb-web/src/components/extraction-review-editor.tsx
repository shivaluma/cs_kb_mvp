import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, RotateCcw, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ExtractionUnit, ExtractionUnitUpdate } from "@/types";

const UNIT_TYPES = [
  "workflow_overview",
  "verification_dependency",
  "decision_point",
  "workflow_step",
  "macro_script",
  "operational_note",
  "security_note",
  "rule_table_row",
  "text_section",
];

type Draft = {
  title: string;
  content: string;
  unitType: string;
  confidence: string;
  reviewStatus: ExtractionUnit["review_status"];
  riskLevel: string;
  effectiveFrom: string;
};

export function ExtractionReviewEditor({
  disabled,
  onSave,
  saving,
  unit,
}: {
  disabled: boolean;
  onSave: (unit: ExtractionUnit, update: ExtractionUnitUpdate) => void;
  saving: boolean;
  unit: ExtractionUnit;
}) {
  const initialDraft = useMemo(() => unitToDraft(unit), [unit]);
  const [draft, setDraft] = useState<Draft>(initialDraft);

  useEffect(() => {
    setDraft(initialDraft);
  }, [initialDraft]);

  const changed = JSON.stringify(draft) !== JSON.stringify(initialDraft);
  const valid = draft.title.trim().length > 0 && draft.content.trim().length > 0 && Number.isFinite(Number(draft.confidence));
  const confidence = Math.max(0, Math.min(Number(draft.confidence) || 0, 1));

  function save() {
    onSave(unit, {
      title: draft.title.trim(),
      content: draft.content.trim(),
      unit_type: draft.unitType,
      confidence,
      review_status: draft.reviewStatus,
      actor: "cs-ops-ui",
      metadata: {
        ...unit.metadata,
        risk_level: draft.riskLevel,
        effective_from: draft.effectiveFrom,
      },
    });
  }

  return (
    <article className={cn("rounded-2xl border bg-card p-4", changed && "border-primary/60 bg-primary/5")}>
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
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">unit {unit.unit_index}</span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_11rem_9rem]">
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
          Title
          <Input
            disabled={disabled}
            onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
            value={draft.title}
          />
        </label>
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
        Curated content
        <textarea
          className="min-h-28 rounded-xl border border-input bg-background px-3 py-2 text-sm leading-6 shadow-xs outline-none transition-[border-color,box-shadow] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={disabled}
          onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
          value={draft.content}
        />
      </label>

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
          <Input
            disabled={disabled}
            onChange={(event) => setDraft((current) => ({ ...current, riskLevel: event.target.value }))}
            placeholder="low, medium, high"
            value={draft.riskLevel}
          />
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

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs leading-5 text-muted-foreground">
          {disabled ? "Published versions are immutable. Create a new draft version to edit." : "Saving recalculates embedding and updates the curated draft."}
        </p>
        <div className="flex items-center gap-2">
          {draft.reviewStatus === "reviewed" || draft.reviewStatus === "approved" ? (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <CheckCircle2 className="size-3.5" />
              reviewed
            </span>
          ) : null}
          <Button disabled={!changed || saving} onClick={() => setDraft(initialDraft)} size="sm" type="button" variant="outline">
            <RotateCcw data-icon="inline-start" className="size-4" />
            Reset
          </Button>
          <Button disabled={disabled || !changed || !valid || saving} onClick={save} size="sm" type="button">
            <Save data-icon="inline-start" className="size-4" />
            {saving ? "Saving" : "Save unit"}
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
    effectiveFrom: String(unit.metadata.effective_from ?? ""),
  };
}
