import { useMutation, useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type {
  ActionTemplateSummary,
  IssueRouterItem,
  KBCollectionDetail,
  KBCollectionSummary,
  ToolLinkSummary,
} from "@/types";

import { queryKeys } from "./query-keys";

export function useCollections() {
  return useQuery({
    queryKey: queryKeys.collections,
    queryFn: () => apiGet<KBCollectionSummary[]>("/api/v1/ai/collections"),
  });
}

export function useCollection(collectionId?: string) {
  return useQuery({
    enabled: Boolean(collectionId),
    queryKey: queryKeys.collection(collectionId ?? ""),
    queryFn: () => apiGet<KBCollectionDetail>(`/api/v1/ai/collections/${collectionId}`),
  });
}

export function useIssueRouter(params: {
  query?: string;
  audience?: string;
  vertical?: string;
  collection?: string;
  taskType?: string;
  riskLevel?: string;
}) {
  const normalized = {
    query: params.query ?? "",
    audience: params.audience ?? "",
    vertical: params.vertical ?? "",
    collection: params.collection ?? "",
    task_type: params.taskType ?? "",
    risk_level: params.riskLevel ?? "",
  };
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(normalized)) {
    if (value) {
      search.set(key, value);
    }
  }
  return useQuery({
    queryKey: queryKeys.issueRouter(normalized),
    queryFn: () => {
      const suffix = search.toString();
      return apiGet<IssueRouterItem[]>(`/api/v1/ai/issue-router${suffix ? `?${suffix}` : ""}`);
    },
  });
}

export function useTools(collection = "") {
  const search = new URLSearchParams();
  if (collection) {
    search.set("collection", collection);
  }
  return useQuery({
    queryKey: queryKeys.tools(collection),
    queryFn: () => {
      const suffix = search.toString();
      return apiGet<ToolLinkSummary[]>(`/api/v1/ai/tools${suffix ? `?${suffix}` : ""}`);
    },
  });
}

export function useActionTemplates(collection = "") {
  const search = new URLSearchParams();
  if (collection) {
    search.set("collection", collection);
  }
  return useQuery({
    queryKey: queryKeys.actionTemplates(collection),
    queryFn: () => {
      const suffix = search.toString();
      return apiGet<ActionTemplateSummary[]>(`/api/v1/ai/action-templates${suffix ? `?${suffix}` : ""}`);
    },
  });
}

export function useRecordKBEvent() {
  return useMutation({
    mutationFn: (payload: {
      action: string;
      entity_type?: string;
      entity_id?: string;
      actor?: string;
      metadata?: Record<string, unknown>;
    }) =>
      apiPost("/api/v1/ai/kb-events", {
        action: payload.action,
        entity_type: payload.entity_type ?? "kb_index",
        entity_id: payload.entity_id ?? null,
        actor: payload.actor ?? "cs-ops-ui",
        metadata: payload.metadata ?? {},
      }),
  });
}
