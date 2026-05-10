import { useMutation } from "@tanstack/react-query";

import { apiPost } from "@/lib/api";
import type { ChatMessage, GroundedChatResponse } from "@/types";

export function useGroundedChat() {
  return useMutation({
    mutationFn: (payload: {
      question: string;
      filters: Record<string, string[]>;
      limit: number;
      conversation: ChatMessage[];
    }) => apiPost<GroundedChatResponse>("/api/v1/ai/chat", payload),
  });
}
