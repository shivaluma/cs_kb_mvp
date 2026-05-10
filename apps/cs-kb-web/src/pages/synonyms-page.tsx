import { lazy, Suspense, useState } from "react";

import { RouteLoading } from "@/components/route-loading";
import { defaultSynonymDraft } from "@/constants";
import {
  useAcceptSuggestion,
  useCreateSynonym,
  useGenerateSuggestions,
  useSyncSynonyms,
  useSynonyms,
  useSynonymSuggestions,
  useTransitionSynonym,
} from "@/hooks/api/synonyms";
import { useUrlSearch } from "@/hooks/use-url-search";
import { splitList } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { SynonymDraft, SynonymGroup, SynonymSuggestion } from "@/types";

const SynonymsWorkspace = lazy(() =>
  import("@/workspaces/synonyms-workspace").then((module) => ({ default: module.SynonymsWorkspace })),
);

export function SynonymsPage() {
  const { getParam, setParams } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const status = getParam("status", "active");
  const [draft, setDraft] = useState<SynonymDraft>(defaultSynonymDraft);
  const synonymsQuery = useSynonyms(status);
  const suggestionsQuery = useSynonymSuggestions();
  const createSynonymMutation = useCreateSynonym();
  const transitionSynonymMutation = useTransitionSynonym();
  const syncSynonymsMutation = useSyncSynonyms();
  const generateSuggestionsMutation = useGenerateSuggestions();
  const acceptSuggestionMutation = useAcceptSuggestion();

  function createSynonymGroup() {
    createSynonymMutation.mutate(
      {
        canonical_key: draft.canonicalKey,
        synonym_type: draft.synonymType,
        domain: draft.domain,
        audience: draft.audience,
        status: draft.status,
        created_by: "cs-ops-ui",
        terms: splitList(draft.terms),
      },
      {
        onSuccess: (group) => {
          reportNotice(`Created synonym group ${group.canonical_key}.`);
          setParams({ status: group.status });
        },
        onError: () => reportError("Could not create synonym group. Check required fields."),
      },
    );
  }

  function transitionSynonym(group: SynonymGroup, action: "submit-review" | "approve" | "archive") {
    const actor = action === "approve" ? "cs-lead-ui" : "cs-ops-ui";
    transitionSynonymMutation.mutate(
      { groupId: group.id, action, actor },
      { onSuccess: () => reportNotice(`Synonym ${action} completed for ${group.canonical_key}.`) },
    );
  }

  function syncSynonyms() {
    syncSynonymsMutation.mutate(undefined, {
      onSuccess: (data) => reportNotice(`Synced ${data.synonym_count} synonym keys to Meilisearch.`),
      onError: () => reportError("Meilisearch synonym sync failed."),
    });
  }

  function acceptSuggestion(suggestion: SynonymSuggestion) {
    const canonical = suggestion.canonical_key || draft.canonicalKey || "manual_review";
    acceptSuggestionMutation.mutate(
      {
        suggestionId: suggestion.id,
        canonical_key: canonical,
        synonym_type: "one_way",
        actor: "cs-ops-ui",
        submit_review: true,
      },
      { onSuccess: () => reportNotice(`Accepted suggestion into review as ${canonical}.`) },
    );
  }

  const busyKey =
    createSynonymMutation.isPending ? "create-synonym" :
    syncSynonymsMutation.isPending ? "sync-synonyms" :
    generateSuggestionsMutation.isPending ? "generate-suggestions" :
    "";

  return (
    <Suspense fallback={<RouteLoading label="Loading synonyms" />}>
      <SynonymsWorkspace
        busyKey={busyKey}
        draft={draft}
        onAcceptSuggestion={acceptSuggestion}
        onCreate={createSynonymGroup}
        onGenerateSuggestions={() => {
          generateSuggestionsMutation.mutate(undefined, {
            onSuccess: (data) => reportNotice(`Generated ${data.length} new suggestion candidates.`),
          });
        }}
        onRefreshSuggestions={() => void suggestionsQuery.refetch()}
        onRefreshSynonyms={() => void synonymsQuery.refetch()}
        onSetStatus={(nextStatus) => setParams({ status: nextStatus === "all" ? "" : nextStatus })}
        onSync={syncSynonyms}
        onTransition={transitionSynonym}
        setDraft={setDraft}
        status={status}
        suggestions={suggestionsQuery.data ?? []}
        synonyms={synonymsQuery.data ?? []}
      />
    </Suspense>
  );
}
