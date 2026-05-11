import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPatch, apiPost, apiUpload } from "@/lib/api";
import type {
  DocumentChunk,
  ExtractionPipelineInspection,
  ExtractionJobSummary,
  DocumentMetadataPreview,
  DocumentSummary,
  ExtractionUnit,
  ExtractionUnitCreate,
  ExtractionUnitUpdate,
  PublishReadiness,
  VersionRawText,
  VersionSummary,
} from "@/types";

import { queryKeys } from "./query-keys";

export function useDocuments() {
  return useQuery({
    queryKey: queryKeys.documents,
    queryFn: () => apiGet<DocumentSummary[]>("/api/v1/ai/documents"),
    refetchInterval: (query) => {
      const documents = query.state.data as DocumentSummary[] | undefined;
      return documents?.some((document) => String(document.metadata?.extraction_status ?? "") === "extracting") ? 4000 : false;
    },
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

export function useVersionRawText(versionId?: string) {
  return useQuery({
    enabled: Boolean(versionId),
    queryKey: queryKeys.versionRaw(versionId ?? ""),
    queryFn: () => apiGet<VersionRawText>(`/api/v1/ai/versions/${versionId}/raw`),
  });
}

export function useExtractionPipeline(versionId?: string) {
  return useQuery({
    enabled: Boolean(versionId),
    queryKey: queryKeys.extractionPipeline(versionId ?? ""),
    queryFn: () => apiGet<ExtractionJobSummary[]>(`/api/v1/ai/versions/${versionId}/extraction-pipeline`),
  });
}

export function useExtractionPipelineInspection(versionId?: string) {
  return useQuery({
    enabled: Boolean(versionId),
    queryKey: queryKeys.extractionPipelineInspection(versionId ?? ""),
    queryFn: () => apiGet<ExtractionPipelineInspection>(`/api/v1/ai/versions/${versionId}/extraction-pipeline/inspection`),
    retry: false,
  });
}

export function usePublishReadiness(versionId?: string) {
  return useQuery({
    enabled: Boolean(versionId),
    queryKey: queryKeys.publishReadiness(versionId ?? ""),
    queryFn: () => apiGet<PublishReadiness>(`/api/v1/ai/versions/${versionId}/publish-readiness`),
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

export function useUploadDocumentAsync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) =>
      apiUpload<{
        title: string;
        version_number: number;
        chunk_count: number;
      }>("/api/v1/ai/documents/upload-async", form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
  });
}

export function useDocumentMetadataPreview() {
  return useMutation({
    mutationFn: (form: FormData) =>
      apiUpload<DocumentMetadataPreview>("/api/v1/ai/documents/metadata-preview", form),
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
      queryClient.invalidateQueries({ queryKey: ["ai-publish-readiness"] });
    },
  });
}

export function useBulkReviewVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { versionId: string; actor: string; reviewStatus: "reviewed" | "approved"; scope?: "all" | "atomic"; force?: boolean }) =>
      apiPost(`/api/v1/ai/versions/${payload.versionId}/bulk-review`, {
        actor: payload.actor,
        review_status: payload.reviewStatus,
        scope: payload.scope ?? "all",
        force: payload.force ?? false,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      queryClient.invalidateQueries({ queryKey: ["ai-document-versions"] });
      queryClient.invalidateQueries({ queryKey: ["ai-document-chunks"] });
      queryClient.invalidateQueries({ queryKey: ["ai-extraction-units"] });
      queryClient.invalidateQueries({ queryKey: ["ai-publish-readiness"] });
    },
  });
}

export function useUpdateExtractionUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { unitId: string; update: ExtractionUnitUpdate }) =>
      apiPatch<ExtractionUnit>(`/api/v1/ai/extraction-units/${payload.unitId}`, payload.update),
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: ["ai-extraction-units"] });
      await queryClient.cancelQueries({ queryKey: ["ai-document-chunks"] });

      const previousExtractionUnits = queryClient.getQueriesData<ExtractionUnit[]>({
        queryKey: ["ai-extraction-units"],
      });
      const previousChunks = queryClient.getQueriesData<DocumentChunk[]>({
        queryKey: ["ai-document-chunks"],
      });

      queryClient.setQueriesData<ExtractionUnit[]>(
        { queryKey: ["ai-extraction-units"] },
        (current) =>
          current?.map((unit) =>
            unit.unit_id === payload.unitId
              ? {
                  ...unit,
                  title: payload.update.title,
                  content: payload.update.content,
                  unit_type: payload.update.unit_type,
                  confidence: payload.update.confidence,
                  review_status: payload.update.review_status,
                  metadata: payload.update.metadata,
                }
              : unit,
          ) ?? current,
      );
      queryClient.setQueriesData<DocumentChunk[]>(
        { queryKey: ["ai-document-chunks"] },
        (current) =>
          current?.map((chunk) =>
            chunk.chunk_id === payload.unitId
              ? {
                  ...chunk,
                  heading: payload.update.title,
                  content: payload.update.content,
                  section: payload.update.unit_type,
                  metadata: {
                    ...chunk.metadata,
                    ...payload.update.metadata,
                    unit_type: payload.update.unit_type,
                    confidence: payload.update.confidence,
                    review_status: payload.update.review_status,
                  },
                }
              : chunk,
          ) ?? current,
      );

      return { previousExtractionUnits, previousChunks };
    },
    onError: (_error, _payload, context) => {
      context?.previousExtractionUnits.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
      context?.previousChunks.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSuccess: (unit) => {
      queryClient.invalidateQueries({ queryKey: ["ai-publish-readiness"] });
      queryClient.setQueriesData<ExtractionUnit[]>(
        { queryKey: ["ai-extraction-units"] },
        (current) => current?.map((item) => (item.unit_id === unit.unit_id ? unit : item)) ?? current,
      );
      queryClient.setQueriesData<DocumentChunk[]>(
        { queryKey: ["ai-document-chunks"] },
        (current) =>
          current?.map((chunk) =>
            chunk.chunk_id === unit.unit_id
              ? {
                  ...chunk,
                  heading: unit.title,
                  content: unit.content,
                  section: unit.unit_type,
                  metadata: unit.metadata,
                }
              : chunk,
          ) ?? current,
      );
    },
  });
}

export function useCreateExtractionUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { versionId: string; unit: ExtractionUnitCreate }) =>
      apiPost<ExtractionUnit>(`/api/v1/ai/versions/${payload.versionId}/extraction-units`, payload.unit),
    onSuccess: (unit) => {
      queryClient.invalidateQueries({ queryKey: ["ai-publish-readiness"] });
      queryClient.setQueriesData<ExtractionUnit[]>(
        { queryKey: ["ai-extraction-units"] },
        (current) => (current ? [...current, unit].sort((left, right) => left.unit_index - right.unit_index) : [unit]),
      );
      queryClient.invalidateQueries({ queryKey: ["ai-document-chunks"] });
      queryClient.invalidateQueries({ queryKey: ["ai-document-versions"] });
      queryClient.invalidateQueries({ queryKey: ["ai-documents"] });
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
