import { lazy, Suspense } from "react";
import { useState } from "react";

import { RouteLoading } from "@/components/route-loading";
import { defaultFilters } from "@/constants";
import { useCollections } from "@/hooks/api/kb-index";
import { useRetrieval, useSearchFilterOptions } from "@/hooks/api/search";
import { useUrlSearch } from "@/hooks/use-url-search";
import { compactFilters, optionizeFilterValues } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { FilterOption, FilterState, RetrievalResponse } from "@/types";

const RetrievalWorkspace = lazy(() =>
  import("@/workspaces/retrieval-workspace").then((module) => ({ default: module.RetrievalWorkspace })),
);

export function RetrievalPage() {
  const { getParam, setParams } = useUrlSearch();
  const { reportError } = useFeedback();
  const collectionsQuery = useCollections();
  const filterOptionsQuery = useSearchFilterOptions();
  const retrievalMutation = useRetrieval();
  const query = getParam("q", "");
  const mode = (getParam("mode", "hybrid") as RetrievalResponse["mode"]) || "hybrid";
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const collectionOptions: FilterOption[] = (collectionsQuery.data ?? []).map((collection) => ({
    label: collection.name,
    value: collection.slug,
  }));
  const dynamicFilterOptions = {
    audience: optionizeFilterValues(filterOptionsQuery.data?.audience, "All audiences"),
    vertical: optionizeFilterValues(filterOptionsQuery.data?.vertical, "All verticals"),
    category: optionizeFilterValues(filterOptionsQuery.data?.category, "All categories"),
    taskType: optionizeFilterValues(filterOptionsQuery.data?.task_types, "All tasks"),
  };

  function setQuery(nextQuery: string) {
    setParams({ q: nextQuery });
  }

  function setMode(nextMode: RetrievalResponse["mode"]) {
    setParams({ mode: nextMode });
  }

  function updateFilter(key: keyof FilterState, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function runRetrieval() {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      retrievalMutation.reset();
      return;
    }
    retrievalMutation.mutate(
      {
        query: trimmedQuery,
        mode,
        limit: 6,
        filters: {
          ...compactFilters(filters),
          status: ["published"],
        },
      },
      {
        onError: () => reportError("Retrieval failed. Check cs-kb-ai and Postgres/pgvector."),
      },
    );
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading retrieval lab" />}>
      <RetrievalWorkspace
        busy={retrievalMutation.isPending}
        collectionOptions={collectionOptions}
        dynamicFilterOptions={dynamicFilterOptions}
        filters={filters}
        mode={mode}
        onModeChange={setMode}
        onRetrieve={runRetrieval}
        onUpdateFilter={updateFilter}
        query={query}
        retrieval={retrievalMutation.data ?? null}
        setQuery={setQuery}
      />
    </Suspense>
  );
}
