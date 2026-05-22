import { useMutation } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";
import type { AISuggestion, RetrievalResponse, RetrievalResult, SearchFilterOptions, SearchResult, SOP } from "@/types";

import { queryKeys } from "./query-keys";

export function useSearchFilterOptions() {
  return useQuery({
    queryKey: queryKeys.searchFilterOptions,
    queryFn: () => apiGet<SearchFilterOptions>("/api/v1/search/filter-options"),
  });
}

export function useSearchAutocomplete(query: string) {
  const debouncedQuery = useDebouncedValue(query.trim(), 280);
  return useQuery({
    enabled: debouncedQuery.length >= 2,
    queryKey: ["search-autocomplete", debouncedQuery],
    queryFn: () =>
      apiGet<{ query: string; suggestions: string[]; sources: string[] }>(
        `/api/v1/search/autocomplete?q=${encodeURIComponent(debouncedQuery)}`,
      ),
    staleTime: 30000,
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: (payload: {
      query: string;
      include_semantic: boolean;
      filters: Record<string, string[]>;
      debug?: boolean;
    }) =>
      apiPost<{ results?: SearchResult[]; semantic_results?: RetrievalResult[] }>("/api/v1/search", payload),
  });
}

function useDebouncedValue(value: string, delayMs: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timeout);
  }, [delayMs, value]);
  return debounced;
}

export function useSOPList() {
  return useQuery({
    queryKey: queryKeys.sops,
    queryFn: () => apiGet<{ items: SOP[] }>("/api/v1/sops"),
  });
}

export function useSOPDetail(id?: string) {
  return useQuery({
    enabled: Boolean(id),
    queryKey: queryKeys.sop(id ?? ""),
    queryFn: () => apiGet<SOP>(`/api/v1/sops/${id}`),
  });
}

export function useSOP() {
  return useMutation({
    mutationFn: (id: string) => apiGet<SOP>(`/api/v1/sops/${id}`),
  });
}

export function useAISuggest() {
  return useMutation({
    mutationFn: (payload: { query: string; sop_id: string }) =>
      apiPost<AISuggestion>("/api/v1/ai/suggest", payload),
  });
}

export function useRetrieval() {
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiPost<RetrievalResponse>("/api/v1/ai/retrieve", payload),
  });
}
