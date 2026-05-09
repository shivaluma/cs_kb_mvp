import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPatch, apiPost, apiUpload } from "@/lib/api";
import type {
  AISuggestion,
  DocumentChunk,
  DocumentSummary,
  ExtractionUnit,
  ExtractionUnitUpdate,
  FilterState,
  Homepage,
  RetrievalResponse,
  RetrievalResult,
  SearchResult,
  SOP,
  SynonymGroup,
  SynonymSuggestion,
  VersionSummary,
} from "@/types";

export const queryKeys = {
  homepage: ["homepage"] as const,
  documents: ["ai-documents"] as const,
  versions: (documentId: string) => ["ai-document-versions", documentId] as const,
  chunks: (documentId: string, versionId: string) =>
    ["ai-document-chunks", documentId, versionId] as const,
  extractionUnits: (documentId: string, versionId: string) =>
    ["ai-extraction-units", documentId, versionId] as const,
  synonyms: (status: string) => ["search-synonyms", status] as const,
  suggestions: ["search-synonym-suggestions"] as const,
  search: (query: string, filters: FilterState) => ["search", query, filters] as const,
  retrieval: (query: string, mode: string, filters: FilterState) =>
    ["retrieval", query, mode, filters] as const,
};

export function useHomepage() {
  return useQuery({
    queryKey: queryKeys.homepage,
    queryFn: () => apiGet<Homepage>("/api/v1/homepage"),
  });
}

export function useDocuments() {
  return useQuery({
    queryKey: queryKeys.documents,
    queryFn: () => apiGet<DocumentSummary[]>("/api/v1/ai/documents"),
  });
}

export function useDocumentVersions(documentId?: string) {
  return useQuery({
    enabled: Boolean(documentId),
    queryKey: queryKeys.versions(documentId ?? ""),
    queryFn: () =>
      apiGet<VersionSummary[]>(`/api/v1/ai/documents/${documentId}/versions`),
  });
}

export function useDocumentChunks(documentId?: string, versionId?: string) {
  return useQuery({
    enabled: Boolean(documentId),
    queryKey: queryKeys.chunks(documentId ?? "", versionId ?? ""),
    queryFn: () => {
      const query = versionId ? `?version_id=${versionId}` : "";
      return apiGet<DocumentChunk[]>(`/api/v1/ai/documents/${documentId}/chunks${query}`);
    },
  });
}

export function useExtractionUnits(documentId?: string, versionId?: string) {
  return useQuery({
    enabled: Boolean(documentId),
    queryKey: queryKeys.extractionUnits(documentId ?? "", versionId ?? ""),
    queryFn: () => {
      const query = versionId ? `?version_id=${versionId}` : "";
      return apiGet<ExtractionUnit[]>(`/api/v1/ai/documents/${documentId}/extraction-units${query}`);
    },
  });
}

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

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) =>
      apiUpload<{
        title: string;
        version_number: number;
        chunk_count: number;
      }>("/api/v1/ai/documents/upload", form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
  });
}

export function usePublishVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { versionId: string; actor: string }) =>
      apiPost(`/api/v1/ai/versions/${payload.versionId}/publish`, {
        actor: payload.actor,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      queryClient.invalidateQueries({ queryKey: ["ai-document-versions"] });
    },
  });
}

export function useUpdateExtractionUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { unitId: string; update: ExtractionUnitUpdate }) =>
      apiPatch<ExtractionUnit>(`/api/v1/ai/extraction-units/${payload.unitId}`, payload.update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-extraction-units"] });
      queryClient.invalidateQueries({ queryKey: ["ai-document-chunks"] });
      queryClient.invalidateQueries({ queryKey: ["ai-document-versions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
  });
}

export function useArchiveDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { documentId: string; actor: string }) =>
      apiPost(`/api/v1/ai/documents/${payload.documentId}/archive`, {
        actor: payload.actor,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      queryClient.invalidateQueries({ queryKey: ["ai-document-versions"] });
      queryClient.invalidateQueries({ queryKey: ["ai-document-chunks"] });
      queryClient.invalidateQueries({ queryKey: ["ai-extraction-units"] });
    },
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
