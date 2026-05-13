import {
  IconCheck as Check,
  IconCopy as Copy,
  IconFileTime as FileClock,
  IconFileText as FileText,
  IconLoader2 as Loader2,
  IconSearch as Search,
  IconShieldCheck as ShieldCheck,
  IconSparkles as Sparkles
} from "@tabler/icons-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AISuggestionPanel,
  EmptyPanel,
  EmptyResults,
  Fact,
  FilterGrid,
  GovernanceItem,
  MacroCopyButton,
  ResultSkeleton,
  SectionTitle,
  TextBlock,
} from "@/components/common";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AISuggestion, FilterOption, FilterState, Macro, RetrievalResult, SearchResult, SOP } from "@/types";

export function LookupWorkspace({
  aiSuggestion,
  booting,
  copied,
  copyError,
  collectionOptions,
  dynamicFilterOptions,
  feedbackRate,
  filters,
  listSource,
  loading,
  onAskAI,
  onCopyMacro,
  onOpenSOP,
  onRunSearch,
  onSelectDocumentMatch,
  onUpdateFilter,
  query,
  selected,
  selectedDocumentMatch,
  selectedVersion,
  semanticResults,
  setQuery,
}: {
  aiSuggestion: AISuggestion | null;
  booting: boolean;
  copied: string;
  copyError: string;
  collectionOptions: FilterOption[];
  dynamicFilterOptions: Partial<Record<Exclude<keyof FilterState, "collection" | "contentType">, FilterOption[]>>;
  feedbackRate: number;
  filters: FilterState;
  listSource: SearchResult[];
  loading: boolean;
  onAskAI: () => void;
  onCopyMacro: (macro: Macro) => void;
  onOpenSOP: (id: string) => void;
  onRunSearch: () => void;
  onSelectDocumentMatch: (match: RetrievalResult) => void;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
  query: string;
  selected: SOP | null;
  selectedDocumentMatch: RetrievalResult | null;
  selectedVersion: SOP["current_version"] | undefined;
  semanticResults: RetrievalResult[];
  setQuery: (query: string) => void;
}) {
  const canSearch = query.trim().length > 0;
  const groupedResults = groupRetrievalResults(semanticResults);
  const aiSuggestedSops = aiSuggestion?.suggested_sops ?? [];
  const selectedCitationMatches =
    selectedDocumentMatch && !semanticResults.some((result) => result.chunk_id === selectedDocumentMatch.chunk_id)
      ? [selectedDocumentMatch]
      : [];
  const visibleCount = listSource.length + semanticResults.length + selectedCitationMatches.length + aiSuggestedSops.length;

  function openFullSop(match: RetrievalResult) {
    const parentMatch = semanticResults.find((item) => item.document_id === match.document_id && isDocumentLayer(item));
    onSelectDocumentMatch(parentMatch ?? match);
  }

  function copyAnswer(text: string) {
    void navigator.clipboard.writeText(text);
  }

  return (
    <div className="space-y-4">
      <Card className="rounded-xl">
        <CardContent className="pt-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
            <div className="relative min-w-0">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="h-10 pl-9"
                id="sop-search"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    onRunSearch();
                  }
                }}
                placeholder="Search SOP, case reason, policy keyword, or natural language question"
                value={query}
              />
            </div>
            <Button className="h-10 px-4" disabled={loading || !canSearch} onClick={onRunSearch} type="button">
              {loading ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Search data-icon="inline-start" className="size-4" />}
              Search
            </Button>
          </div>
          <div className="mt-3">
            <FilterGrid
              collectionOptions={collectionOptions}
              filterOptions={dynamicFilterOptions}
              filters={filters}
              onUpdateFilter={onUpdateFilter}
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(22rem,0.72fr)_minmax(34rem,1.28fr)]">
        <section className="min-w-0">
          <Card className="rounded-xl">
          <CardHeader className="border-b pb-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>Results</CardTitle>
                <CardDescription>{loading ? "Searching approved content" : `${visibleCount} matches from SOPs and published document chunks`}</CardDescription>
              </div>
              <Badge variant="outline">published only</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[35rem] pr-3">
              <div className="space-y-2">
                {!canSearch ? (
                  <EmptyPanel icon={Search} title="Enter a query" text="Search results appear after you run a lookup." compact />
                ) : loading || booting ? (
                  <ResultSkeleton />
                ) : visibleCount === 0 ? (
                  <EmptyResults query={query} />
                ) : (
                  <div className="space-y-4">
                    {selectedCitationMatches.length > 0 ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={selectedCitationMatches.length} title="Selected citation" />
                        <div className="rounded-xl border bg-secondary/45 p-3 text-xs leading-5 text-secondary-foreground">
                          Opened from Chat or a citation link. Search results may still be loading or may not match this exact title.
                        </div>
                        {selectedCitationMatches.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => openFullSop(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </div>
                    ) : null}
                    {groupedResults.exact.length > 0 ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={groupedResults.exact.length} title="Exact rule match" />
                        {groupedResults.exact.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => openFullSop(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </div>
                    ) : null}
                    {groupedResults.issueRouter.length > 0 ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={groupedResults.issueRouter.length} title="Issue Router Match" />
                        {groupedResults.issueRouter.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => openFullSop(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </div>
                    ) : null}
                    {groupedResults.tool.length > 0 ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={groupedResults.tool.length} title="Tool Link" />
                        {groupedResults.tool.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => openFullSop(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </div>
                    ) : null}
                    {groupedResults.action.length > 0 ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={groupedResults.action.length} title="Action Template" />
                        {groupedResults.action.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => openFullSop(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </div>
                    ) : null}
                    {(groupedResults.parent.length > 0 || listSource.length > 0) ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={groupedResults.parent.length + listSource.length} title="Parent SOP" />
                        {groupedResults.parent.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => onSelectDocumentMatch(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                        {listSource.map((item) => (
                          <SopResultCard
                            item={item}
                            key={item.sop_id}
                            onCopyAnswer={() => copyAnswer(item.snippet)}
                            onOpen={() => onOpenSOP(item.sop_id)}
                            selected={selected?.id === item.sop_id}
                          />
                        ))}
                      </div>
                    ) : null}
                    {groupedResults.related.length > 0 ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={groupedResults.related.length} title="Related SOP" />
                        {groupedResults.related.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => openFullSop(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </div>
                    ) : null}
                    {aiSuggestedSops.length > 0 ? (
                      <div className="space-y-2">
                        <ResultGroupHeader count={aiSuggestedSops.length} title="AI suggestion" />
                        {aiSuggestedSops.map((item) => (
                          <article
                            className="w-full rounded-xl border bg-muted/20 p-3 text-left"
                            key={`${item.sop_id}-${item.version}`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <h3 className="min-w-0 text-sm font-semibold leading-5">{item.title}</h3>
                              <Badge variant="outline">{Math.round(item.confidence * 100)}%</Badge>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <Badge variant="secondary">grounded</Badge>
                              <Badge variant="outline">v{item.version}</Badge>
                              <Button className="h-7 px-2" onClick={() => onOpenSOP(item.sop_id)} size="sm" type="button" variant="outline">Open full SOP</Button>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </section>

      <article className="min-w-0">
        {selectedDocumentMatch ? (
          <DocumentMatchDetail match={selectedDocumentMatch} />
        ) : selected && selectedVersion ? (
          <SOPDetail
            aiSuggestion={aiSuggestion}
            copied={copied}
            copyError={copyError}
            feedbackRate={feedbackRate}
            onAskAI={onAskAI}
            onCopyMacro={onCopyMacro}
            selected={selected}
            selectedVersion={selectedVersion}
          />
        ) : (
          <EmptyPanel icon={Search} title="Select a result" text="Search or choose a SOP/document match to inspect latest published content." />
        )}
      </article>
      </div>
    </div>
  );
}

function DocumentMatchButton({
  match,
  onClick,
  onCopyAnswer,
  onOpenFullSop,
  selected,
}: {
  match: RetrievalResult;
  onClick: () => void;
  onCopyAnswer: () => void;
  onOpenFullSop: () => void;
  selected: boolean;
}) {
  const scope = String(match.metadata.retrieval_scope ?? "unit");
  const unitType = String(match.metadata.unit_type ?? match.section);
  const isDocumentLayer = scope === "document" || unitType === "full_sop";
  const facts = operationalFacts(match.metadata).slice(0, 4);
  return (
    <article
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left",
        selected && "border-primary bg-primary/5",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-sm font-semibold leading-5">{match.heading || match.title}</h3>
        <Badge variant="outline">doc v{match.version_number}</Badge>
      </div>
      <p className="mt-1 truncate text-xs text-muted-foreground">From: {match.title}</p>
      <p className="mt-2 line-clamp-3 text-sm leading-5 text-muted-foreground">{match.content}</p>
      {facts.length > 0 ? (
        <div className="mt-3 grid gap-1.5 rounded-lg border bg-muted/20 p-2">
          {facts.map((fact) => (
            <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-2 text-[11px]" key={fact.label}>
              <span className="text-muted-foreground">{fact.label}</span>
              <span className="truncate font-medium">{fact.value}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant={isDocumentLayer ? "secondary" : "outline"}>{isDocumentLayer ? "Full SOP" : "Quick answer"}</Badge>
        <Badge variant="secondary">{unitType}</Badge>
        <Badge variant="outline">{String(match.metadata.review_status ?? "approved")}</Badge>
        <Badge variant="outline">{match.rank_source.join(" + ")}</Badge>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button className="h-7 px-2" onClick={onClick} size="sm" type="button" variant="outline">
          Open quick answer
        </Button>
        <Button className="h-7 px-2" onClick={onOpenFullSop} size="sm" type="button" variant="outline">
          Open full SOP
        </Button>
        <Button className="h-7 px-2" onClick={onCopyAnswer} size="sm" type="button" variant="ghost">
          <Copy data-icon="inline-start" className="size-3.5" />
          Copy answer
        </Button>
      </div>
    </article>
  );
}

function SopResultCard({
  item,
  onCopyAnswer,
  onOpen,
  selected,
}: {
  item: SearchResult;
  onCopyAnswer: () => void;
  onOpen: () => void;
  selected: boolean;
}) {
  return (
    <article
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left",
        selected && "border-primary bg-primary/5",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-sm font-semibold leading-5">{item.title}</h3>
        <Badge variant="secondary">v{item.version}</Badge>
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-5 text-muted-foreground">{item.snippet}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{item.category}</Badge>
        <Badge variant="outline">{item.vertical}</Badge>
        <span className="text-xs text-muted-foreground">{formatDate(item.updated_at)}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button className="h-7 px-2" onClick={onOpen} size="sm" type="button" variant="outline">
          Open full SOP
        </Button>
        <Button className="h-7 px-2" onClick={onCopyAnswer} size="sm" type="button" variant="ghost">
          <Copy data-icon="inline-start" className="size-3.5" />
          Copy answer
        </Button>
      </div>
    </article>
  );
}

function ResultGroupHeader({ count, title }: { count: number; title: string }) {
  return (
    <div className="flex items-center justify-between gap-3 px-1">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      <Badge variant="outline">{count}</Badge>
    </div>
  );
}

function groupRetrievalResults(results: RetrievalResult[]) {
  return results.reduce(
    (groups, result) => {
      if (isDocumentLayer(result)) {
        groups.parent.push(result);
      } else if (isIssueRouterMatch(result)) {
        groups.issueRouter.push(result);
      } else if (isToolMatch(result)) {
        groups.tool.push(result);
      } else if (isActionTemplateMatch(result)) {
        groups.action.push(result);
      } else if (isExactRuleMatch(result)) {
        groups.exact.push(result);
      } else {
        groups.related.push(result);
      }
      return groups;
    },
    {
      exact: [] as RetrievalResult[],
      issueRouter: [] as RetrievalResult[],
      tool: [] as RetrievalResult[],
      action: [] as RetrievalResult[],
      parent: [] as RetrievalResult[],
      related: [] as RetrievalResult[],
    },
  );
}

function isDocumentLayer(match: RetrievalResult) {
  const scope = String(match.metadata.retrieval_scope ?? "unit");
  const unitType = String(match.metadata.unit_type ?? match.section);
  return scope === "document" || unitType === "full_sop";
}

function isIssueRouterMatch(match: RetrievalResult) {
  const unitType = String(match.metadata.unit_type ?? match.section);
  return ["issue_router_unit", "sop_reference", "vip_overlay_rule", "product_update_note"].includes(unitType);
}

function isToolMatch(match: RetrievalResult) {
  const unitType = String(match.metadata.unit_type ?? match.section);
  return unitType === "tool_link";
}

function isActionTemplateMatch(match: RetrievalResult) {
  const unitType = String(match.metadata.unit_type ?? match.section);
  return unitType === "quick_action_rule";
}

function isExactRuleMatch(match: RetrievalResult) {
  const unitType = String(match.metadata.unit_type ?? match.section);
  return [
    "validation_rule",
    "handling_rule",
    "routing_rule",
    "operational_instruction",
    "policy_rule",
    "sla_rule",
    "decision_rule",
    "escalation_rule",
    "case_creation_rule",
    "handoff_rule",
    "tasklist_creation_rule",
    "subject_format_rule",
    "related_process_note",
    "compliance_note",
    "security_note",
    "decision_tree",
    "decision_point",
    "workflow_step",
    "warning",
  ].includes(unitType) || match.rank_source.includes("lexical");
}

function DocumentMatchDetail({ match }: { match: RetrievalResult }) {
  const scope = String(match.metadata.retrieval_scope ?? "unit");
  const unitType = String(match.metadata.unit_type ?? match.section);
  const isDocumentLayer = scope === "document" || unitType === "full_sop";
  const facts = operationalFacts(match.metadata);
  return (
    <Card className="rounded-xl">
      <CardHeader className="space-y-4 border-b pb-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant={isDocumentLayer ? "secondary" : "outline"}>{isDocumentLayer ? "Full SOP" : "Quick answer"}</Badge>
              <Badge variant="secondary">approved document</Badge>
              <Badge variant="outline">v{match.version_number}</Badge>
              <Badge variant="outline">{unitType}</Badge>
            </div>
            <CardTitle className="text-xl md:text-2xl">{match.heading || match.title}</CardTitle>
            <CardDescription className="mt-2 max-w-[72ch] text-sm leading-6">
              From: {match.title}, {match.source_filename}
            </CardDescription>
          </div>
          <div className="rounded-xl border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            score {match.score.toFixed(4)}
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <Fact icon={FileText} label="Section" value={match.section} />
          <Fact icon={ShieldCheck} label="Review" value={String(match.metadata.review_status ?? "approved")} />
          <Fact icon={FileClock} label="Chunk" value={`${match.chunk_index}`} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pt-4">
        <section>
          <SectionTitle title={isDocumentLayer ? "Full SOP page" : "Atomic knowledge unit"} />
          <p className="mt-3 whitespace-pre-wrap rounded-xl border bg-muted/25 p-4 text-sm leading-7">{match.content}</p>
        </section>
        {facts.length > 0 ? (
          <section>
            <SectionTitle title="Operational fields" />
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {facts.map((fact) => (
                <GovernanceItem key={fact.label} label={fact.label} value={fact.value} />
              ))}
            </div>
          </section>
        ) : null}
        <section className="grid gap-3 md:grid-cols-2">
          <GovernanceItem label="Parent SOP" value={match.title} />
          <GovernanceItem label="Document ID" value={match.document_id} />
          <GovernanceItem label="Version ID" value={match.version_id} />
          <GovernanceItem label="Chunk ID" value={match.chunk_id} />
          <GovernanceItem label="Source file" value={match.source_filename} />
        </section>
      </CardContent>
    </Card>
  );
}

function operationalFacts(metadata: Record<string, unknown>) {
  const fields = [
    ["Priority", metadata.priority],
    ["Condition", metadata.condition],
    ["Action", metadata.action ?? metadata.default_action],
    ["Queue", metadata.queue],
    ["Reporter", metadata.reporter],
    ["Service", metadata.service ?? metadata.vertical],
    ["Audience", metadata.audience],
    ["Ping Tech", metadata.requires_ping ?? metadata.requires_ping_tech],
    ["Owner", metadata.owner ?? metadata.owner_team],
    ["Risk", metadata.risk_level],
  ] as const;
  return fields
    .map(([label, value]) => ({ label, value: formatMetadataValue(value) }))
    .filter((fact) => fact.value.length > 0);
}

function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (Array.isArray(value)) {
    return value.map(formatMetadataValue).filter(Boolean).join(", ");
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function SOPDetail({
  aiSuggestion,
  copied,
  copyError,
  feedbackRate,
  onAskAI,
  onCopyMacro,
  selected,
  selectedVersion,
}: {
  aiSuggestion: AISuggestion | null;
  copied: string;
  copyError: string;
  feedbackRate: number;
  onAskAI: () => void;
  onCopyMacro: (macro: Macro) => void;
  selected: SOP;
  selectedVersion: SOP["current_version"];
}) {
  return (
    <Card className="rounded-xl">
      <CardHeader className="space-y-4 border-b pb-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{selected.code}</Badge>
              <Badge variant="outline">v{selectedVersion.version_number}</Badge>
              <Badge variant="secondary">published</Badge>
            </div>
            <CardTitle className="text-xl md:text-2xl">{selected.title}</CardTitle>
            <CardDescription className="mt-2 max-w-[72ch] text-sm leading-6">{selected.summary}</CardDescription>
          </div>
          <Button onClick={onAskAI} type="button" variant="outline">
            <Sparkles data-icon="inline-start" className="size-4 text-muted-foreground" />
            Ask AI
          </Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <Fact icon={FileClock} label="Updated" value={formatDate(selected.updated_at)} />
          <Fact icon={ShieldCheck} label="Owner" value={selected.owner_team} />
          <Fact icon={Check} label="Helpful" value={`${feedbackRate || 0}%`} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pt-4">
        <Tabs defaultValue="procedure">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="procedure">Procedure</TabsTrigger>
            <TabsTrigger value="macros">Macros</TabsTrigger>
            <TabsTrigger value="governance">Governance</TabsTrigger>
          </TabsList>
          <TabsContent className="mt-5 space-y-5" value="procedure">
            <TextBlock title="When to apply" value={selectedVersion.sections.when_to_apply} />
            <TextBlock title="Input requirements" value={selectedVersion.sections.input_requirements} />
            <section>
              <SectionTitle title="Handling checklist" />
              <ol className="mt-3 grid gap-2">
                {selectedVersion.sections.checklist.map((step, index) => (
                  <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3" key={step}>
                    <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-sm font-semibold text-primary">{index + 1}</span>
                    <p className="min-w-0 rounded-xl border bg-muted/35 px-3 py-2 text-sm leading-6">{step}</p>
                  </li>
                ))}
              </ol>
            </section>
          </TabsContent>
          <TabsContent className="mt-5 space-y-3" value="macros">
            {selectedVersion.sections.macro_response.map((macro) => (
              <div className="rounded-xl border bg-muted/25 p-3" key={macro.title}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold">{macro.title}</h3>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{macro.content}</p>
                  </div>
                  <MacroCopyButton macro={macro} onCopyMacro={onCopyMacro} />
                </div>
              </div>
            ))}
            {copied ? <div className="rounded-xl border bg-secondary px-3 py-2 text-sm text-secondary-foreground">Copied: {copied}</div> : null}
            {copyError ? <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">{copyError}</div> : null}
          </TabsContent>
          <TabsContent className="mt-5 space-y-4" value="governance">
            <div className="grid gap-3 md:grid-cols-2">
              <GovernanceItem label="Change summary" value={selectedVersion.change_summary} />
              <GovernanceItem label="Version ID" value={selectedVersion.id} />
              <GovernanceItem label="Current version pointer" value={selected.current_version_id} />
              <GovernanceItem label="Case reasons" value={selected.case_reasons.join(", ")} />
            </div>
          </TabsContent>
        </Tabs>
        {aiSuggestion ? <AISuggestionPanel suggestion={aiSuggestion} /> : null}
        <Separator />
        <div className="rounded-xl border bg-muted/20 px-3 py-2">
          <p className="text-sm text-muted-foreground">Agent script: <span className="text-foreground">{selectedVersion.sections.agent_script}</span></p>
        </div>
      </CardContent>
    </Card>
  );
}
