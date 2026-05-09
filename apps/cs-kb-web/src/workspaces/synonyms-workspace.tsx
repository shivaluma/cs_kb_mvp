import type { Dispatch, SetStateAction } from "react";
import { DatabaseZap, Loader2, RefreshCw, Sparkles, WandSparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EmptyPanel, Field, StatusBadge } from "@/components/common";
import type { SynonymDraft, SynonymGroup, SynonymSuggestion } from "@/types";

export function SynonymsWorkspace({
  busyKey,
  draft,
  onAcceptSuggestion,
  onCreate,
  onGenerateSuggestions,
  onRefreshSuggestions,
  onRefreshSynonyms,
  onSetStatus,
  onSync,
  onTransition,
  setDraft,
  status,
  suggestions,
  synonyms,
}: {
  busyKey: string;
  draft: SynonymDraft;
  onAcceptSuggestion: (suggestion: SynonymSuggestion) => void;
  onCreate: () => void;
  onGenerateSuggestions: () => void;
  onRefreshSuggestions: () => void;
  onRefreshSynonyms: () => void;
  onSetStatus: (status: string) => void;
  onSync: () => void;
  onTransition: (group: SynonymGroup, action: "submit-review" | "approve" | "archive") => void;
  setDraft: Dispatch<SetStateAction<SynonymDraft>>;
  status: string;
  suggestions: SynonymSuggestion[];
  synonyms: SynonymGroup[];
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(22rem,0.72fr)_minmax(38rem,1.28fr)]">
      <section className="space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Create synonym group</CardTitle>
            <CardDescription>
              Govern phrase-level mappings. Use one-way for policy-sensitive intents.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Canonical key" value={draft.canonicalKey} onChange={(canonicalKey) => setDraft((current) => ({ ...current, canonicalKey }))} />
              <Field label="Domain" value={draft.domain} onChange={(domain) => setDraft((current) => ({ ...current, domain }))} />
              <Field label="Audience" value={draft.audience} onChange={(audience) => setDraft((current) => ({ ...current, audience }))} />
              <div className="grid gap-1.5">
                <label className="text-xs font-medium text-muted-foreground">Type</label>
                <Select onValueChange={(synonymType) => setDraft((current) => ({ ...current, synonymType: synonymType as SynonymDraft["synonymType"] }))} value={draft.synonymType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="one_way">one_way</SelectItem>
                    <SelectItem value="regular">regular</SelectItem>
                    <SelectItem value="typo_correction">typo_correction</SelectItem>
                    <SelectItem value="placeholder">placeholder</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="synonym-terms">
                Terms, comma-separated
              </label>
              <textarea
                className="min-h-24 rounded-xl border bg-background px-3 py-2 text-sm leading-6 shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/40"
                id="synonym-terms"
                onChange={(event) => setDraft((current) => ({ ...current, terms: event.target.value }))}
                value={draft.terms}
              />
            </div>
            <Button className="w-full justify-center" disabled={busyKey === "create-synonym"} onClick={onCreate} type="button">
              {busyKey === "create-synonym" ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <WandSparkles data-icon="inline-start" className="size-4" />}
              Create governed group
            </Button>
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Suggestion queue</CardTitle>
            <CardDescription>
              Generate candidates from failed searches, then move useful terms into review.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2 pt-4">
            <Button disabled={busyKey === "generate-suggestions"} onClick={onGenerateSuggestions} type="button" variant="outline">
              <Sparkles data-icon="inline-start" className="size-4" />
              Generate
            </Button>
            <Button onClick={onRefreshSuggestions} type="button" variant="outline">
              <RefreshCw data-icon="inline-start" className="size-4" />
              Refresh
            </Button>
            <Button disabled={busyKey === "sync-synonyms"} onClick={onSync} type="button">
              <DatabaseZap data-icon="inline-start" className="size-4" />
              Sync Meili
            </Button>
          </CardContent>
        </Card>
      </section>

      <section className="grid min-w-0 gap-4 2xl:grid-cols-[1fr_0.9fr]">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Synonym governance</CardTitle>
                <CardDescription>{synonyms.length} groups in current view</CardDescription>
              </div>
              <div className="flex gap-2">
                <Select onValueChange={onSetStatus} value={status || "all"}>
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">all</SelectItem>
                    <SelectItem value="active">active</SelectItem>
                    <SelectItem value="draft">draft</SelectItem>
                    <SelectItem value="in_review">in_review</SelectItem>
                    <SelectItem value="archived">archived</SelectItem>
                  </SelectContent>
                </Select>
                <Button onClick={onRefreshSynonyms} type="button" variant="outline">
                  <RefreshCw className="size-4" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            <ScrollArea className="h-[42rem] pr-3">
              <div className="space-y-3">
                {synonyms.length === 0 ? (
                  <EmptyPanel icon={WandSparkles} title="No groups" text="Create or generate a synonym group to begin governance." compact />
                ) : (
                  synonyms.map((group) => (
                    <SynonymGroupCard busyKey={busyKey} group={group} key={group.id} onTransition={onTransition} />
                  ))
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Pending suggestions</CardTitle>
            <CardDescription>{suggestions.length} candidates from logs</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <ScrollArea className="h-[42rem] pr-3">
              <div className="space-y-3">
                {suggestions.length === 0 ? (
                  <EmptyPanel icon={Sparkles} title="No pending suggestions" text="Run failed searches, then generate candidates from retrieval logs." compact />
                ) : (
                  suggestions.map((suggestion) => (
                    <div className="rounded-xl border bg-muted/20 p-3" key={suggestion.id}>
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <Badge variant="outline">{suggestion.source}</Badge>
                          <h3 className="mt-2 text-sm font-semibold">{suggestion.canonical_key || "Needs canonical key"}</h3>
                        </div>
                        <Badge variant="secondary">{Math.round(suggestion.confidence * 100)}%</Badge>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {suggestion.suggested_terms.map((term) => (
                          <Badge key={term} variant="outline">{term}</Badge>
                        ))}
                      </div>
                      <p className="mt-3 text-xs leading-5 text-muted-foreground">
                        {String(suggestion.evidence.reason ?? "analytics candidate")}
                      </p>
                      <Button
                        className="mt-3 w-full justify-center"
                        disabled={busyKey === `accept-${suggestion.id}`}
                        onClick={() => onAcceptSuggestion(suggestion)}
                        type="button"
                        variant="outline"
                      >
                        Accept into review
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function SynonymGroupCard({
  busyKey,
  group,
  onTransition,
}: {
  busyKey: string;
  group: SynonymGroup;
  onTransition: (group: SynonymGroup, action: "submit-review" | "approve" | "archive") => void;
}) {
  return (
    <article className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={group.status} />
            <Badge variant="outline">{group.synonym_type}</Badge>
            {group.domain ? <Badge variant="outline">{group.domain}</Badge> : null}
          </div>
          <h3 className="mt-2 text-sm font-semibold">{group.canonical_key}</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {group.approved_by ? `Approved by ${group.approved_by}` : `Created by ${group.created_by}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {group.status === "draft" ? (
            <Button disabled={busyKey === `${group.id}-submit-review`} onClick={() => onTransition(group, "submit-review")} size="sm" type="button" variant="outline">
              Submit
            </Button>
          ) : null}
          {group.status === "in_review" ? (
            <Button disabled={busyKey === `${group.id}-approve`} onClick={() => onTransition(group, "approve")} size="sm" type="button">
              Approve
            </Button>
          ) : null}
          {group.status !== "archived" ? (
            <Button disabled={busyKey === `${group.id}-archive`} onClick={() => onTransition(group, "archive")} size="sm" type="button" variant="outline">
              Archive
            </Button>
          ) : null}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {group.terms.map((term) => (
          <Badge key={`${group.id}-${term.normalized_term}`} variant="outline">{term.normalized_term}</Badge>
        ))}
      </div>
    </article>
  );
}
