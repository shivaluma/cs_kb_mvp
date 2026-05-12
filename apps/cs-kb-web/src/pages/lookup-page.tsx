import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { RouteLoading } from "@/components/route-loading";
import { defaultFilters } from "@/constants";
import { useHomepage } from "@/hooks/api/homepage";
import { useAISuggest, useSearch, useSOP } from "@/hooks/api/search";
import { useUrlSearch } from "@/hooks/use-url-search";
import { compactFilters, toSearchResult } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { AISuggestion, FilterState, Macro, RetrievalResult, SOP } from "@/types";

const LookupWorkspace = lazy(() =>
  import("@/workspaces/lookup-workspace").then((module) => ({ default: module.LookupWorkspace })),
);

export function LookupPage() {
  const { getParam, setParams } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const query = getParam("q", "");
  const hasSearchQuery = query.trim().length > 0;
  const chunkId = getParam("chunk", "");
  const [filters, setFilters] = useState<FilterState>({
    audience: getParam("audience", defaultFilters.audience),
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
  const searchMutation = useSearch();
  const sopMutation = useSOP();
  const aiSuggestMutation = useAISuggest();
  const homepage = homepageQuery.data;
  const searchResults = hasSearchQuery ? (searchMutation.data?.results ?? []) : [];
  const semanticResults = hasSearchQuery ? (searchMutation.data?.semantic_results ?? []) : [];
  const aiSuggestion = (aiSuggestMutation.data as AISuggestion | undefined) ?? null;
  const booting = homepageQuery.isLoading && !homepageQuery.data && !homepageQuery.error && !searchMutation.data;
  const listSource = useMemo(() => {
    if (!hasSearchQuery) {
      return [];
    }
    if (searchResults.length > 0) {
      return searchResults;
    }
    return searchMutation.data ? [] : (homepage?.most_viewed ?? []).map(toSearchResult);
  }, [hasSearchQuery, homepage, searchMutation.data, searchResults]);
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
    setSelectedDocumentMatch(match);
    setSelected(null);
    sessionStorage.setItem("kb:selected-quick-source", JSON.stringify(match));
    setParams({ chunk: match.chunk_id });
  }

  async function copyMacro(macro: Macro) {
    setCopied("");
    setCopyError("");
    try {
      await navigator.clipboard.writeText(macro.content);
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
        feedbackRate={helpfulRate}
        filters={filters}
        listSource={listSource}
        loading={searchMutation.isPending}
        onAskAI={askAI}
        onCopyMacro={copyMacro}
        onOpenSOP={openSOP}
        onRunSearch={() => runSearch()}
        onSelectDocumentMatch={selectDocumentMatch}
        onUpdateFilter={updateFilter}
        query={query}
        selected={selected}
        selectedDocumentMatch={selectedDocumentMatch}
        selectedVersion={selected?.current_version}
        semanticResults={semanticResults}
        setQuery={setQuery}
      />
    </Suspense>
  );
}
