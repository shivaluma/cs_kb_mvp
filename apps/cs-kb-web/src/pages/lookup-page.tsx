import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { defaultFilters } from "@/constants";
import { useHomepage } from "@/hooks/api/homepage";
import { useCollections, useRecordKBEvent } from "@/hooks/api/kb-index";
import { useAISuggest, useSearch, useSearchAutocomplete, useSearchFilterOptions, useSOP } from "@/hooks/api/search";
import { useUrlSearch } from "@/hooks/use-url-search";
import { compactFilters, optionizeFilterValues, toSearchResult } from "@/lib/format";
import { buildSopSourceLink, SOP_SOURCE_STORAGE_KEY } from "@/lib/sop-source-link";
import { useFeedback } from "@/providers/feedback-context";
import type { AISuggestion, FilterOption, FilterState, Macro, RetrievalResult, SOP } from "@/types";

const LookupWorkspace = lazy(() =>
  import("@/workspaces/lookup-workspace").then((module) => ({ default: module.LookupWorkspace })),
);

export function LookupPage() {
  const navigate = useNavigate();
  const { getParam, setParams } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const query = getParam("q", "");
  const hasSearchQuery = query.trim().length > 0;
  const chunkId = getParam("chunk", "");
  const [filters, setFilters] = useState<FilterState>({
    collection: getParam("collection", defaultFilters.collection),
    audience: getParam("audience", defaultFilters.audience),
    contentType: getParam("contentType", defaultFilters.contentType),
    taskType: getParam("taskType", defaultFilters.taskType),
    category: getParam("category", defaultFilters.category),
    vertical: getParam("vertical", defaultFilters.vertical),
  });
  const [selected, setSelected] = useState<SOP | null>(null);
  const [selectedDocumentMatch, setSelectedDocumentMatch] = useState<RetrievalResult | null>(null);
  const [copied, setCopied] = useState("");
  const [copyError, setCopyError] = useState("");
  const autoSelectedInitialSop = useRef(false);
  const autoSearchedInitialQuery = useRef("");
  const homepageQuery = useHomepage();
  const collectionsQuery = useCollections();
  const filterOptionsQuery = useSearchFilterOptions();
  const searchMutation = useSearch();
  const autocompleteQuery = useSearchAutocomplete(query);
  const sopMutation = useSOP();
  const aiSuggestMutation = useAISuggest();
  const eventMutation = useRecordKBEvent();
  const [searchEventId, setSearchEventId] = useState("");
  const homepage = homepageQuery.data;
  const searchResults = hasSearchQuery ? (searchMutation.data?.results ?? []) : [];
  const catalogSearchResults = searchResults.filter((result) => !result.chunk_id && result.result_type !== "sop_chunk");
  const semanticResults = hasSearchQuery ? (searchMutation.data?.semantic_results ?? []) : [];
  const aiSuggestion = (aiSuggestMutation.data as AISuggestion | undefined) ?? null;
  const booting = homepageQuery.isLoading && !homepageQuery.data && !homepageQuery.error && !searchMutation.data;
  const collectionOptions: FilterOption[] = useMemo(
    () =>
      (collectionsQuery.data ?? []).map((collection) => ({
        label: collection.name,
        value: collection.slug,
      })),
    [collectionsQuery.data],
  );
  const dynamicFilterOptions = useMemo(
    () => ({
      audience: optionizeFilterValues(filterOptionsQuery.data?.audience, "All audiences"),
      vertical: optionizeFilterValues(filterOptionsQuery.data?.vertical, "All verticals"),
      category: optionizeFilterValues(filterOptionsQuery.data?.category, "All categories"),
      taskType: optionizeFilterValues(filterOptionsQuery.data?.task_types, "All tasks"),
    }),
    [filterOptionsQuery.data],
  );
  const hasStructuredFilters =
    filters.collection !== "all" ||
    filters.contentType !== "all" ||
    filters.taskType !== "all";
  const listSource = useMemo(() => {
    if (!hasSearchQuery) {
      return [];
    }
    if (hasStructuredFilters) {
      return [];
    }
    if (catalogSearchResults.length > 0) {
      return catalogSearchResults;
    }
    return searchMutation.data ? [] : (homepage?.most_viewed ?? []).map(toSearchResult);
  }, [catalogSearchResults, hasSearchQuery, hasStructuredFilters, homepage, searchMutation.data]);
  const feedbackTotal = selected ? selected.analytics.helpful + selected.analytics.not_helpful : 0;
  const helpfulRate = feedbackTotal && selected ? Math.round((selected.analytics.helpful / feedbackTotal) * 100) : 0;

  useEffect(() => {
    if (!chunkId || selectedDocumentMatch) {
      return;
    }
    const stored = sessionStorage.getItem("kb:selected-quick-source");
    if (!stored) {
      return;
    }
    try {
      const parsed = JSON.parse(stored) as RetrievalResult;
      if (parsed.chunk_id === chunkId) {
        setSelectedDocumentMatch(parsed);
      }
    } catch {
      sessionStorage.removeItem("kb:selected-quick-source");
    }
  }, [chunkId, selectedDocumentMatch]);

  useEffect(() => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery || searchMutation.data || searchMutation.isPending || autoSearchedInitialQuery.current === trimmedQuery) {
      return;
    }
    autoSearchedInitialQuery.current = trimmedQuery;
    runSearch(trimmedQuery, filters);
  }, [filters, query, searchMutation.data, searchMutation.isPending]);

  useEffect(() => {
    if (!autoSelectedInitialSop.current && !selected && homepage?.recently_updated?.[0] && !selectedDocumentMatch) {
      autoSelectedInitialSop.current = true;
      setSelected(homepage.recently_updated[0]);
    }
  }, [homepage, selected, selectedDocumentMatch]);

  function setQuery(nextQuery: string) {
    if (!nextQuery.trim()) {
      searchMutation.reset();
      setSelectedDocumentMatch(null);
      setParams({ q: nextQuery, chunk: "" });
      return;
    }
    setParams({ q: nextQuery });
  }

  function runSearch(nextQuery = query, nextFilters = filters) {
    const trimmedQuery = nextQuery.trim();
    if (!trimmedQuery) {
      searchMutation.reset();
      setSelectedDocumentMatch(null);
      setParams({ chunk: "" });
      return;
    }
    if ([...trimmedQuery].length === 1) {
      reportNotice("Enter at least 2 characters for title or macro lookup.");
      return;
    }
    const nextSearchEventId = crypto.randomUUID();
    setSearchEventId(nextSearchEventId);
    eventMutation.mutate({
      action: "sop_search",
      entity_type: "search",
      metadata: {
        search_event_id: nextSearchEventId,
        query: trimmedQuery,
        filters: compactFilters(nextFilters),
      },
    });
    searchMutation.mutate(
      {
        query: trimmedQuery,
        include_semantic: true,
        filters: compactFilters(nextFilters),
      },
      {
        onError: () => reportError("Search failed. Keyword SOP lookup should stay available even when AI is down."),
      },
    );
  }

  function updateFilter(key: keyof FilterState, value: string) {
    const nextFilters = { ...filters, [key]: value };
    setFilters(nextFilters);
    setParams({ [key]: value === "all" ? "" : value });
    runSearch(query, nextFilters);
  }

  function openSOP(id: string) {
    sopMutation.mutate(id, {
      onSuccess: (sop) => {
        eventMutation.mutate({
          action: "full_sop_open",
          entity_type: "sop_version",
          entity_id: sop.current_version_id,
          metadata: {
            search_event_id: searchEventId,
            query,
            sop_id: sop.id,
            title: sop.title,
          },
        });
        setSelected(sop);
        setSelectedDocumentMatch(null);
        setParams({ chunk: "" });
      },
      onError: () => reportError("Cannot open this SOP. It may be archived or unavailable."),
    });
  }

  function askAI() {
    if (!selected) {
      return;
    }
    aiSuggestMutation.mutate(
      { query, sop_id: selected.id },
      { onError: () => reportError("AI suggestion failed.") },
    );
  }

  function selectDocumentMatch(match: RetrievalResult) {
    const rank = semanticResults.findIndex((result) => result.chunk_id === match.chunk_id) + 1;
    const unitType = String(match.metadata.unit_type ?? match.section);
    const scope = String(match.metadata.retrieval_scope ?? "unit");
    const isFullSop = scope === "document" || unitType === "full_sop";
    eventMutation.mutate({
      action: "search_result_click",
      entity_type: "chunk",
      entity_id: match.chunk_id,
      metadata: {
        search_event_id: searchEventId,
        query,
        rank: rank > 0 ? rank : undefined,
        target_title: match.heading || match.title,
        document_title: match.title,
        unit_type: unitType,
      },
    });
    eventMutation.mutate({
      action: isFullSop ? "full_sop_open" : "quick_answer_open",
      entity_type: "chunk",
      entity_id: match.chunk_id,
      metadata: {
        search_event_id: searchEventId,
        query,
        rank: rank > 0 ? rank : undefined,
        target_title: match.heading || match.title,
        document_title: match.title,
      },
    });
    setSelectedDocumentMatch(match);
    setSelected(null);
    sessionStorage.setItem("kb:selected-quick-source", JSON.stringify(match));
    setParams({ chunk: match.chunk_id });
  }

  function openDocumentSource(match: RetrievalResult) {
    const link = buildSopSourceLink(match, query);
    if (!link) {
      selectDocumentMatch(match);
      return;
    }
    const rank = semanticResults.findIndex((result) => result.chunk_id === match.chunk_id) + 1;
    sessionStorage.setItem(SOP_SOURCE_STORAGE_KEY, JSON.stringify(match));
    eventMutation.mutate({
      action: "full_sop_open",
      entity_type: "chunk",
      entity_id: match.chunk_id,
      metadata: {
        search_event_id: searchEventId,
        query,
        rank: rank > 0 ? rank : undefined,
        target_title: match.heading || match.title,
        document_title: match.title,
        sop_id: link.sopId,
        surface: "lookup_source_card",
      },
    });
    void navigate({
      to: "/sop/$sopId",
      params: { sopId: link.sopId },
      search: link.search as never,
    });
  }

  async function copyMacro(macro: Macro) {
    setCopied("");
    setCopyError("");
    try {
      await navigator.clipboard.writeText(macro.content);
      eventMutation.mutate({
        action: "macro_copy",
        entity_type: "macro",
        metadata: {
          search_event_id: searchEventId,
          query,
          target_title: macro.title,
        },
      });
      setCopied(macro.title);
      window.setTimeout(() => setCopied(""), 1800);
      reportNotice(`Copied macro: ${macro.title}.`);
    } catch {
      setCopyError(`Clipboard permission blocked. Macro selected: ${macro.title}`);
      window.setTimeout(() => setCopyError(""), 2600);
    }
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading lookup" />}>
      <LookupWorkspace
        aiSuggestion={aiSuggestion}
        booting={booting && searchMutation.isIdle}
        copied={copied}
        copyError={copyError}
        collectionOptions={collectionOptions}
        dynamicFilterOptions={dynamicFilterOptions}
        feedbackRate={helpfulRate}
        filters={filters}
        listSource={listSource}
        loading={searchMutation.isPending}
        onAskAI={askAI}
        onCopyMacro={copyMacro}
        onOpenSOP={openSOP}
        onOpenSourceMatch={openDocumentSource}
        onRunSearch={() => runSearch()}
        onSuggestionSelect={(suggestion) => {
          setQuery(suggestion);
          runSearch(suggestion);
        }}
        onSelectDocumentMatch={selectDocumentMatch}
        onUpdateFilter={updateFilter}
        query={query}
        selected={selected}
        selectedDocumentMatch={selectedDocumentMatch}
        selectedVersion={selected?.current_version}
        semanticResults={semanticResults}
        searchEventId={searchEventId}
        suggestions={autocompleteQuery.data?.suggestions ?? []}
        setQuery={setQuery}
      />
    </Suspense>
  );
}
