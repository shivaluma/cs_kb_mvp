import { useState } from "react";
import {
  IconCheck as Check,
  IconCopy as Copy,
  IconFileTime as FileClock,
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
import { SourceContextCard } from "@/components/source-context-card";
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
import { groupResultsByDisplaySource, type SourceDisplayGroup } from "@/lib/source-display";
import { isDebugUiEnabled } from "@/lib/ui-mode";
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
  onSuggestionSelect,
  onUpdateFilter,
  query,
  selected,
  selectedDocumentMatch,
  selectedVersion,
  semanticResults,
  searchEventId,
  suggestions,
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
  onSuggestionSelect: (value: string) => void;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
  query: string;
  selected: SOP | null;
  selectedDocumentMatch: RetrievalResult | null;
  selectedVersion: SOP["current_version"] | undefined;
  semanticResults: RetrievalResult[];
  searchEventId: string;
  suggestions: string[];
  setQuery: (query: string) => void;
}) {
  const canSearch = query.trim().length >= 2;
  const [filtersOpen, setFiltersOpen] = useState(false);
  const groupedSourceResults = groupResultsByDisplaySource(semanticResults);
  const aiSuggestedSops = aiSuggestion?.suggested_sops ?? [];
  const selectedCitationMatches =
    selectedDocumentMatch && !semanticResults.some((result) => result.chunk_id === selectedDocumentMatch.chunk_id)
      ? [selectedDocumentMatch]
      : [];
  const selectedCitationGroups = groupResultsByDisplaySource(selectedCitationMatches);
  const selectedSourceGroup = selectedDocumentMatch
    ? groupResultsByDisplaySource([...semanticResults, ...selectedCitationMatches]).find((group) =>
        group.results.some((result) => result.chunk_id === selectedDocumentMatch.chunk_id),
      ) ?? groupResultsByDisplaySource([selectedDocumentMatch])[0]
    : null;
  const visibleCount = listSource.length + groupedSourceResults.length + selectedCitationGroups.length + aiSuggestedSops.length;
  const activeFilterCount = countActiveFilters(filters);
  const debugEnabled = isDebugUiEnabled();

  function openFullSop(match: RetrievalResult) {
    onSelectDocumentMatch(match);
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
            minLength={2}
            onChange={setQuery}
            onSearch={onRunSearch}
            onSuggestionSelect={onSuggestionSelect}
            placeholder="Search case reason, macro, policy wording, or customer issue"
            suggestions={suggestions}
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
                  text="Try a case reason, customer issue, macro name, or policy wording. Suggestions appear after two characters."
                  title="Search published SOPs"
                />
              ) : loading || booting ? (
                <ResultSkeleton />
              ) : visibleCount === 0 ? (
                <EmptyResults query={query} />
              ) : (
                <>
                  {selectedCitationMatches.length > 0 ? (
                    <ResultGroup count={selectedCitationGroups.length} title="Selected citation">
                      <p className="text-xs leading-5 text-muted-foreground">
                        Opened from Chat or a citation link. Search results may still be loading or may not match this exact title.
                      </p>
                      {selectedCitationGroups.map((group) => (
                        <SourceContextCard
                          compact
                          group={group}
                          key={group.id}
                          onCopyExcerpt={copyAnswer}
                          onOpenSource={() => openFullSop(group.results[0])}
                          onSelect={() => onSelectDocumentMatch(group.results[0])}
                          selected={Boolean(selectedDocumentMatch && group.results.some((result) => result.chunk_id === selectedDocumentMatch.chunk_id))}
                          showDebugScore={debugEnabled}
                        />
                      ))}
                    </ResultGroup>
                  ) : null}

                  {groupedSourceResults.length ? (
                    <ResultGroup accent count={groupedSourceResults.length} title="Best SOP evidence">
                      {groupedSourceResults.map((group) => (
                        <SourceContextCard
                          compact
                          group={group}
                          key={group.id}
                          onCopyExcerpt={copyAnswer}
                          onOpenSource={() => openFullSop(group.results[0])}
                          onSelect={() => onSelectDocumentMatch(group.results[0])}
                          selected={Boolean(selectedDocumentMatch && group.results.some((result) => result.chunk_id === selectedDocumentMatch.chunk_id))}
                          showDebugScore={debugEnabled}
                        />
                      ))}
                    </ResultGroup>
                  ) : null}

                  {listSource.length ? (
                    <ResultGroup count={listSource.length} title="SOP documents">
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
                  ) : null}

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
                              Open in SOP
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
          {selectedDocumentMatch && selectedSourceGroup ? (
            <DocumentMatchDetail group={selectedSourceGroup} query={query} searchEventId={searchEventId} />
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
              text="Choose a result to read the full SOP context and verify the highlighted source."
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

function countActiveFilters(filters: FilterState) {
  return Object.values(filters).filter((value) => value && value !== "all").length;
}

function DocumentMatchDetail({ group, query, searchEventId }: { group: SourceDisplayGroup; query: string; searchEventId: string }) {
  const primary = group.matches[0]?.result;
  const facts = primary ? operationalFacts(primary.metadata) : [];

  return (
    <article className="rounded-xl border bg-card">
      <header className="space-y-3 border-b p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary">source context</Badge>
              <Badge variant="outline">v{group.versionNumber}</Badge>
              {group.matches.length > 1 ? <Badge variant="outline">{group.matches.length} highlighted matches</Badge> : null}
            </div>
            <h2 className="mt-2 text-lg font-semibold leading-snug">{group.title}</h2>
            <p className="mt-1 max-w-[65ch] text-sm text-muted-foreground">
              {group.category || "Published SOP source"}
              {group.collections.length ? <span className="text-muted-foreground/70"> · {group.collections.join(", ")}</span> : null}
            </p>
          </div>
          {isDebugUiEnabled() ? (
            <div className="shrink-0 text-right text-[11px] text-muted-foreground">
              <div>score</div>
              <div className="font-medium tabular-nums text-foreground">{group.score.toFixed(4)}</div>
            </div>
          ) : null}
        </div>
      </header>
      <div className="space-y-5 p-5">
        <SourceContextCard
          autoScrollToHighlight
          group={group}
          onCopyExcerpt={(text) => void navigator.clipboard.writeText(text)}
          showDebugScore={isDebugUiEnabled()}
        />
        {group.matches.length > 1 ? (
          <section>
            <SectionTitle title="Highlighted matches" />
            <div className="mt-2 grid gap-2">
              {group.matches.map((match) => (
                <div className="rounded-lg border bg-muted/20 px-3 py-2" key={match.chunkId}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="min-w-0 text-sm font-medium">{match.title}</p>
                    <Badge variant="outline">{Math.round(match.score * 100)}%</Badge>
                  </div>
                  <MetaLine className="mt-1" items={[match.sectionTitle, match.unitType]} />
                </div>
              ))}
            </div>
          </section>
        ) : null}
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
          <SectionTitle title="Source" />
          <dl className="mt-2 grid gap-x-6 gap-y-2 md:grid-cols-2">
            <GovernanceItem label="Document" value={group.title} />
            <GovernanceItem label="Version" value={`v${group.versionNumber}`} />
            <GovernanceItem label="Category" value={group.category || "n/a"} />
            <GovernanceItem label="Collection" value={group.collections.join(", ") || "n/a"} />
          </dl>
        </section>
        {primary ? (
          <OperationalFeedbackButtons
            entityId={primary.chunk_id}
            entityType="chunk"
            metadata={{
              search_event_id: searchEventId,
              unit_type: primary.metadata.unit_type ?? primary.section,
              version_id: primary.version_id,
              document_id: primary.document_id,
            }}
            sampleQuery={query}
            sourceTitle={group.title}
            targetTitle={group.matches[0]?.title || group.title}
          />
        ) : null}
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
              {isDebugUiEnabled() ? <GovernanceItem label="Version ID" value={selectedVersion.id} /> : null}
              {isDebugUiEnabled() ? <GovernanceItem label="Current version pointer" value={selected.current_version_id} /> : null}
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
