import { useMutation, useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type { ChatMessage, ChatModelRoute, ChatModelRoutesResponse, GroundedChatResponse } from "@/types";

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
