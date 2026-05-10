import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type { SynonymGroup, SynonymSuggestion } from "@/types";

import { queryKeys } from "./query-keys";

export function useSynonyms(status: string) {
  return useQuery({
    queryKey: queryKeys.synonyms(status),
    queryFn: () =>
      apiGet<SynonymGroup[]>(`/api/v1/search/synonyms?status=${status}`),
  });
}

export function useSynonymSuggestions() {
  return useQuery({
    queryKey: queryKeys.suggestions,
    queryFn: () =>
      apiGet<SynonymSuggestion[]>(
        "/api/v1/search/synonym-suggestions?status=pending&limit=30",
      ),
  });
}

export function useCreateSynonym() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiPost<SynonymGroup>("/api/v1/search/synonyms", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["search-synonyms"] });
    },
  });
}

export function useTransitionSynonym() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      groupId: string;
      action: "submit-review" | "approve" | "archive";
      actor: string;
    }) =>
      apiPost(`/api/v1/search/synonyms/${payload.groupId}/${payload.action}`, {
        actor: payload.actor,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["search-synonyms"] });
    },
  });
}

export function useSyncSynonyms() {
  return useMutation({
    mutationFn: () =>
      apiPost<{ synonym_count: number }>("/api/v1/search/synonyms/sync", {}),
  });
}

export function useGenerateSuggestions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<SynonymSuggestion[]>(
        "/api/v1/search/synonym-suggestions/generate",
        { days: 14, min_count: 1, limit: 10 },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.suggestions });
    },
  });
}

export function useAcceptSuggestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      suggestionId: string;
      canonical_key: string;
      synonym_type: string;
      actor: string;
      submit_review: boolean;
    }) =>
      apiPost(`/api/v1/search/synonym-suggestions/${payload.suggestionId}/accept`, {
        canonical_key: payload.canonical_key,
        synonym_type: payload.synonym_type,
        actor: payload.actor,
        submit_review: payload.submit_review,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.suggestions });
      queryClient.invalidateQueries({ queryKey: ["search-synonyms"] });
    },
  });
}
