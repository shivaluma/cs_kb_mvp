import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type {
  ChatMessage,
  ChatModelRoute,
  ChatModelRoutesResponse,
  ChatSessionMessageResponse,
  ChatSessionSummary,
  ChatStoredMessage,
  FilterState,
  GroundedChatResponse,
} from "@/types";

import { queryKeys } from "./query-keys";

export function useChatModelRoutes() {
  return useQuery({
    queryKey: ["chat-model-routes"],
    queryFn: () => apiGet<ChatModelRoutesResponse>("/api/v1/ai/chat/model-routes"),
    staleTime: 60_000,
  });
}

export function useGroundedChat() {
  return useMutation({
    mutationFn: (payload: {
      question: string;
      filters: Record<string, string[]>;
      limit: number;
      conversation: ChatMessage[];
      model_route?: ChatModelRoute;
    }) => apiPost<GroundedChatResponse>("/api/v1/ai/chat", payload, 120000),
  });
}

export function useChatSessions(status = "active") {
  return useQuery({
    queryKey: queryKeys.chatSessions(status),
    queryFn: () => apiGet<ChatSessionSummary[]>(`/api/v1/ai/chat/sessions?status=${status}`),
    staleTime: 10_000,
  });
}

export function useCreateChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { title?: string; model_route?: ChatModelRoute; filters?: Record<string, unknown> }) =>
      apiPost<ChatSessionSummary>("/api/v1/ai/chat/sessions", {
        title: payload.title ?? "",
        model_route: normalizeChatModelRoute(payload.model_route),
        filters: payload.filters ?? {},
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useUpdateChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      sessionId: string;
      title?: string;
      status?: "active" | "archived";
      model_route?: ChatModelRoute;
      filters?: Record<string, unknown>;
    }) =>
      apiPost<ChatSessionSummary>(
        `/api/v1/ai/chat/sessions/${payload.sessionId}/update`,
        {
          title: payload.title,
          status: payload.status,
          model_route: payload.model_route ? normalizeChatModelRoute(payload.model_route) : undefined,
          filters: payload.filters,
        },
        30_000,
      ),
    onSuccess: (_, payload) => {
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.chatSessionMessages(payload.sessionId) });
    },
  });
}

export function useChatSessionMessages(sessionId?: string) {
  return useQuery({
    enabled: Boolean(sessionId),
    queryKey: queryKeys.chatSessionMessages(sessionId ?? ""),
    queryFn: () => apiGet<ChatStoredMessage[]>(`/api/v1/ai/chat/sessions/${sessionId}/messages`),
  });
}

export function useCreateChatSessionMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      sessionId: string;
      question: string;
      filters: FilterState;
      limit: number;
      model_route?: ChatModelRoute;
    }) =>
      apiPost<ChatSessionMessageResponse>(
        `/api/v1/ai/chat/sessions/${payload.sessionId}/messages`,
        {
          question: payload.question,
          filters: {
            collections: payload.filters.collection === "all" ? [] : [payload.filters.collection],
            audience: payload.filters.audience === "all" ? [] : [payload.filters.audience],
            vertical: payload.filters.vertical === "all" ? [] : [payload.filters.vertical],
            task_types: payload.filters.taskType === "all" ? [] : [payload.filters.taskType],
            status: ["published"],
          },
          limit: payload.limit,
          model_route: normalizeChatModelRoute(payload.model_route),
        },
        120_000,
      ),
    onSuccess: (_, payload) => {
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.chatSessionMessages(payload.sessionId) });
    },
  });
}

const VALID_CHAT_MODEL_ROUTES = new Set<ChatModelRoute>([
  "auto",
  "simple",
  "policy",
  "high_risk",
  "complex",
  "google/gemini-2.5-flash",
  "google/gemini-3.1-flash-lite-preview",
  "google/gemini-3-flash-preview",
  "anthropic/claude-3.5-haiku",
]);

function normalizeChatModelRoute(value: unknown): ChatModelRoute {
  return typeof value === "string" && VALID_CHAT_MODEL_ROUTES.has(value as ChatModelRoute)
    ? (value as ChatModelRoute)
    : "simple";
}
