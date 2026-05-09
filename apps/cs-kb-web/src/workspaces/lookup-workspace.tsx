import { Check, FileClock, FileText, Loader2, Search, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";

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
  ResultButton,
  ResultSkeleton,
  SectionTitle,
  TextBlock,
} from "@/components/common";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AISuggestion, FilterState, Macro, RetrievalResult, SearchResult, SOP } from "@/types";

export function LookupWorkspace({
  aiSuggestion,
  booting,
  copied,
  copyError,
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
  const visibleCount = listSource.length + semanticResults.length;
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
            <Button className="h-10 px-4" disabled={loading} onClick={onRunSearch} type="button">
              {loading ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Search data-icon="inline-start" className="size-4" />}
              Search
            </Button>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <FilterGrid filters={filters} onUpdateFilter={onUpdateFilter} />
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
                {loading || booting ? (
                  <ResultSkeleton />
                ) : visibleCount === 0 ? (
                  <EmptyResults query={query} />
                ) : (
                  <>
                    {listSource.length > 0 ? (
                      <div className="space-y-2">
                        <div className="px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Structured SOPs</div>
                        {listSource.map((item) => (
                          <ResultButton item={item} key={item.sop_id} onClick={() => onOpenSOP(item.sop_id)} selected={selected?.id === item.sop_id} />
                        ))}
                      </div>
                    ) : null}
                    {semanticResults.length > 0 ? (
                      <div className="space-y-2 pt-2">
                        <div className="px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Approved document matches</div>
                        {semanticResults.map((match) => (
                          <DocumentMatchButton
                            key={match.chunk_id}
                            match={match}
                            onClick={() => onSelectDocumentMatch(match)}
                            selected={selectedDocumentMatch?.chunk_id === match.chunk_id}
                          />
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </section>

      <article className="min-w-0">
        {selected && selectedVersion ? (
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
        ) : selectedDocumentMatch ? (
          <DocumentMatchDetail match={selectedDocumentMatch} />
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
  selected,
}: {
  match: RetrievalResult;
  onClick: () => void;
  selected: boolean;
}) {
  return (
    <button
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        selected && "border-primary bg-primary/5",
      )}
      onClick={onClick}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-sm font-semibold leading-5">{match.heading || match.title}</h3>
        <Badge variant="outline">doc v{match.version_number}</Badge>
      </div>
      <p className="mt-2 line-clamp-3 text-sm leading-5 text-muted-foreground">{match.content}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{String(match.metadata.unit_type ?? match.section)}</Badge>
        <Badge variant="outline">{String(match.metadata.review_status ?? "approved")}</Badge>
        <Badge variant="outline">{match.rank_source.join(" + ")}</Badge>
      </div>
    </button>
  );
}

function DocumentMatchDetail({ match }: { match: RetrievalResult }) {
  return (
    <Card className="rounded-xl">
      <CardHeader className="space-y-4 border-b pb-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary">approved document</Badge>
              <Badge variant="outline">v{match.version_number}</Badge>
              <Badge variant="outline">{String(match.metadata.unit_type ?? match.section)}</Badge>
            </div>
            <CardTitle className="text-xl md:text-2xl">{match.heading || match.title}</CardTitle>
            <CardDescription className="mt-2 max-w-[72ch] text-sm leading-6">
              {match.title}, {match.source_filename}
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
          <SectionTitle title="Curated content" />
          <p className="mt-3 whitespace-pre-wrap rounded-xl border bg-muted/25 p-4 text-sm leading-7">{match.content}</p>
        </section>
        <section className="grid gap-3 md:grid-cols-2">
          <GovernanceItem label="Document ID" value={match.document_id} />
          <GovernanceItem label="Version ID" value={match.version_id} />
          <GovernanceItem label="Chunk ID" value={match.chunk_id} />
          <GovernanceItem label="Source file" value={match.source_filename} />
        </section>
      </CardContent>
    </Card>
  );
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
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">Agent script: <span className="text-foreground">{selectedVersion.sections.agent_script}</span></p>
          <div className="flex gap-2">
            <Button type="button" variant="outline"><ThumbsUp data-icon="inline-start" className="size-4" />Helpful</Button>
            <Button type="button" variant="outline"><ThumbsDown data-icon="inline-start" className="size-4" />Not useful</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
