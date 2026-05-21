import { useState } from "react";
import {
  IconCheck as Check,
  IconCopy as Copy,
  IconFileTime as FileClock,
  IconFileText as FileText,
  IconAdjustmentsHorizontal as SlidersHorizontal,
  IconSearch as Search,
  IconShieldCheck as ShieldCheck,
  IconSparkles as Sparkles
} from "@tabler/icons-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SearchBar } from "@/components/search-bar";
import {
  AISuggestionPanel,
  EmptyPanel,
  EmptyResults,
  Fact,
  FilterGrid,
  GovernanceItem,
  MetaLine,
  MacroCopyButton,
  ResultSkeleton,
  SectionTitle,
  TextBlock,
} from "@/components/common";
import { OperationalFeedbackButtons } from "@/components/operational-feedback";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AISuggestion, FilterOption, FilterState, Macro, RetrievalResult, SearchResult, SOP } from "@/types";

const GROUP_ORDER: Array<{
  key: keyof GroupedResults;
  label: string;
  accent?: boolean;
}> = [
  { key: "exact", label: "Exact rule match", accent: true },
  { key: "issueRouter", label: "Issue router" },
  { key: "tool", label: "Tool link" },
  { key: "action", label: "Action template" },
  { key: "parent", label: "Document overview" },
  { key: "sourceEvidence", label: "Source evidence" },
  { key: "related", label: "Related SOP" },
];

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
  searchEventId,
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
  searchEventId: string;
  setQuery: (query: string) => void;
}) {
  const canSearch = query.trim().length > 0;
  const [filtersOpen, setFiltersOpen] = useState(false);
  const groupedResults = groupRetrievalResults(semanticResults);
  const aiSuggestedSops = aiSuggestion?.suggested_sops ?? [];
  const selectedCitationMatches =
    selectedDocumentMatch && !semanticResults.some((result) => result.chunk_id === selectedDocumentMatch.chunk_id)
      ? [selectedDocumentMatch]
      : [];
  const visibleCount = listSource.length + semanticResults.length + selectedCitationMatches.length + aiSuggestedSops.length;
  const activeFilterCount = countActiveFilters(filters);

  function openFullSop(match: RetrievalResult) {
    const parentMatch = semanticResults.find((item) => item.document_id === match.document_id && isDocumentLayer(item));
    onSelectDocumentMatch(parentMatch ?? match);
  }

  function copyAnswer(text: string) {
    void navigator.clipboard.writeText(text);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <SearchBar
            actionLabel="Search"
            id="sop-search"
            loading={loading}
            onChange={setQuery}
            onSearch={onRunSearch}
            placeholder="Search SOP, case reason, policy keyword, or natural language question"
            value={query}
          />
        </div>
        <Button
          aria-expanded={filtersOpen}
          className="shrink-0"
          onClick={() => setFiltersOpen((open) => !open)}
          size="default"
          type="button"
          variant="outline"
        >
          <SlidersHorizontal data-icon="inline-start" className="size-4" />
          Filters
          {activeFilterCount > 0 ? (
            <Badge className="ms-1" variant="secondary">
              {activeFilterCount}
            </Badge>
          ) : null}
        </Button>
      </div>

      {filtersOpen ? (
        <div className="rounded-lg border bg-muted/15 p-3">
          <FilterGrid
            collectionOptions={collectionOptions}
            filterOptions={dynamicFilterOptions}
            filters={filters}
            onUpdateFilter={onUpdateFilter}
          />
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(22rem,0.7fr)_minmax(34rem,1.3fr)]">
        <section className="min-w-0">
          <div className="flex items-baseline justify-between gap-3 pb-2">
            <h2 className="text-sm font-semibold">
              {loading ? "Searching…" : canSearch ? `${visibleCount} match${visibleCount === 1 ? "" : "es"}` : "Results"}
            </h2>
            <span className="text-xs text-muted-foreground">published only</span>
          </div>

          <ScrollArea className="h-[calc(100vh-15rem)] pr-3">
            <div className="space-y-5">
              {!canSearch ? (
                <EmptyPanel
                  compact
                  icon={Search}
                  text="Search results appear after you run a lookup."
                  title="Enter a query"
                />
              ) : loading || booting ? (
                <ResultSkeleton />
              ) : visibleCount === 0 ? (
                <EmptyResults query={query} />
              ) : (
                <>
                  {selectedCitationMatches.length > 0 ? (
                    <ResultGroup count={selectedCitationMatches.length} title="Selected citation">
                      <p className="text-xs leading-5 text-muted-foreground">
                        Opened from Chat or a citation link. Search results may still be loading or may not match this exact title.
                      </p>
                      {selectedCitationMatches.map((match) => (
                        <DocumentMatchRow
                          key={match.chunk_id}
                          match={match}
                          onCopyAnswer={() => copyAnswer(match.content)}
                          onOpenFullSop={() => openFullSop(match)}
                          onSelect={() => onSelectDocumentMatch(match)}
                          selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                        />
                      ))}
                    </ResultGroup>
                  ) : null}

                  {GROUP_ORDER.map((group) => {
                    const matches = groupedResults[group.key];
                    if (group.key === "parent") {
                      const total = matches.length + listSource.length;
                      if (total === 0) return null;
                      return (
                        <ResultGroup accent={group.accent} count={total} key={group.key} title={group.label}>
                          {matches.map((match) => (
                            <DocumentMatchRow
                              key={match.chunk_id}
                              match={match}
                              onCopyAnswer={() => copyAnswer(match.content)}
                              onOpenFullSop={() => onSelectDocumentMatch(match)}
                              onSelect={() => onSelectDocumentMatch(match)}
                              selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                            />
                          ))}
                          {listSource.map((item) => (
                            <SopResultRow
                              item={item}
                              key={item.sop_id}
                              onCopyAnswer={() => copyAnswer(item.snippet)}
                              onOpen={() => onOpenSOP(item.sop_id)}
                              selected={selected?.id === item.sop_id}
                            />
                          ))}
                        </ResultGroup>
                      );
                    }
                    if (matches.length === 0) return null;
                    return (
                      <ResultGroup accent={group.accent} count={matches.length} key={group.key} title={group.label}>
                        {matches.map((match) => (
                          <DocumentMatchRow
                            key={match.chunk_id}
                            match={match}
                            onCopyAnswer={() => copyAnswer(match.content)}
                            onOpenFullSop={() => openFullSop(match)}
                            onSelect={() => onSelectDocumentMatch(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </ResultGroup>
                    );
                  })}

                  {aiSuggestedSops.length > 0 ? (
                    <ResultGroup count={aiSuggestedSops.length} title="AI suggestion">
                      {aiSuggestedSops.map((item) => (
                        <div className="rounded-lg border bg-muted/15 p-3" key={`${item.sop_id}-${item.version}`}>
                          <div className="flex items-start justify-between gap-3">
                            <h3 className="min-w-0 text-sm font-semibold leading-snug">{item.title}</h3>
                            <Badge variant="outline">{Math.round(item.confidence * 100)}%</Badge>
                          </div>
                          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                            <Badge variant="secondary">grounded</Badge>
                            <Badge variant="outline">v{item.version}</Badge>
                            <Button
                              className="ms-auto"
                              onClick={() => onOpenSOP(item.sop_id)}
                              size="xs"
                              type="button"
                              variant="outline"
                            >
                              Open source
                            </Button>
                          </div>
                        </div>
                      ))}
                    </ResultGroup>
                  ) : null}
                </>
              )}
            </div>
          </ScrollArea>
        </section>

        <article className="min-w-0">
          {selectedDocumentMatch ? (
            <DocumentMatchDetail match={selectedDocumentMatch} query={query} searchEventId={searchEventId} />
          ) : selected && selectedVersion ? (
            <SOPDetail
              aiSuggestion={aiSuggestion}
              copied={copied}
              copyError={copyError}
              feedbackRate={feedbackRate}
              onAskAI={onAskAI}
              onCopyMacro={onCopyMacro}
              query={query}
              searchEventId={searchEventId}
              selected={selected}
              selectedVersion={selectedVersion}
            />
          ) : (
            <EmptyPanel
              compact
              icon={Search}
              text="Search or choose a SOP/document match to inspect the latest published content."
              title="Select a result"
            />
          )}
        </article>
      </div>
    </div>
  );
}

function ResultGroup({
  accent,
  children,
  count,
  title,
}: {
  accent?: boolean;
  children: React.ReactNode;
  count: number;
  title: string;
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-3 px-0.5">
        <div className="flex items-center gap-2">
          {accent ? <span className="size-1.5 rounded-full bg-foreground" aria-hidden="true" /> : null}
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
        </div>
        <Badge variant="outline">{count}</Badge>
      </div>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

function DocumentMatchRow({
  match,
  onCopyAnswer,
  onOpenFullSop,
  onSelect,
  selected,
}: {
  match: RetrievalResult;
  onCopyAnswer: () => void;
  onOpenFullSop: () => void;
  onSelect: () => void;
  selected: boolean;
}) {
  const scope = String(match.metadata.retrieval_scope ?? "unit");
  const unitType = String(match.metadata.unit_type ?? match.section);
  const isDocLayer = scope === "document" || unitType === "full_sop";
  const isSourceEvidence = scope === "source_evidence" || unitType === "source_evidence_section" || match.metadata.source_evidence_only === true;
  const scopeLabel = isDocLayer ? "Overview" : isSourceEvidence ? "Source evidence" : "Quick answer";

  return (
    <div
      className={cn(
        "group/row rounded-lg border bg-card text-left transition-colors hover:bg-muted/30 focus-within:ring-3 focus-within:ring-ring/40",
        selected && "border-foreground/60 bg-muted/40",
      )}
    >
      <button
        aria-pressed={selected}
        className="block w-full rounded-lg p-3 text-left outline-none"
        onClick={onSelect}
        type="button"
      >
        <div className="flex items-start justify-between gap-2">
          <h4 className="min-w-0 text-sm font-semibold leading-snug">{match.heading || match.title}</h4>
          <Badge className="shrink-0" variant={isDocLayer ? "secondary" : "outline"}>
            {scopeLabel}
          </Badge>
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground">From {match.title}</p>
        <MetaLine
          className="mt-1"
          items={[`v${match.version_number}`, unitType, String(match.metadata.review_status ?? "approved"), match.rank_source.join(" + ")]}
        />
        <p className="mt-1.5 line-clamp-2 text-sm leading-snug text-muted-foreground">{match.content}</p>
      </button>
      <div className="flex items-center gap-1 border-t bg-muted/10 px-2 py-1.5">
        <Button onClick={onOpenFullSop} size="xs" type="button" variant="ghost">
          Open source
        </Button>
        <Button onClick={onCopyAnswer} size="xs" type="button" variant="ghost">
          <Copy data-icon="inline-start" className="size-3" />
          Copy
        </Button>
      </div>
    </div>
  );
}

function SopResultRow({
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
    <div
      className={cn(
        "group/row rounded-lg border bg-card text-left transition-colors hover:bg-muted/30",
        selected && "border-foreground/60 bg-muted/40",
      )}
    >
      <button
        aria-pressed={selected}
        className="block w-full rounded-lg p-3 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
        onClick={onOpen}
        type="button"
      >
        <h4 className="min-w-0 text-sm font-semibold leading-snug">{item.title}</h4>
        <p className="mt-1 line-clamp-2 text-sm leading-snug text-muted-foreground">{item.snippet}</p>
        <MetaLine className="mt-1.5" items={[`v${item.version}`, item.category, item.vertical, formatDate(item.updated_at)]} />
      </button>
      <div className="flex items-center gap-1 border-t bg-muted/10 px-2 py-1.5">
        <Button onClick={onOpen} size="xs" type="button" variant="ghost">
          Open source
        </Button>
        <Button onClick={onCopyAnswer} size="xs" type="button" variant="ghost">
          <Copy data-icon="inline-start" className="size-3" />
          Copy
        </Button>
      </div>
    </div>
  );
}

function groupRetrievalResults(results: RetrievalResult[]): GroupedResults {
  return results.reduce<GroupedResults>(
    (groups, result) => {
      if (isDocumentLayer(result)) {
        groups.parent.push(result);
      } else if (isSourceEvidenceMatch(result)) {
        groups.sourceEvidence.push(result);
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
      exact: [],
      issueRouter: [],
      tool: [],
      action: [],
      parent: [],
      sourceEvidence: [],
      related: [],
    },
  );
}

type GroupedResults = {
  exact: RetrievalResult[];
  issueRouter: RetrievalResult[];
  tool: RetrievalResult[];
  action: RetrievalResult[];
  parent: RetrievalResult[];
  sourceEvidence: RetrievalResult[];
  related: RetrievalResult[];
};

function isDocumentLayer(match: RetrievalResult) {
  const scope = String(match.metadata.retrieval_scope ?? "unit");
  const unitType = String(match.metadata.unit_type ?? match.section);
  return scope === "document" || unitType === "full_sop";
}

function isSourceEvidenceMatch(match: RetrievalResult) {
  const scope = String(match.metadata.retrieval_scope ?? "unit");
  const unitType = String(match.metadata.unit_type ?? match.section);
  return scope === "source_evidence" || unitType === "source_evidence_section" || match.metadata.source_evidence_only === true;
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

function countActiveFilters(filters: FilterState) {
  return Object.values(filters).filter((value) => value && value !== "all").length;
}

function DocumentMatchDetail({ match, query, searchEventId }: { match: RetrievalResult; query: string; searchEventId: string }) {
  const scope = String(match.metadata.retrieval_scope ?? "unit");
  const unitType = String(match.metadata.unit_type ?? match.section);
  const isDocLayer = scope === "document" || unitType === "full_sop";
  const isSourceEvidence = scope === "source_evidence" || unitType === "source_evidence_section" || match.metadata.source_evidence_only === true;
  const facts = operationalFacts(match.metadata);
  const scopeLabel = isDocLayer ? "Overview" : isSourceEvidence ? "Source evidence" : "Quick answer";

  return (
    <article className="rounded-xl border bg-card">
      <header className="space-y-3 border-b p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant={isDocLayer ? "secondary" : "outline"}>{scopeLabel}</Badge>
              <Badge variant="outline">v{match.version_number}</Badge>
              <Badge variant="outline">{unitType}</Badge>
            </div>
            <h2 className="mt-2 text-lg font-semibold leading-snug">{match.heading || match.title}</h2>
            <p className="mt-1 max-w-[65ch] text-sm text-muted-foreground">
              From {match.title}
              {match.source_filename ? <span className="text-muted-foreground/70"> · {match.source_filename}</span> : null}
            </p>
          </div>
          <div className="shrink-0 text-right text-[11px] text-muted-foreground">
            <div>score</div>
            <div className="font-medium tabular-nums text-foreground">{match.score.toFixed(4)}</div>
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <Fact icon={FileText} label="Section" value={match.section} />
          <Fact icon={ShieldCheck} label="Review" value={String(match.metadata.review_status ?? "approved")} />
          <Fact icon={FileClock} label="Chunk" value={`${match.chunk_index}`} />
        </div>
      </header>
      <div className="space-y-5 p-5">
        <section>
          <SectionTitle title={isDocLayer ? "Document overview" : isSourceEvidence ? "Source evidence section" : "Atomic knowledge unit"} />
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7">{match.content}</p>
        </section>
        {facts.length > 0 ? (
          <section>
            <SectionTitle title="Operational fields" />
            <dl className="mt-2 grid gap-x-6 gap-y-2 md:grid-cols-2">
              {facts.map((fact) => (
                <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 text-sm" key={fact.label}>
                  <dt className="text-muted-foreground">{fact.label}</dt>
                  <dd className="min-w-0 break-words font-medium">{fact.value}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}
        <section>
          <SectionTitle title="Source identifiers" />
          <dl className="mt-2 grid gap-x-6 gap-y-2 md:grid-cols-2">
            <GovernanceItem label="Source document" value={match.title} />
            <GovernanceItem label="Document ID" value={match.document_id} />
            <GovernanceItem label="Version ID" value={match.version_id} />
            <GovernanceItem label="Chunk ID" value={match.chunk_id} />
            <GovernanceItem label="Source file" value={match.source_filename} />
          </dl>
        </section>
        <OperationalFeedbackButtons
          entityId={match.chunk_id}
          entityType="chunk"
          metadata={{
            search_event_id: searchEventId,
            unit_type: unitType,
            version_id: match.version_id,
            document_id: match.document_id,
          }}
          sampleQuery={query}
          sourceTitle={match.title}
          targetTitle={match.heading || match.title}
        />
      </div>
    </article>
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
  query,
  searchEventId,
  selected,
  selectedVersion,
}: {
  aiSuggestion: AISuggestion | null;
  copied: string;
  copyError: string;
  feedbackRate: number;
  onAskAI: () => void;
  onCopyMacro: (macro: Macro) => void;
  query: string;
  searchEventId: string;
  selected: SOP;
  selectedVersion: SOP["current_version"];
}) {
  return (
    <article className="rounded-xl border bg-card">
      <header className="space-y-3 border-b p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary">{selected.code}</Badge>
              <Badge variant="outline">published</Badge>
              <Badge variant="outline">v{selectedVersion.version_number}</Badge>
            </div>
            <h2 className="mt-2 text-lg font-semibold leading-snug">{selected.title}</h2>
            <p className="mt-1 max-w-[65ch] text-sm leading-6 text-muted-foreground">{selected.summary}</p>
          </div>
          <Button onClick={onAskAI} size="sm" type="button" variant="outline">
            <Sparkles data-icon="inline-start" className="size-4 text-muted-foreground" />
            Ask AI
          </Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <Fact icon={FileClock} label="Updated" value={formatDate(selected.updated_at)} />
          <Fact icon={ShieldCheck} label="Owner" value={selected.owner_team} />
          <Fact icon={Check} label="Helpful" value={`${feedbackRate || 0}%`} />
        </div>
      </header>
      <div className="space-y-5 p-5">
        <Tabs defaultValue="procedure">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="procedure">Procedure</TabsTrigger>
            <TabsTrigger value="macros">Macros</TabsTrigger>
            <TabsTrigger value="governance">Governance</TabsTrigger>
          </TabsList>
          <TabsContent className="mt-4 space-y-5" value="procedure">
            <TextBlock title="When to apply" value={selectedVersion.sections.when_to_apply} />
            <TextBlock title="Input requirements" value={selectedVersion.sections.input_requirements} />
            <section>
              <SectionTitle title="Handling checklist" />
              <ol className="mt-2 space-y-1.5">
                {selectedVersion.sections.checklist.map((step, index) => (
                  <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] items-start gap-3 text-sm leading-6" key={step}>
                    <span className="mt-0.5 inline-flex size-6 items-center justify-center rounded-full bg-muted text-xs font-semibold tabular-nums text-muted-foreground">
                      {index + 1}
                    </span>
                    <p className="min-w-0">{step}</p>
                  </li>
                ))}
              </ol>
            </section>
          </TabsContent>
          <TabsContent className="mt-4 space-y-2" value="macros">
            {selectedVersion.sections.macro_response.map((macro) => (
              <div className="flex items-start justify-between gap-3 rounded-lg border bg-muted/15 p-3" key={macro.title}>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold">{macro.title}</h3>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">{macro.content}</p>
                </div>
                <MacroCopyButton macro={macro} onCopyMacro={onCopyMacro} />
              </div>
            ))}
            {copied ? (
              <div className="rounded-lg border bg-secondary px-3 py-2 text-sm text-secondary-foreground">Copied: {copied}</div>
            ) : null}
            {copyError ? (
              <div className="rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">{copyError}</div>
            ) : null}
          </TabsContent>
          <TabsContent className="mt-4 space-y-3" value="governance">
            <dl className="grid gap-x-6 gap-y-2 md:grid-cols-2">
              <GovernanceItem label="Change summary" value={selectedVersion.change_summary} />
              <GovernanceItem label="Version ID" value={selectedVersion.id} />
              <GovernanceItem label="Current version pointer" value={selected.current_version_id} />
              <GovernanceItem label="Case reasons" value={selected.case_reasons.join(", ")} />
            </dl>
          </TabsContent>
        </Tabs>
        {aiSuggestion ? <AISuggestionPanel suggestion={aiSuggestion} /> : null}
        <Separator />
        <OperationalFeedbackButtons
          entityId={selected.current_version_id}
          entityType="sop_version"
          metadata={{
            search_event_id: searchEventId,
            sop_id: selected.id,
          }}
          sampleQuery={query}
          sourceTitle={selected.title}
          targetTitle={selected.title}
        />
        <p className="text-sm text-muted-foreground">
          Agent script: <span className="text-foreground">{selectedVersion.sections.agent_script}</span>
        </p>
      </div>
    </article>
  );
}
