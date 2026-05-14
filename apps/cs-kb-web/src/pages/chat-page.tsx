import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { defaultFilters, workspacePaths } from "@/constants";
import { useCollections, useRecordKBEvent } from "@/hooks/api/kb-index";
import {
  useChatModelRoutes,
  useChatSessionMessages,
  useChatSessions,
  useCreateChatSession,
  useCreateChatSessionMessage,
  useUpdateChatSession,
} from "@/hooks/api/chat";
import { useSearchFilterOptions } from "@/hooks/api/search";
import { useUrlSearch } from "@/hooks/use-url-search";
import { optionizeFilterValues } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type {
  ChatModelRoute,
  ChatStoredMessage,
  ChatThreadMessage,
  FilterOption,
  FilterState,
  GroundedChatResponse,
  RetrievalResult,
} from "@/types";

const ChatWorkspace = lazy(() =>
  import("@/workspaces/chat-workspace").then((module) => ({ default: module.ChatWorkspace })),
);

export function ChatPage() {
  const navigate = useNavigate();
  const { getParam } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const initialQuestion = getParam("q", "");
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const routeSessionId = chatSessionIdFromPathname(pathname);
  const initialQuestionSent = useRef("");
  const chatModelRoutesQuery = useChatModelRoutes();
  const collectionsQuery = useCollections();
  const filterOptionsQuery = useSearchFilterOptions();
  const chatSessionsQuery = useChatSessions();
  const createChatSessionMutation = useCreateChatSession();
  const updateChatSessionMutation = useUpdateChatSession();
  const createChatSessionMessageMutation = useCreateChatSessionMessage();
  const eventMutation = useRecordKBEvent();
  const [activeSessionId, setActiveSessionId] = useState("");
  const chatSessionMessagesQuery = useChatSessionMessages(activeSessionId);
  const [messages, setMessages] = useState<ChatThreadMessage[]>([]);
  const [modelRoute, setModelRoute] = useState<ChatModelRoute>("simple");
  const [scopeFilters, setScopeFilters] = useState<FilterState>(defaultFilters);
  const busy =
    createChatSessionMutation.isPending ||
    createChatSessionMessageMutation.isPending ||
    updateChatSessionMutation.isPending;
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
    if (routeSessionId && routeSessionId !== activeSessionId) {
      setActiveSessionId(routeSessionId);
    }
  }, [activeSessionId, routeSessionId]);

  useEffect(() => {
    if (!routeSessionId && !activeSessionId && chatSessionsQuery.data?.length) {
      setActiveSessionId(chatSessionsQuery.data[0].id);
    }
  }, [activeSessionId, chatSessionsQuery.data, routeSessionId]);

  useEffect(() => {
    const activeSession = chatSessionsQuery.data?.find((session) => session.id === activeSessionId);
    if (!activeSession) {
      return;
    }
    if (isChatModelRoute(activeSession.model_route)) {
      setModelRoute(activeSession.model_route);
    }
    setScopeFilters((current) => ({
      ...current,
      collection: firstFilterValue(activeSession.filters.collections) ?? "all",
      audience: firstFilterValue(activeSession.filters.audience) ?? "all",
      vertical: firstFilterValue(activeSession.filters.vertical) ?? "all",
      taskType: firstFilterValue(activeSession.filters.task_types) ?? "all",
    }));
  }, [activeSessionId, chatSessionsQuery.data]);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }
    if (chatSessionMessagesQuery.data) {
      setMessages(chatSessionMessagesQuery.data.map(storedMessageToThreadMessage));
    }
  }, [activeSessionId, chatSessionMessagesQuery.data]);

  useEffect(() => {
    const trimmedInitialQuestion = initialQuestion.trim();
    if (!trimmedInitialQuestion || initialQuestionSent.current === trimmedInitialQuestion) {
      return;
    }
    initialQuestionSent.current = trimmedInitialQuestion;
    askGroundedChat(trimmedInitialQuestion);
  }, [initialQuestion]);

  async function ensureSession() {
    if (activeSessionId) {
      return activeSessionId;
    }
    const session = await createChatSessionMutation.mutateAsync({
      model_route: modelRoute,
      filters: {},
    });
    setActiveSessionId(session.id);
    navigateToChatSession(navigate, session.id);
    return session.id;
  }

  async function askGroundedChat(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) {
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
    setMessages((current) => [...current, userMessage, pendingMessage]);
    const chatEventId = crypto.randomUUID();
    eventMutation.mutate({
      action: "chat_message_sent",
      entity_type: "chat_session",
      entity_id: activeSessionId || undefined,
      metadata: {
        chat_event_id: chatEventId,
        question: trimmed,
        model_route: modelRoute,
        filters: scopeFilters,
      },
    });
    try {
      const sessionId = await ensureSession();
      const chatResponse = await createChatSessionMessageMutation.mutateAsync({
        sessionId,
        question: trimmed,
        filters: scopeFilters,
        limit: 12,
        model_route: modelRoute,
      });
      setActiveSessionId(chatResponse.session.id);
      navigateToChatSession(navigate, chatResponse.session.id);
      eventMutation.mutate({
        action: "chat_answer_cited",
        entity_type: "chat_session",
        entity_id: chatResponse.session.id,
        metadata: {
          chat_event_id: chatEventId,
          citation_count: chatResponse.response.citations.length,
          source_chunk_ids: chatResponse.response.citations.map((citation) => citation.chunk_id),
          confidence: chatResponse.response.confidence,
          model_route: chatResponse.response.model_route,
        },
      });
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingId
            ? {
                ...message,
                content: chatResponse.response.answer,
                pending: false,
                response: chatResponse.response,
              }
            : message,
        ),
      );
      reportNotice(`Grounded answer generated from ${chatResponse.response.citations.length} published citation(s).`);
    } catch (chatError) {
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
    }
  }

  async function startNewSession() {
    if (busy) {
      return;
    }
    try {
      const session = await createChatSessionMutation.mutateAsync({
        model_route: modelRoute,
        filters: {},
      });
      setActiveSessionId(session.id);
      navigateToChatSession(navigate, session.id);
      setMessages([]);
      reportNotice("New chat session created.");
    } catch (error) {
      reportError(error instanceof Error ? error.message : "Could not create chat session.");
    }
  }

  function selectSession(sessionId: string) {
    if (sessionId === activeSessionId) {
      if (routeSessionId !== sessionId) {
        navigateToChatSession(navigate, sessionId);
      }
      return;
    }
    setActiveSessionId(sessionId);
    navigateToChatSession(navigate, sessionId);
  }

  async function archiveSession(sessionId: string) {
    if (!sessionId || updateChatSessionMutation.isPending) {
      return;
    }
    try {
      await updateChatSessionMutation.mutateAsync({ sessionId, status: "archived" });
      if (sessionId === activeSessionId) {
        const nextSession = chatSessionsQuery.data?.find((session) => session.id !== sessionId);
        setActiveSessionId(nextSession?.id ?? "");
        if (!nextSession) {
          setMessages([]);
          void navigate({ to: workspacePaths.chat });
        } else {
          navigateToChatSession(navigate, nextSession.id);
        }
      }
      reportNotice("Chat session archived.");
    } catch (error) {
      reportError(error instanceof Error ? error.message : "Could not archive chat session.");
    }
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
    eventMutation.mutate({
      action: "quick_answer_open",
      entity_type: "chunk",
      entity_id: source.chunk_id,
      metadata: {
        target_title: source.heading || source.title,
        document_title: source.title,
        unit_type: source.metadata.unit_type ?? source.section,
        source: "chat_source",
      },
    });
    sessionStorage.setItem("kb:selected-quick-source", JSON.stringify(source));
    void navigate({
      to: workspacePaths.lookup,
      search: { q: source.heading || source.title, chunk: source.chunk_id } as never,
    });
  }

  function openDocumentSource(source: RetrievalResult) {
    eventMutation.mutate({
      action: "full_sop_open",
      entity_type: "document_version",
      entity_id: source.version_id,
      metadata: {
        target_title: source.title,
        chunk_id: source.chunk_id,
        source: "chat_source",
      },
    });
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
        activeSessionId={activeSessionId}
        busy={busy}
        collectionOptions={collectionOptions}
        dynamicFilterOptions={dynamicFilterOptions}
        filters={scopeFilters}
        fallbackModel={chatModelRoutesQuery.data?.fallback_model}
        messages={messages}
        modelRoutes={chatModelRoutesQuery.data?.routes}
        modelRoute={modelRoute}
        onAsk={askGroundedChat}
        onArchiveSession={archiveSession}
        onCopy={copyText}
        onModelRouteChange={setModelRoute}
        onNewSession={startNewSession}
        onOpenDocument={openDocumentSource}
        onOpenQuickSource={openQuickSource}
        onSelectSession={selectSession}
        onUpdateFilter={updateScopeFilter}
        sessions={chatSessionsQuery.data ?? []}
        sessionsLoading={chatSessionsQuery.isLoading || chatSessionMessagesQuery.isLoading}
      />
    </Suspense>
  );
}

function storedMessageToThreadMessage(message: ChatStoredMessage): ChatThreadMessage {
  const response = isGroundedChatResponse(message.response_payload) ? message.response_payload : undefined;
  return {
    id: message.id,
    role: message.role,
    content: message.role === "assistant" && response?.answer ? response.answer : message.content,
    createdAt: message.created_at,
    response,
  };
}

function isGroundedChatResponse(value: ChatStoredMessage["response_payload"]): value is GroundedChatResponse {
  return Boolean(value && typeof value === "object" && "answer" in value && "citations" in value && "retrieval" in value);
}

function chatSessionIdFromPathname(pathname: string) {
  const prefix = `${workspacePaths.chat}/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  const [sessionId = ""] = pathname.slice(prefix.length).split("/");
  return sessionId ? decodeURIComponent(sessionId) : "";
}

function navigateToChatSession(navigate: ReturnType<typeof useNavigate>, sessionId: string) {
  void navigate({ to: `${workspacePaths.chat}/${encodeURIComponent(sessionId)}` as never });
}

function firstFilterValue(value: unknown) {
  if (Array.isArray(value)) {
    const first = value.find((item) => typeof item === "string" && item.trim());
    return typeof first === "string" ? first : undefined;
  }
  return typeof value === "string" && value.trim() ? value : undefined;
}

function isChatModelRoute(value: unknown): value is ChatModelRoute {
  return (
    value === "auto" ||
    value === "simple" ||
    value === "policy" ||
    value === "high_risk" ||
    value === "complex" ||
    value === "google/gemini-2.5-flash" ||
    value === "google/gemini-3-flash-preview" ||
    value === "anthropic/claude-3.5-haiku"
  );
}
