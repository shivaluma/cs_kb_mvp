import { useMutation } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type { AISuggestion, RetrievalResponse, RetrievalResult, SearchResult, SOP } from "@/types";

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
