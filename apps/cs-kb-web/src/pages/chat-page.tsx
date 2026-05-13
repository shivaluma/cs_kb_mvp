import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { defaultFilters, workspacePaths } from "@/constants";
import { useCollections } from "@/hooks/api/kb-index";
import { useChatModelRoutes, useGroundedChat } from "@/hooks/api/chat";
import { useSearchFilterOptions } from "@/hooks/api/search";
import { useUrlSearch } from "@/hooks/use-url-search";
import { compactFilters, optionizeFilterValues } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { ChatMessage, ChatModelRoute, ChatThreadMessage, FilterOption, FilterState, RetrievalResult } from "@/types";

const ChatWorkspace = lazy(() =>
  import("@/workspaces/chat-workspace").then((module) => ({ default: module.ChatWorkspace })),
);

export function ChatPage() {
  const navigate = useNavigate();
  const { getParam } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const initialQuestion = getParam("q", "");
  const initialQuestionSent = useRef("");
  const chatModelRoutesQuery = useChatModelRoutes();
  const collectionsQuery = useCollections();
  const filterOptionsQuery = useSearchFilterOptions();
  const groundedChatMutation = useGroundedChat();
  const [messages, setMessages] = useState<ChatThreadMessage[]>([]);
  const [modelRoute, setModelRoute] = useState<ChatModelRoute>("simple");
  const [scopeFilters, setScopeFilters] = useState<FilterState>(defaultFilters);
  const collectionOptions: FilterOption[] = useMemo(
    () =>
      (collectionsQuery.data ?? []).map((collection) => ({
        label: collection.name,
        value: collection.slug,
      })),
    [collectionsQuery.data],
  );
  const dynamicFilterOptions = useMemo(
    () => ({
      audience: optionizeFilterValues(filterOptionsQuery.data?.audience, "All audiences"),
      vertical: optionizeFilterValues(filterOptionsQuery.data?.vertical, "All verticals"),
      taskType: optionizeFilterValues(filterOptionsQuery.data?.task_types, "All tasks"),
    }),
    [filterOptionsQuery.data],
  );

  useEffect(() => {
    const trimmedInitialQuestion = initialQuestion.trim();
    if (!trimmedInitialQuestion || initialQuestionSent.current === trimmedInitialQuestion) {
      return;
    }
    initialQuestionSent.current = trimmedInitialQuestion;
    askGroundedChat(trimmedInitialQuestion);
  }, [initialQuestion]);

  function askGroundedChat(question: string) {
    const trimmed = question.trim();
    if (!trimmed || groundedChatMutation.isPending) {
      return;
    }
    const userMessage: ChatThreadMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
    };
    const pendingId = crypto.randomUUID();
    const pendingMessage: ChatThreadMessage = {
      id: pendingId,
      role: "assistant",
      content: "Retrieving published SOP units and checking citations...",
      createdAt: new Date().toISOString(),
      pending: true,
    };
    const conversation: ChatMessage[] = messages
      .filter((message) => !message.pending)
      .slice(-6)
      .map((message) => ({ role: message.role, content: message.content }));
    setMessages((current) => [...current, userMessage, pendingMessage]);
    groundedChatMutation.mutate(
      {
        question: trimmed,
        limit: 12,
        conversation,
        model_route: modelRoute,
        filters: {
          ...compactFilters(scopeFilters),
          status: ["published"],
        },
      },
      {
        onSuccess: (response) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === pendingId
                ? {
                    ...message,
                    content: response.answer,
                    pending: false,
                    response,
                  }
                : message,
            ),
          );
          reportNotice(`Grounded answer generated from ${response.citations.length} published citation(s).`);
        },
        onError: (chatError) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === pendingId
                ? {
                    ...message,
                    content: "Chat failed before a grounded answer could be generated. Retrieval/AI service may be unavailable.",
                    pending: false,
                  }
                : message,
            ),
          );
          reportError(chatError instanceof Error ? chatError.message : "SOP Chat failed. Check cs-kb-ai, OpenRouter, and published retrieval data.");
        },
      },
    );
  }

  function updateScopeFilter(key: keyof FilterState, value: string) {
    setScopeFilters((current) => ({ ...current, [key]: value }));
  }

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      reportNotice("Copied grounded answer.");
    } catch {
      reportError("Clipboard permission blocked.");
    }
  }

  function openQuickSource(source: RetrievalResult) {
    sessionStorage.setItem("kb:selected-quick-source", JSON.stringify(source));
    void navigate({
      to: workspacePaths.lookup,
      search: { q: source.heading || source.title, chunk: source.chunk_id } as never,
    });
  }

  function openDocumentSource(source: RetrievalResult) {
    void navigate({
      to: workspacePaths.documents,
      search: {
        document: source.document_id,
        version: source.version_id,
        unit: source.chunk_id,
      } as never,
    });
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading SOP chat" />}>
      <ChatWorkspace
        busy={groundedChatMutation.isPending}
        collectionOptions={collectionOptions}
        dynamicFilterOptions={dynamicFilterOptions}
        filters={scopeFilters}
        fallbackModel={chatModelRoutesQuery.data?.fallback_model}
        messages={messages}
        modelRoutes={chatModelRoutesQuery.data?.routes}
        modelRoute={modelRoute}
        onAsk={askGroundedChat}
        onCopy={copyText}
        onModelRouteChange={setModelRoute}
        onOpenDocument={openDocumentSource}
        onOpenQuickSource={openQuickSource}
        onUpdateFilter={updateScopeFilter}
      />
    </Suspense>
  );
}
