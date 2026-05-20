import { useMutation } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type { AISuggestion, RetrievalResponse, RetrievalResult, SearchFilterOptions, SearchResult, SOP } from "@/types";

import { queryKeys } from "./query-keys";

export function useSearchFilterOptions() {
  return useQuery({
    queryKey: queryKeys.searchFilterOptions,
    queryFn: () => apiGet<SearchFilterOptions>("/api/v1/search/filter-options"),
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: (payload: {
      query: string;
      include_semantic: boolean;
      filters: Record<string, string[]>;
    }) =>
      apiPost<{ results?: SearchResult[]; semantic_results?: RetrievalResult[] }>("/api/v1/search", payload),
  });
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
