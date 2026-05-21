import {
  IconRobot as Bot,
  IconLoader2 as Loader2,
  IconSparkles as Sparkles,
  IconWand as WandSparkles
} from "@tabler/icons-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SearchBar } from "@/components/search-bar";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EmptyPanel, EmptyResults, FilterGrid } from "@/components/common";
import { SourceContextCard } from "@/components/source-context-card";
import { groupResultsByDisplaySource } from "@/lib/source-display";
import type { FilterOption, FilterState, RetrievalResponse } from "@/types";

export function RetrievalWorkspace({
  busy,
  collectionOptions,
  dynamicFilterOptions,
  filters,
  mode,
  onModeChange,
  onRetrieve,
  onUpdateFilter,
  query,
  retrieval,
  setQuery,
}: {
  busy: boolean;
  collectionOptions: FilterOption[];
  dynamicFilterOptions: Partial<Record<Exclude<keyof FilterState, "collection" | "contentType">, FilterOption[]>>;
  filters: FilterState;
  mode: RetrievalResponse["mode"];
  onModeChange: (mode: RetrievalResponse["mode"]) => void;
  onRetrieve: () => void;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
  query: string;
  retrieval: RetrievalResponse | null;
  setQuery: (query: string) => void;
}) {
  const canRetrieve = query.trim().length > 0;
  const sourceGroups = groupResultsByDisplaySource(retrieval?.results ?? []);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(23rem,0.72fr)_minmax(34rem,1.28fr)]">
      <section className="space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Retrieval workbench</CardTitle>
            <CardDescription>
              Test production retrieval without changing source data.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            <SearchBar
              actionLabel="Run"
              className="lg:block"
              id="retrieval-query"
              loading={busy}
              multiline
              onChange={setQuery}
              onSearch={onRetrieve}
              placeholder="Ask a natural-language retrieval question"
              value={query}
            />

            <div className="grid gap-2">
              <div className="grid gap-1.5">
                <label className="text-xs font-medium capitalize text-muted-foreground">mode</label>
                <Select onValueChange={(value) => onModeChange(value as RetrievalResponse["mode"])} value={mode}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="hybrid">hybrid</SelectItem>
                    <SelectItem value="lexical">lexical</SelectItem>
                    <SelectItem value="vector">vector</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <FilterGrid
                collectionOptions={collectionOptions}
                filterOptions={dynamicFilterOptions}
                filters={filters}
                onUpdateFilter={onUpdateFilter}
                showAdvancedByDefault
              />
            </div>

            <Button className="w-full justify-center" disabled={busy || !canRetrieve} onClick={onRetrieve} type="button">
              {busy ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Sparkles data-icon="inline-start" className="size-4" />}
              Run query
            </Button>
          </CardContent>
        </Card>

        <QueryExpansionPanel retrieval={retrieval} />
      </section>

      <section className="min-w-0">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Evidence</CardTitle>
                <CardDescription>
                  {retrieval ? `${sourceGroups.length} source contexts, ${retrieval.latency_ms}ms` : "No retrieval run yet"}
                </CardDescription>
              </div>
              <Badge variant={retrieval?.warnings.length ? "destructive" : "outline"}>
                {retrieval?.warnings[0] ?? "citation-required"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            {!retrieval ? (
              <EmptyPanel icon={Bot} title="Run a query" text="Results show grouped published source contexts with highlighted matches." compact />
            ) : retrieval.results.length === 0 ? (
              <EmptyResults query={retrieval.query} />
            ) : (
              <div className="space-y-3">
                {sourceGroups.map((group) => (
                  <SourceContextCard
                    compact
                    group={group}
                    key={group.id}
                    onCopyExcerpt={(text) => void navigator.clipboard.writeText(text)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function QueryExpansionPanel({ retrieval }: { retrieval: RetrievalResponse | null }) {
  return (
    <Card className="rounded-xl" size="sm">
      <CardHeader>
        <CardTitle>Query expansion</CardTitle>
        <CardDescription>Synonym matches and normalized query before ranking.</CardDescription>
      </CardHeader>
      <CardContent>
        {!retrieval ? (
          <EmptyPanel
            compact
            icon={WandSparkles}
            text="Run retrieval to see DB-managed synonym matches."
            title="No expansion yet"
          />
        ) : (
          <div className="space-y-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Normalized query
              </p>
              <p className="mt-1 break-words text-sm">{retrieval.normalized_query}</p>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Expansions
              </p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {retrieval.query_expansion.expansions.length === 0 ? (
                  <Badge variant="outline">no expansion</Badge>
                ) : (
                  retrieval.query_expansion.expansions.map((item) => (
                    <Badge key={item} variant="secondary">
                      {item}
                    </Badge>
                  ))
                )}
              </div>
            </div>
            {retrieval.query_expansion.matched_synonyms.length ? (
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Matched synonyms
                </p>
                <ul className="divide-y rounded-md border bg-card">
                  {retrieval.query_expansion.matched_synonyms.map((match) => (
                    <li className="space-y-1 p-2.5" key={`${match.group_id}-${match.canonical_key}`}>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="secondary">{match.canonical_key}</Badge>
                        <Badge variant="outline">{match.synonym_type}</Badge>
                        {match.domain ? <Badge variant="outline">{match.domain}</Badge> : null}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Matched: {match.matched_terms.join(", ") || "canonical key"}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
