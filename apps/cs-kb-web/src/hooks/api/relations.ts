import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type { DocumentRelation, RelationStatus, RelationType } from "@/types";

import { queryKeys } from "./query-keys";

export function useRelations(status: RelationStatus | "all" = "unresolved") {
  const query = status === "all" ? "?status=" : `?status=${status}`;
  return useQuery({
    queryKey: queryKeys.relations(status),
    queryFn: () => apiGet<DocumentRelation[]>(`/api/v1/ai/relations${query}`),
  });
}

export function useAssignRelation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { relationId: string; targetDocumentId: string; actor: string }) =>
      apiPost<DocumentRelation>(`/api/v1/ai/relations/${payload.relationId}/assign`, {
        target_document_id: payload.targetDocumentId,
        actor: payload.actor,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-document-relations"] });
    },
  });
}

export function useCreateRelation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      actor: string;
      metadata?: Record<string, unknown>;
      relationType: RelationType;
      sourceChunkId?: string;
      sourceDocumentId: string;
      targetDocumentId?: string;
      targetTitle: string;
    }) =>
      apiPost<DocumentRelation>("/api/v1/ai/relations", {
        actor: payload.actor,
        metadata: payload.metadata ?? {},
        relation_type: payload.relationType,
        source_chunk_id: payload.sourceChunkId || null,
        source_document_id: payload.sourceDocumentId,
        target_document_id: payload.targetDocumentId || null,
        target_title: payload.targetTitle,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-document-relations"] });
    },
  });
}

export function useRejectRelation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { relationId: string; actor: string; rejectionReason?: string }) =>
      apiPost<DocumentRelation>(`/api/v1/ai/relations/${payload.relationId}/reject`, {
        actor: payload.actor,
        rejection_reason: payload.rejectionReason ?? "",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-document-relations"] });
    },
  });
}

export function useArchiveRelation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { relationId: string; actor: string; archiveReason?: string }) =>
      apiPost<DocumentRelation>(`/api/v1/ai/relations/${payload.relationId}/archive`, {
        actor: payload.actor,
        archive_reason: payload.archiveReason ?? "",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-document-relations"] });
    },
  });
}
