import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type { DocumentRelation, RelationStatus } from "@/types";

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
