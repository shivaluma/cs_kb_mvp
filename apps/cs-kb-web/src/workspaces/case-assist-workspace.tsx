import { useEffect, useMemo, useState } from "react";
import {
  IconArrowRight as ArrowRight,
  IconChecklist as Checklist,
  IconCopy as Copy,
  IconExternalLink as ExternalLink,
  IconFileText as FileText,
  IconRoute as Route,
  IconSearch as Search,
  IconShieldCheck as ShieldCheck,
  IconTool as Wrench,
  IconTemplate as Template,
  IconAlertTriangle as Warning
} from "@tabler/icons-react";

import { OperationalFeedbackButtons } from "@/components/operational-feedback";
import { EmptyPanel, FilterGrid, SectionTitle } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type {
  ActionTemplateSummary,
  FilterOption,
  FilterState,
  IssueRouterItem,
  RetrievalResult,
  ToolLinkSummary,
} from "@/types";

export type CaseAssistCandidate = {
  audience: string[];
  caseType: string[];
  chunkId: string;
  collection: string;
  content: string;
  documentId: string;
  heading: string;
  metadata: Record<string, unknown>;
  parentTitle: string;
  relationStatus: string;
  riskLevel: string;
  score: number;
  sourceRole: "issue_router" | "direct_sop" | "parent_sop" | "related_sop" | "tool_link" | "action_template";
  taskType: string[];
  title: string;
  toolIds: string[];
  unitType: string;
  versionId: string;
  vertical: string[];
};

type ActionCard = {
  conditions: string[];
  requiredInputs: string[];
  relatedSops: string[];
  steps: string[];
  warnings: string[];
  whenToApply: string;
};

export function CaseAssistWorkspace({
  actionTemplates,
  collectionOptions,
  dynamicFilterOptions,
  filters,
  loading,
  onCopyActionTemplate,
  onCopyChecklist,
  onCopyQuickAnswer,
  onOpenFullSop,
  onOpenQuickAnswer,
  onOpenTool,
  onRunSearch,
  onSelectCandidate,
  onUpdateFilter,
  query,
  results,
  riskLevel,
  routerResults,
  searchEventId,
  setQuery,
  setRiskLevel,
  tools,
}: {
  actionTemplates: ActionTemplateSummary[];
  collectionOptions: FilterOption[];
  dynamicFilterOptions: Partial<Record<Exclude<keyof FilterState, "collection" | "contentType">, FilterOption[]>>;
  filters: FilterState;
  loading: boolean;
  onCopyActionTemplate: (template: ActionTemplateSummary) => void;
  onCopyChecklist: (candidate: CaseAssistCandidate, checklist: string[]) => void;
  onCopyQuickAnswer: (candidate: CaseAssistCandidate) => void;
  onOpenFullSop: (candidate: CaseAssistCandidate) => void;
  onOpenQuickAnswer: (candidate: CaseAssistCandidate) => void;
  onOpenTool: (tool: ToolLinkSummary) => void;
  onRunSearch: () => void;
  onSelectCandidate: (candidate: CaseAssistCandidate, rank: number) => void;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
  query: string;
  results: RetrievalResult[];
  riskLevel: string;
  routerResults: IssueRouterItem[];
  searchEventId: string;
  setQuery: (query: string) => void;
  setRiskLevel: (value: string) => void;
  tools: ToolLinkSummary[];
}) {
  const normalizedQuery = textFrom(query);
  const candidates = useMemo(() => buildCandidates(routerResults, results), [results, routerResults]);
  const [selectedKey, setSelectedKey] = useState("");
  const selected = candidates.find((candidate) => candidate.chunkId === selectedKey) ?? candidates[0] ?? null;
  const actionCard = selected ? buildActionCard(selected) : null;
  const relatedTools = selected ? selectTools(selected, tools, actionTemplates) : [];
  const relatedTemplates = selected ? selectActionTemplates(selected, actionTemplates, normalizedQuery) : [];
  const grouped = useMemo(() => groupCandidates(candidates), [candidates]);

  useEffect(() => {
    if (!candidates.length) {
      setSelectedKey("");
      return;
    }
    if (!candidates.some((candidate) => candidate.chunkId === selectedKey)) {
      setSelectedKey(candidates[0].chunkId);
    }
  }, [candidates, selectedKey]);

  function selectCandidate(candidate: CaseAssistCandidate, rank: number) {
    setSelectedKey(candidate.chunkId);
    onSelectCandidate(candidate, rank);
    onOpenQuickAnswer(candidate);
  }

  return (
    <div className="space-y-4">
      <Card className="rounded-xl">
        <CardContent className="space-y-3 pt-4">
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="h-10 pl-9"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    onRunSearch();
                  }
                }}
                placeholder="I have an issue: không áp dụng mã khuyến mãi, KH không nhớ email, TX gọi hotline..."
                value={query}
              />
            </div>
            <Button className="h-10 px-4" disabled={!normalizedQuery || loading} onClick={onRunSearch} type="button">
              <Search data-icon="inline-start" className="size-4" />
              Search issue
            </Button>
          </div>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_180px]">
            <FilterGrid
              collectionOptions={collectionOptions}
              filterOptions={{ ...dynamicFilterOptions, contentType: [{ label: "All approved content", value: "all" }] }}
              filters={filters}
              onUpdateFilter={onUpdateFilter}
            />
            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">Risk</label>
              <Select onValueChange={setRiskLevel} value={riskLevel}>
                <SelectTrigger>
                  <SelectValue placeholder="Risk" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All risk</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(23rem,0.82fr)_minmax(36rem,1.18fr)]">
        <Card className="min-w-0 rounded-xl">
          <CardHeader className="border-b pb-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>Issue matches</CardTitle>
                <CardDescription>{loading ? "Searching approved router and SOP units" : `${candidates.length} approved matches`}</CardDescription>
              </div>
              <Badge variant="outline">no case ID</Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-3">
            <ScrollArea className="h-[39rem] pr-3">
              {!normalizedQuery ? (
                <EmptyPanel compact icon={Route} text="Type the issue in plain language. Case Assist will compose quick answer, checklist, tools, and related SOPs from approved content." title="Start with the issue" />
              ) : loading ? (
                <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">Searching approved operational index...</div>
              ) : candidates.length === 0 ? (
                <div className="rounded-xl border bg-muted/20 p-4 text-sm leading-6 text-muted-foreground">
                  No approved Case Assist match. Try SOP Lookup for raw keyword search, or submit feedback if this issue should have a router unit.
                </div>
              ) : (
                <div className="space-y-4">
                  {(["direct_sop", "issue_router", "action_template", "tool_link", "parent_sop", "related_sop"] as const).map((role) =>
                    grouped[role].length ? (
                      <section className="space-y-2" key={role}>
                        <div className="flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                          {roleLabel(role)}
                          <Badge variant="outline">{grouped[role].length}</Badge>
                        </div>
                        {grouped[role].map((candidate) => {
                          const rank = candidates.findIndex((item) => item.chunkId === candidate.chunkId) + 1;
                          return (
                            <CaseAssistResult
                              candidate={candidate}
                              key={`${candidate.sourceRole}-${candidate.chunkId}`}
                              onSelect={() => selectCandidate(candidate, rank)}
                              selected={selected?.chunkId === candidate.chunkId}
                            />
                          );
                        })}
                      </section>
                    ) : null,
                  )}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        <section className="min-w-0">
          {selected && actionCard ? (
            <CaseAssistDetail
              actionCard={actionCard}
              candidate={selected}
              onCopyChecklist={() => onCopyChecklist(selected, actionCard.steps)}
              onCopyQuickAnswer={() => onCopyQuickAnswer(selected)}
              onOpenFullSop={() => onOpenFullSop(selected)}
              query={normalizedQuery}
              relatedTemplates={relatedTemplates}
              relatedTools={relatedTools}
              searchEventId={searchEventId}
              onCopyActionTemplate={onCopyActionTemplate}
              onOpenTool={onOpenTool}
            />
          ) : (
            <EmptyPanel icon={Checklist} text="Select a match to see the action card." title="No action card selected" />
          )}
        </section>
      </div>
    </div>
  );
}

function CaseAssistResult({
  candidate,
  onSelect,
  selected,
}: {
  candidate: CaseAssistCandidate;
  onSelect: () => void;
  selected: boolean;
}) {
  return (
    <button
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        selected && "border-primary bg-primary/5",
      )}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-sm font-semibold leading-5">{candidate.title}</h3>
        <Badge variant="outline">{Math.round(candidate.score * 100) || 1}</Badge>
      </div>
      <p className="mt-1 truncate text-xs text-muted-foreground">{candidate.parentTitle || candidate.collection || roleLabel(candidate.sourceRole)}</p>
      <p className="mt-2 line-clamp-3 text-sm leading-5 text-muted-foreground">{candidate.content}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Badge variant={candidate.sourceRole === "direct_sop" ? "secondary" : "outline"}>{roleLabel(candidate.sourceRole)}</Badge>
        {candidate.unitType ? <Badge variant="secondary">{candidate.unitType}</Badge> : null}
        {candidate.riskLevel ? <Badge variant="outline">{candidate.riskLevel} risk</Badge> : null}
      </div>
    </button>
  );
}

function CaseAssistDetail({
  actionCard,
  candidate,
  onCopyActionTemplate,
  onCopyChecklist,
  onCopyQuickAnswer,
  onOpenFullSop,
  onOpenTool,
  query,
  relatedTemplates,
  relatedTools,
  searchEventId,
}: {
  actionCard: ActionCard;
  candidate: CaseAssistCandidate;
  onCopyActionTemplate: (template: ActionTemplateSummary) => void;
  onCopyChecklist: () => void;
  onCopyQuickAnswer: () => void;
  onOpenFullSop: () => void;
  onOpenTool: (tool: ToolLinkSummary) => void;
  query: string;
  relatedTemplates: ActionTemplateSummary[];
  relatedTools: ToolLinkSummary[];
  searchEventId: string;
}) {
  return (
    <Card className="rounded-xl">
      <CardHeader className="space-y-4 border-b pb-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap gap-2">
              <Badge variant="secondary">Quick answer</Badge>
              <Badge variant="outline">{roleLabel(candidate.sourceRole)}</Badge>
              {candidate.relationStatus ? <Badge variant="outline">{candidate.relationStatus}</Badge> : null}
            </div>
            <CardTitle className="text-xl">{candidate.title}</CardTitle>
            <CardDescription className="mt-2 max-w-[72ch] leading-6">
              {candidate.parentTitle ? `From ${candidate.parentTitle}` : "Approved operational unit"}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button className="h-8 rounded-full px-3" onClick={onCopyQuickAnswer} size="sm" type="button" variant="outline">
              <Copy data-icon="inline-start" className="size-3.5" />
              Copy quick answer
            </Button>
            <Button asChild className="h-8 rounded-full px-3" onClick={onOpenFullSop} size="sm" type="button" variant="outline">
              <a href={`/lookup?q=${encodeURIComponent(candidate.parentTitle || candidate.title)}&chunk=${encodeURIComponent(candidate.chunkId)}`}>
                <FileText data-icon="inline-start" className="size-3.5" />
                Open full SOP
              </a>
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pt-4">
        <section className="rounded-xl border bg-muted/20 p-4">
          <SectionTitle title="Approved answer" />
          <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{candidate.content}</p>
        </section>

        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <section className="space-y-3 rounded-xl border p-4">
            <div className="flex items-center justify-between gap-3">
              <SectionTitle title="Checklist" />
              <Button className="h-8 rounded-full px-3" onClick={onCopyChecklist} size="sm" type="button" variant="outline">
                <Copy data-icon="inline-start" className="size-3.5" />
                Copy checklist
              </Button>
            </div>
            <div className="space-y-2">
              {actionCard.steps.map((step, index) => (
                <label className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-2 rounded-lg border bg-muted/15 p-3 text-sm leading-6" key={`${step}-${index}`}>
                  <input className="mt-1 size-4 accent-primary" type="checkbox" />
                  <span>{step}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="space-y-3 rounded-xl border p-4">
            <SectionTitle title="Action card" />
            <ActionFact icon={ShieldCheck} label="When to apply" values={[actionCard.whenToApply]} />
            <ActionFact icon={ArrowRight} label="Conditions" values={actionCard.conditions} />
            <ActionFact icon={FileText} label="Required inputs" values={actionCard.requiredInputs} />
            <ActionFact icon={Warning} label="Warnings" values={actionCard.warnings} />
          </section>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <section className="space-y-3 rounded-xl border p-4">
            <div className="flex items-center gap-2 font-medium">
              <Wrench className="size-4 text-muted-foreground" />
              Tool links
            </div>
            {relatedTools.length ? relatedTools.map((tool) => (
              <a
                className="block rounded-lg border bg-muted/15 p-3 text-sm transition-colors hover:bg-muted/40"
                href={tool.url}
                key={tool.id}
                onClick={() => onOpenTool(tool)}
                rel="noreferrer"
                target="_blank"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{tool.name}</span>
                  <ExternalLink className="size-3.5 text-muted-foreground" />
                </div>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{tool.description || tool.tool_type}</p>
              </a>
            )) : <p className="text-sm leading-6 text-muted-foreground">No approved tool is linked to this match yet.</p>}
          </section>

          <section className="space-y-3 rounded-xl border p-4">
            <div className="flex items-center gap-2 font-medium">
              <Template className="size-4 text-muted-foreground" />
              Macro/action templates
            </div>
            {relatedTemplates.length ? relatedTemplates.map((template) => (
              <div className="rounded-lg border bg-muted/15 p-3" key={template.id}>
                <div className="font-medium">{template.name}</div>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{template.description || template.action_type}</p>
                <Button
                  className="mt-3 h-8 rounded-full px-3"
                  disabled={!template.copy_template && !template.description && !template.name}
                  onClick={() => onCopyActionTemplate(template)}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  <Copy data-icon="inline-start" className="size-3.5" />
                  Copy
                </Button>
              </div>
            )) : <p className="text-sm leading-6 text-muted-foreground">No approved macro or action template is linked yet.</p>}
          </section>

          <section className="space-y-3 rounded-xl border p-4">
            <div className="flex items-center gap-2 font-medium">
              <FileText className="size-4 text-muted-foreground" />
              Related SOPs
            </div>
            {actionCard.relatedSops.length ? actionCard.relatedSops.map((title) => (
              <div className="rounded-lg border bg-muted/15 p-3 text-sm" key={title}>
                {title}
              </div>
            )) : <p className="text-sm leading-6 text-muted-foreground">No related SOP target is linked yet.</p>}
          </section>
        </div>

        <OperationalFeedbackButtons
          className="rounded-xl border bg-muted/15 p-3"
          entityId={candidate.chunkId}
          entityType="chunk"
          metadata={{
            search_event_id: searchEventId,
            source_role: candidate.sourceRole,
            unit_type: candidate.unitType,
            document_id: candidate.documentId,
            version_id: candidate.versionId,
          }}
          sampleQuery={textFrom(query)}
          sourceTitle={candidate.parentTitle}
          targetTitle={candidate.title}
        />
      </CardContent>
    </Card>
  );
}

function ActionFact({ icon: Icon, label, values }: { icon: typeof FileText; label: string; values: string[] }) {
  const cleaned = values.filter(Boolean);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" />
        {label}
      </div>
      {cleaned.length ? (
        <ul className="space-y-1 text-sm leading-6">
          {cleaned.map((value) => <li key={value}>{value}</li>)}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Not specified in approved metadata.</p>
      )}
    </div>
  );
}

function buildCandidates(routerResults: IssueRouterItem[], retrievalResults: RetrievalResult[]) {
  const byId = new Map<string, CaseAssistCandidate>();
  for (const item of routerResults) {
    const metadata = metadataFrom(item.metadata);
    const chunkId = textFrom(item.chunk_id);
    if (!chunkId) {
      continue;
    }
    byId.set(chunkId, {
      audience: asList(item.audience),
      caseType: asList(item.case_type),
      chunkId,
      collection: textFrom(item.collection),
      content: textFrom(item.content),
      documentId: textFrom(item.document_id),
      heading: textFrom(item.title),
      metadata,
      parentTitle: textFrom(item.target_sop_title) || textFrom(item.collection),
      relationStatus: textFrom(item.relation_status),
      riskLevel: textFrom(item.risk_level),
      score: Math.max(numberFrom(item.score), 0.72),
      sourceRole: "issue_router",
      taskType: asList(item.task_type),
      title: textFrom(item.title) || textFrom(item.issue_text),
      toolIds: asList(item.tool_ids),
      unitType: textFrom(metadata.unit_type) || "issue_router_unit",
      versionId: textFrom(item.version_id),
      vertical: asList(item.vertical),
    });
  }
  for (const result of retrievalResults) {
    const chunkId = textFrom(result.chunk_id);
    if (!chunkId || byId.has(chunkId)) {
      continue;
    }
    const metadata = metadataFrom(result.metadata);
    const unitType = textFrom(metadata.unit_type) || textFrom(result.section);
    byId.set(chunkId, {
      audience: asList(metadata.audience),
      caseType: asList(metadata.case_type),
      chunkId,
      collection: textFrom(metadata.collection_name) || textFrom(metadata.collection_slug),
      content: textFrom(result.content),
      documentId: textFrom(result.document_id),
      heading: textFrom(result.heading),
      metadata,
      parentTitle: textFrom(result.title),
      relationStatus: textFrom(metadata.relation_status),
      riskLevel: textFrom(metadata.risk_level),
      score: Math.max(numberFrom(result.score), 0.01),
      sourceRole: sourceRoleFor(result),
      taskType: asList(metadata.task_type),
      title: textFrom(result.heading) || textFrom(result.title),
      toolIds: asList(metadata.tool_ids),
      unitType,
      versionId: textFrom(result.version_id),
      vertical: asList(metadata.vertical),
    });
  }
  return Array.from(byId.values()).sort((left, right) => {
    const roleDelta = rolePriority(left.sourceRole) - rolePriority(right.sourceRole);
    if (roleDelta) {
      return roleDelta;
    }
    return right.score - left.score;
  });
}

function sourceRoleFor(result: RetrievalResult): CaseAssistCandidate["sourceRole"] {
  const metadata = metadataFrom(result.metadata);
  const unitType = textFrom(metadata.unit_type) || textFrom(result.section);
  const scope = textFrom(metadata.retrieval_scope) || "unit";
  if (unitType === "tool_link") {
    return "tool_link";
  }
  if (unitType === "quick_action_rule") {
    return "action_template";
  }
  if (["issue_router_unit", "sop_reference", "vip_overlay_rule", "product_update_note"].includes(unitType)) {
    return "issue_router";
  }
  if (scope === "document" || unitType === "full_sop") {
    return "parent_sop";
  }
  if (asList(result.rank_source).includes("relation")) {
    return "related_sop";
  }
  return "direct_sop";
}

function groupCandidates(candidates: CaseAssistCandidate[]) {
  return candidates.reduce(
    (groups, candidate) => {
      groups[candidate.sourceRole].push(candidate);
      return groups;
    },
    {
      direct_sop: [] as CaseAssistCandidate[],
      issue_router: [] as CaseAssistCandidate[],
      action_template: [] as CaseAssistCandidate[],
      tool_link: [] as CaseAssistCandidate[],
      parent_sop: [] as CaseAssistCandidate[],
      related_sop: [] as CaseAssistCandidate[],
    },
  );
}

function buildActionCard(candidate: CaseAssistCandidate): ActionCard {
  const metadata = metadataFrom(candidate.metadata);
  const steps = firstList(metadata, ["checklist", "steps", "workflow_steps", "actions"]);
  const fallbackSteps = splitOperationalSteps(candidate.content);
  const conditions = [
    textFrom(metadata.condition),
    ...asList(metadata.conditions),
    ...asList(candidate.caseType),
    ...asList(candidate.audience).map((item) => `Audience: ${item}`),
    ...asList(candidate.vertical).map((item) => `Vertical: ${item}`),
  ].filter(Boolean);
  const warnings = [
    ...asList(metadata.warnings),
    textFrom(metadata.warning),
    candidate.riskLevel ? `Risk level: ${candidate.riskLevel}` : "",
  ].filter(Boolean);
  const relatedSops = [
    textFrom(metadata.target_sop_title),
    textFrom(metadata.related_sop_title),
    candidate.parentTitle,
  ].filter(Boolean);
  return {
    conditions: unique(conditions),
    requiredInputs: unique(firstList(metadata, ["required_inputs", "input_requirements", "inputs", "fields"])),
    relatedSops: unique(relatedSops),
    steps: unique((steps.length ? steps : fallbackSteps).slice(0, 8)),
    warnings: unique(warnings),
    whenToApply: textFrom(metadata.when_to_apply) || textFrom(metadata.issue_text) || candidate.title,
  };
}

function splitOperationalSteps(content: string) {
  const safeContent = textFrom(content);
  const bulletLines = safeContent
    .split(/\n+/)
    .map((line) => line.replace(/^[-*•\d.()\s]+/, "").trim())
    .filter((line) => line.length > 4);
  if (bulletLines.length >= 2) {
    return bulletLines;
  }
  return safeContent
    .split(/(?<=[.!?])\s+|;\s+|,\s(?=(CS|KH|TX|Nếu|Trường hợp|Bước)\b)/)
    .map((line) => line.trim())
    .filter((line) => line.length > 8)
    .slice(0, 6);
}

function selectTools(candidate: CaseAssistCandidate, tools: ToolLinkSummary[], templates: ActionTemplateSummary[]) {
  const ids = new Set(candidate.toolIds);
  for (const template of templates) {
    if (template.source_unit_id === candidate.chunkId || matchesCollection(template.metadata, candidate)) {
      asList(template.related_tool_ids).forEach((id) => ids.add(id));
    }
  }
  const exact = tools.filter((tool) => ids.has(tool.id));
  if (exact.length) {
    return exact.slice(0, 5);
  }
  return tools.filter((tool) => matchesCollection(tool.metadata, candidate)).slice(0, 3);
}

function selectActionTemplates(candidate: CaseAssistCandidate, templates: ActionTemplateSummary[], query: string) {
  const queryTokens = tokenSet(query);
  return templates
    .map((template) => ({ template, score: actionTemplateScore(candidate, template, queryTokens) }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
    .map((item) => item.template)
    .slice(0, 4);
}

function actionTemplateScore(candidate: CaseAssistCandidate, template: ActionTemplateSummary, queryTokens: Set<string>) {
  let score = 0;
  if (template.source_unit_id === candidate.chunkId) {
    score += 8;
  }
  if (matchesCollection(template.metadata, candidate)) {
    score += 2;
  }
  const text = `${textFrom(template.name)} ${textFrom(template.description)} ${textFrom(template.copy_template)}`.toLowerCase();
  for (const token of queryTokens) {
    if (text.includes(token)) {
      score += 1;
    }
  }
  const relatedToolIds = asList(template.related_tool_ids);
  if (candidate.toolIds.some((id) => relatedToolIds.includes(id))) {
    score += 2;
  }
  return score;
}

function matchesCollection(metadata: Record<string, unknown>, candidate: CaseAssistCandidate) {
  const safeMetadata = metadataFrom(metadata);
  const collectionSlug = textFrom(safeMetadata.collection_slug);
  const collectionName = textFrom(safeMetadata.collection_name);
  return Boolean(candidate.collection && (candidate.collection === collectionSlug || candidate.collection === collectionName));
}

function firstList(metadata: Record<string, unknown>, keys: string[]) {
  const safeMetadata = metadataFrom(metadata);
  for (const key of keys) {
    const value = safeMetadata[key];
    const list = asList(value);
    if (list.length) {
      return list;
    }
  }
  return [];
}

function asList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(textFrom).filter(Boolean);
  }
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${textFrom(item)}`)
      .filter((item) => item.length > 2);
  }
  const text = textFrom(value);
  return text ? [text] : [];
}

function textFrom(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function metadataFrom(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function numberFrom(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function unique(values: string[]) {
  return Array.from(new Set(values.map(textFrom).filter(Boolean)));
}

function tokenSet(value: string) {
  const safeValue = textFrom(value);
  return new Set(
    safeValue
      .toLowerCase()
      .split(/\W+/)
      .map((token) => token.trim())
      .filter((token) => token.length >= 3),
  );
}

function rolePriority(role: CaseAssistCandidate["sourceRole"]) {
  const order: Record<CaseAssistCandidate["sourceRole"], number> = {
    direct_sop: 0,
    issue_router: 1,
    action_template: 2,
    tool_link: 3,
    parent_sop: 4,
    related_sop: 5,
  };
  return order[role];
}

function roleLabel(role: CaseAssistCandidate["sourceRole"]) {
  const labels: Record<CaseAssistCandidate["sourceRole"], string> = {
    direct_sop: "Exact rule",
    issue_router: "Issue router",
    action_template: "Action template",
    tool_link: "Tool link",
    parent_sop: "Parent SOP",
    related_sop: "Related SOP",
  };
  return labels[role];
}
