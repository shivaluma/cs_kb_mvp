import {
  IconArchive as Archive,
  IconArrowUp as ArrowUp,
  IconChevronDown as ChevronDown,
  IconClipboard as Clipboard,
  IconClock as Clock3,
  IconLoader2 as Loader2,
  IconMessagePlus as MessageSquarePlus,
  IconLayoutSidebarLeftCollapse as PanelLeftClose,
  IconLayoutSidebarLeftExpand as PanelLeftOpen,
  IconSearch as Search,
  IconShieldCheck as ShieldCheck,
  IconAdjustmentsHorizontal as SlidersHorizontal
} from "@tabler/icons-react";
import {
  useLayoutEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { Badge } from "@/components/ui/badge";
import { SourceContextCard } from "@/components/source-context-card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { isDebugUiEnabled } from "@/lib/ui-mode";
import { groupResultsByDisplaySource } from "@/lib/source-display";
import type {
  ChatModelRoute,
  ChatModelRouteConfig,
  ChatSessionSummary,
  ChatThreadMessage,
  FilterOption,
  FilterState,
  RetrievalResult,
  SourceGroup,
} from "@/types";

const FALLBACK_CHAT_MODEL_ROUTES: ChatModelRouteConfig[] = [
  {
    route: "simple",
    label: "Gemini Flash Lite",
    model: "google/gemini-2.5-flash-lite",
    description: "Simple factual SOP Q&A, nhanh và rẻ cho câu hỏi tra cứu ngắn.",
  },
  {
    route: "policy",
    label: "Kimi K2.5 Policy",
    model: "moonshotai/kimi-k2.5",
    description: "Policy, decision, exception Q&A cần reasoning tốt hơn.",
  },
  {
    route: "high_risk",
    label: "Kimi K2.5 High Risk",
    model: "moonshotai/kimi-k2.5",
    description: "Refund, payment, account, privacy, ZT với grounding/citation chặt hơn.",
  },
  {
    route: "complex",
    label: "Kimi K2.6 Complex",
    model: "moonshotai/kimi-k2.6",
    description: "Multi-SOP synthesis hoặc macro polished từ nhiều nguồn published.",
  },
  {
    route: "google/gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    model: "google/gemini-2.5-flash",
    description: "Manual model override cân bằng tốc độ và chất lượng cho SOP chat.",
  },
  {
    route: "google/gemini-3-flash-preview",
    label: "Gemini 3 Flash Preview",
    model: "google/gemini-3-flash-preview",
    description: "Manual model override cho câu hỏi nhiều nguồn hoặc cần reasoning mới hơn.",
  },
  {
    route: "anthropic/claude-3.5-haiku",
    label: "Claude 3.5 Haiku",
    model: "anthropic/claude-3.5-haiku",
    description: "Manual model override cho câu trả lời ngắn, nhanh và grounded.",
  },
];
const COMPOSER_MAX_HEIGHT = 176;

export function ChatWorkspace({
  activeSessionId,
  busy,
  collectionOptions,
  dynamicFilterOptions,
  filters,
  messages,
  modelRoutes,
  modelRoute,
  onAsk,
  onArchiveSession,
  onCopy,
  onModelRouteChange,
  onNewSession,
  onOpenDocument,
  onSelectSession,
  onUpdateFilter,
  sessions,
  sessionsLoading,
}: {
  activeSessionId: string;
  busy: boolean;
  collectionOptions: FilterOption[];
  dynamicFilterOptions: {
    audience: FilterOption[];
    vertical: FilterOption[];
    taskType: FilterOption[];
  };
  fallbackModel?: string;
  filters: FilterState;
  messages: ChatThreadMessage[];
  modelRoutes?: ChatModelRouteConfig[];
  modelRoute: ChatModelRoute;
  onAsk: (question: string) => void;
  onArchiveSession: (sessionId: string) => void;
  onCopy: (text: string) => void;
  onModelRouteChange: (route: ChatModelRoute) => void;
  onNewSession: () => void;
  onOpenDocument: (source: RetrievalResult) => void;
  onSelectSession: (sessionId: string) => void;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
  sessions: ChatSessionSummary[];
  sessionsLoading: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [isExpanded, setIsExpanded] = useState(false);
  const [sessionPanelOpen, setSessionPanelOpen] = useState(true);
  const [sessionSearch, setSessionSearch] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const routeOptions = modelRoutes?.length ? modelRoutes : FALLBACK_CHAT_MODEL_ROUTES;
  const hasMessages = messages.length > 0;
  const filteredSessions = sessions.filter((session) =>
    session.title.toLowerCase().includes(sessionSearch.trim().toLowerCase()),
  );
  const debugEnabled = isDebugUiEnabled();

  function resetComposer() {
    setDraft("");
    setIsExpanded(false);
    resizeComposerTextarea(inputRef.current);
  }

  function submit(question = draft) {
    const trimmed = question.trim();
    if (!trimmed || busy) {
      return;
    }
    onAsk(trimmed);
    resetComposer();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleDraftChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const value = event.target.value;
    const nextHeight = resizeComposerTextarea(event.currentTarget);
    setDraft(value);
    setIsExpanded(value.length > 120 || value.includes("\n") || nextHeight > 36);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background md:flex-row">
      {sessionPanelOpen ? (
        <SessionPanel
          activeSessionId={activeSessionId}
          busy={busy}
          onArchiveSession={onArchiveSession}
          onNewSession={onNewSession}
          onSearchChange={setSessionSearch}
          onSelectSession={onSelectSession}
          searchValue={sessionSearch}
          sessions={filteredSessions}
          sessionsLoading={sessionsLoading}
        />
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center justify-between border-b px-3 md:px-4">
          <Button
            aria-label={sessionPanelOpen ? "Hide chat sessions" : "Show chat sessions"}
            className="h-8 rounded-full px-2 text-xs text-muted-foreground"
            onClick={() => setSessionPanelOpen((open) => !open)}
            size="sm"
            type="button"
            variant="ghost"
          >
            {sessionPanelOpen ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
            <span className="hidden sm:inline">Sessions</span>
          </Button>
          <div className="truncate text-xs font-medium text-muted-foreground">SOP Chat</div>
        </div>

        <div className={cn("min-h-0 flex-1 overflow-y-auto", hasMessages ? "px-1 py-2" : "grid place-items-center px-4 py-10")}>
          {hasMessages ? (
            <div className="mx-auto grid w-full max-w-3xl gap-6 pb-6">
              {messages.map((message) => (
                <ChatBubble
                  key={message.id}
                  message={message}
                  showDebug={debugEnabled}
                  onCopy={onCopy}
                  onOpenDocument={onOpenDocument}
                />
              ))}
            </div>
          ) : (
            <div className="w-full pb-20">
              <EmptyChatState />
            </div>
          )}
        </div>

        <div className="shrink-0 bg-background px-2 pb-2 pt-3 md:px-4 md:pb-3">
          <Composer
            busy={busy}
            collectionOptions={collectionOptions}
            draft={draft}
            dynamicFilterOptions={dynamicFilterOptions}
            filters={filters}
            inputRef={inputRef}
            isExpanded={isExpanded}
            onDraftChange={handleDraftChange}
            onKeyDown={handleKeyDown}
            onModelRouteChange={onModelRouteChange}
            onSubmit={handleSubmit}
            onUpdateFilter={onUpdateFilter}
            routeOptions={routeOptions}
            modelRoute={modelRoute}
            showDebug={debugEnabled}
          />
        </div>
      </div>
    </div>
  );
}

function SessionPanel({
  activeSessionId,
  busy,
  onArchiveSession,
  onNewSession,
  onSearchChange,
  onSelectSession,
  searchValue,
  sessions,
  sessionsLoading,
}: {
  activeSessionId: string;
  busy: boolean;
  onArchiveSession: (sessionId: string) => void;
  onNewSession: () => void;
  onSearchChange: (value: string) => void;
  onSelectSession: (sessionId: string) => void;
  searchValue: string;
  sessions: ChatSessionSummary[];
  sessionsLoading: boolean;
}) {
  return (
    <aside className="flex max-h-64 min-h-0 shrink-0 flex-col border-b bg-muted/15 md:h-full md:max-h-none md:w-72 md:border-b-0 md:border-r">
      <div className="shrink-0 px-3 py-3">
        <Button className="h-9 w-full rounded-full" disabled={busy} onClick={onNewSession} type="button">
          <MessageSquarePlus data-icon="inline-start" className="size-4" />
          New chat
        </Button>
        <label className="mt-2 flex h-9 items-center gap-2 rounded-full border bg-background px-3 text-sm">
          <Search className="size-4 text-muted-foreground" />
          <input
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search sessions"
            value={searchValue}
          />
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {sessionsLoading && !sessions.length ? (
          <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            Loading sessions
          </div>
        ) : null}
        {!sessionsLoading && !sessions.length ? (
          <p className="px-2 py-3 text-xs leading-5 text-muted-foreground">
            No chat sessions yet. Start a chat to keep the trail for later.
          </p>
        ) : null}
        <div className="grid gap-1.5">
          {sessions.map((session) => (
            <SessionListItem
              active={session.id === activeSessionId}
              busy={busy}
              key={session.id}
              onArchive={() => onArchiveSession(session.id)}
              onSelect={() => onSelectSession(session.id)}
              session={session}
            />
          ))}
        </div>
      </div>
    </aside>
  );
}

function SessionListItem({
  active,
  busy,
  onArchive,
  onSelect,
  session,
}: {
  active: boolean;
  busy: boolean;
  onArchive: () => void;
  onSelect: () => void;
  session: ChatSessionSummary;
}) {
  return (
    <div
      className={cn(
        "group/session flex min-w-0 items-start gap-2 rounded-xl px-2 py-2 text-left transition-colors",
        active ? "bg-background shadow-sm ring-1 ring-border" : "hover:bg-background/60",
      )}
    >
      <button className="min-w-0 flex-1 text-left" onClick={onSelect} type="button">
        <p className="truncate text-sm font-medium text-foreground">{session.title || "New chat"}</p>
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {session.message_count} messages · {formatSessionTime(session.last_message_at ?? session.updated_at)}
        </p>
      </button>
      <Button
        aria-label="Archive chat session"
        className={cn("h-7 w-7 rounded-full opacity-70 md:opacity-0 md:group-hover/session:opacity-100", active && "opacity-100")}
        disabled={busy}
        onClick={onArchive}
        size="icon"
        title="Archive"
        type="button"
        variant="ghost"
      >
        <Archive className="size-3.5" />
      </Button>
    </div>
  );
}

function EmptyChatState() {
  return (
    <section className="w-full">
      <h2 className="mx-auto max-w-2xl text-center text-2xl font-semibold leading-8 text-foreground">
        Where should we begin?
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-center text-sm leading-6 text-muted-foreground">
        Ask a case question. SOP Chat searches published SOPs, issue routers, tools, and approved relations, then answers only from grounded policy evidence.
      </p>
    </section>
  );
}

function Composer({
  busy,
  collectionOptions,
  draft,
  dynamicFilterOptions,
  filters,
  inputRef,
  isExpanded,
  modelRoute,
  onDraftChange,
  onKeyDown,
  onModelRouteChange,
  onSubmit,
  onUpdateFilter,
  routeOptions,
  showDebug,
}: {
  busy: boolean;
  collectionOptions: FilterOption[];
  draft: string;
  dynamicFilterOptions: {
    audience: FilterOption[];
    vertical: FilterOption[];
    taskType: FilterOption[];
  };
  filters: FilterState;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  isExpanded: boolean;
  modelRoute: ChatModelRoute;
  onDraftChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onModelRouteChange: (route: ChatModelRoute) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
  routeOptions: ChatModelRouteConfig[];
  showDebug: boolean;
}) {
  const [scopeOpen, setScopeOpen] = useState(false);
  const scopedValues = [filters.collection, filters.audience, filters.vertical, filters.taskType];
  const activeScopeCount = scopedValues.filter((value) => value && value !== "all").length;
  const selectedRouteLabel = routeOptions.find((route) => route.route === modelRoute)?.label ?? modelRoute;
  const scopeOptions = {
    collection: [{ label: "All collections", value: "all" }, ...collectionOptions],
    audience: dynamicFilterOptions.audience.length
      ? dynamicFilterOptions.audience
      : [{ label: "All audiences", value: "all" }],
    vertical: dynamicFilterOptions.vertical.length
      ? dynamicFilterOptions.vertical
      : [{ label: "All verticals", value: "all" }],
    taskType: dynamicFilterOptions.taskType.length
      ? dynamicFilterOptions.taskType
      : [{ label: "All tasks", value: "all" }],
  };

  useLayoutEffect(() => {
    resizeComposerTextarea(inputRef.current);
  });

  return (
    <div className="mx-auto w-full max-w-3xl space-y-2">
      <div className="flex justify-end">
        <Button
          aria-expanded={scopeOpen}
          className="h-8 rounded-full px-2 text-xs text-muted-foreground"
          onClick={() => setScopeOpen((open) => !open)}
          size="sm"
          type="button"
          variant="ghost"
        >
          <SlidersHorizontal data-icon="inline-start" className="size-3.5" />
          Scope
          {activeScopeCount ? <CompactBadge variant="secondary">{activeScopeCount}</CompactBadge> : null}
        </Button>
      </div>

      {scopeOpen ? (
        <div className="grid gap-2 rounded-2xl border bg-muted/20 p-2 sm:grid-cols-2 lg:grid-cols-4">
          <ScopeSelect
            label="Collection"
            onChange={(value) => onUpdateFilter("collection", value)}
            options={scopeOptions.collection}
            value={filters.collection}
          />
          <ScopeSelect
            label="Audience"
            onChange={(value) => onUpdateFilter("audience", value)}
            options={scopeOptions.audience}
            value={filters.audience}
          />
          <ScopeSelect
            label="Vertical"
            onChange={(value) => onUpdateFilter("vertical", value)}
            options={scopeOptions.vertical}
            value={filters.vertical}
          />
          <ScopeSelect
            label="Task"
            onChange={(value) => onUpdateFilter("taskType", value)}
            options={scopeOptions.taskType}
            value={filters.taskType}
          />
        </div>
      ) : null}

      <form className="group/composer w-full" onSubmit={onSubmit}>
        <div
          className={cn(
            "grid w-full cursor-text overflow-clip border border-border bg-transparent bg-clip-padding p-2.5 shadow-lg transition-[border-radius] duration-200 ease-out dark:bg-muted/50",
            isExpanded
              ? "rounded-3xl [grid-template-areas:'primary'_'footer'] [grid-template-columns:1fr] [grid-template-rows:1fr_auto]"
              : "rounded-3xl [grid-template-areas:'primary_trailing'] [grid-template-columns:1fr_auto] [grid-template-rows:auto]",
          )}
        >
          <div
            className={cn("flex min-h-14 items-center overflow-x-hidden px-1.5", {
              "mb-0 px-2 py-1": isExpanded,
              "-my-2.5": !isExpanded,
            })}
            style={{ gridArea: "primary" }}
          >
            <div className="max-h-52 flex-1 overflow-hidden">
              <textarea
                ref={inputRef}
                className="block w-full min-h-6 resize-none overflow-hidden rounded-none border-0 bg-transparent p-0 text-base leading-6 outline-none placeholder:text-muted-foreground focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={busy}
                onChange={onDraftChange}
                onKeyDown={onKeyDown}
                placeholder="Ask a published SOP question"
                rows={1}
                value={draft}
              />
            </div>
          </div>

          <div
            className="flex items-center gap-2"
            style={{ gridArea: isExpanded ? "footer" : "trailing" }}
          >
            <div className="ms-auto flex items-center gap-1.5">
              {showDebug ? (
                <div className="hidden min-w-0 sm:block">
                  <Select
                    disabled={busy}
                    onValueChange={(value) => onModelRouteChange(value as ChatModelRoute)}
                    value={modelRoute}
                  >
                    <SelectTrigger
                      aria-label="Select model route"
                      className="h-9 w-48 max-w-[42vw] rounded-full border-0 bg-transparent px-2 text-base text-muted-foreground shadow-none hover:bg-accent hover:text-foreground focus-visible:ring-0"
                      size="sm"
                      title={selectedRouteLabel}
                    >
                      <span className="min-w-0 flex-1 truncate text-left">{selectedRouteLabel}</span>
                    </SelectTrigger>
                    <SelectContent align="end" className="w-80" position="popper" side="top" sideOffset={8}>
                      {groupRouteOptions(routeOptions).map((group) => (
                        <div className="px-1 py-1" key={group.label}>
                          <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                            {group.label}
                          </div>
                          {group.routes.map((route) => (
                            <SelectItem key={route.route} textValue={route.label} value={route.route}>
                              <div className="flex flex-col">
                                <span className="text-sm font-medium">{route.label}</span>
                                {route.description ? (
                                  <span className="line-clamp-1 text-[11px] text-muted-foreground">
                                    {route.description}
                                  </span>
                                ) : null}
                              </div>
                            </SelectItem>
                          ))}
                        </div>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}

              {draft.trim() ? (
                <Button
                  aria-label="Send message"
                  className="rounded-full"
                  disabled={busy}
                  size="icon"
                  title="Send"
                  type="submit"
                >
                  {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-5" />}
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}

function ScopeSelect({
  label,
  onChange,
  options,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  options: FilterOption[];
  value: string;
}) {
  return (
    <label className="grid min-w-0 gap-1">
      <span className="px-1 text-[11px] font-semibold text-muted-foreground">{label}</span>
      <Select onValueChange={onChange} value={value}>
        <SelectTrigger className="h-9 min-w-0 rounded-full border-0 bg-background/80 px-3 text-xs shadow-none">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={`${label}-${option.value}`} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

function ChatBubble({
  message,
  onCopy,
  onOpenDocument,
  showDebug,
}: {
  message: ChatThreadMessage;
  onCopy: (text: string) => void;
  onOpenDocument: (source: RetrievalResult) => void;
  showDebug: boolean;
}) {
  const isUser = message.role === "user";
  const response = message.response;
  const groupedSources = response ? sourceGroupsForResponse(response) : [];
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const sourceCount = groupedSources.reduce((total, group) => total + group.sources.length, 0);
  return (
    <article className={cn("min-w-0", isUser ? "ml-auto max-w-[78%]" : "mr-auto w-full max-w-3xl")}>
      <div
        className={cn(
          "min-w-0 break-words text-sm leading-6",
          isUser
            ? "rounded-[1.65rem] bg-primary px-4 py-2.5 text-primary-foreground"
            : "px-1 text-foreground",
        )}
      >
        {!isUser ? (
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <ShieldCheck className="size-3.5" />
            Grounded answer
            {message.pending ? <Loader2 className="size-3.5 animate-spin" /> : null}
          </div>
        ) : null}

        <p className="whitespace-pre-wrap break-words">{message.content}</p>

        {response ? (
          <div className="mt-3 grid min-w-0 gap-3">
            <ResponseMeta response={response} onCopy={onCopy} showDebug={showDebug} />
            {response.steps.length ? <ActionSteps steps={response.steps} /> : null}
            {response.warnings.length ? <Warnings showDebug={showDebug} warnings={response.warnings} /> : null}
            {showDebug && response.model_reason ? (
              <p className="max-w-full rounded-xl bg-muted/35 px-3 py-2 text-xs leading-5 text-muted-foreground">
                Model routing: {response.model_reason}
              </p>
            ) : null}
            {showDebug && hasRetrievalTrace(response) ? <RetrievalTrace trace={response.retrieval_trace ?? {}} /> : null}
            {groupedSources.length ? (
              <section className="min-w-0 rounded-xl border bg-muted/10 px-3 py-2.5">
                <button
                  aria-expanded={sourcesOpen}
                  className="flex w-full min-w-0 items-center gap-2 text-left"
                  onClick={() => setSourcesOpen((current) => !current)}
                  type="button"
                >
                  <span className="shrink-0 text-xs font-semibold text-muted-foreground">Sources used</span>
                  <CompactBadge variant="secondary">{sourceCount}</CompactBadge>
                  <span className="flex min-w-0 flex-1 flex-wrap gap-1.5">
                    {groupedSources.map((group) => (
                      <CompactBadge className="max-w-[11rem]" key={group.role}>
                        {group.label}: {group.sources.length}
                      </CompactBadge>
                    ))}
                  </span>
                  <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", sourcesOpen && "rotate-180")} />
                </button>
                {sourcesOpen ? (
                  <div className="mt-3 grid min-w-0 gap-3">
                    {groupedSources.map((group) => (
                      <div className="min-w-0" key={group.role}>
                        <div className="mb-1.5 flex items-center gap-2">
                          <CompactBadge variant="secondary">{group.label}</CompactBadge>
                          <span className="text-[11px] text-muted-foreground">{group.sources.length}</span>
                        </div>
                        <div className="grid min-w-0 gap-2">
                          {groupResultsByDisplaySource(group.sources).map((sourceGroup) => (
                            <SourceContextCard
                              compact
                              group={sourceGroup}
                              key={`${group.role}-${sourceGroup.id}`}
                              onCopyExcerpt={(text) => onCopy(text)}
                              onOpenSource={() => onOpenDocument(sourceGroup.results[0])}
                              showDebugScore={showDebug}
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function ResponseMeta({
  onCopy,
  response,
  showDebug,
}: {
  onCopy: (text: string) => void;
  response: NonNullable<ChatThreadMessage["response"]>;
  showDebug: boolean;
}) {
  const finalSourceCount = numericTraceValue(response.retrieval_trace, "final_count");
  return (
    <div className="flex max-w-full flex-wrap items-center gap-1.5">
      <CompactBadge variant={response.citations.length ? "secondary" : "destructive"}>
        {response.citations.length ? `${response.citations.length} citations` : "no citation"}
      </CompactBadge>
      <CompactBadge>{Math.round(response.confidence * 100)}% evidence</CompactBadge>
      {finalSourceCount ? <CompactBadge>{finalSourceCount} sources checked</CompactBadge> : null}
      {showDebug && response.model_route ? <CompactBadge>{response.model_route}</CompactBadge> : null}
      {showDebug && response.model_used ? <CompactBadge className="max-w-[13rem]">{response.model_used}</CompactBadge> : null}
      {showDebug ? (
        <CompactBadge>
          <Clock3 data-icon="inline-start" className="size-3" />
          {response.latency_ms}ms
        </CompactBadge>
      ) : null}
      <Button className="ml-auto h-7 rounded-full px-2" onClick={() => onCopy(response.answer)} size="sm" type="button" variant="outline">
        <Clipboard data-icon="inline-start" className="size-3.5" />
        Copy
      </Button>
    </div>
  );
}

function RetrievalTrace({ trace }: { trace: Record<string, unknown> }) {
  const stages = [
    { label: "Direct candidates", value: numericTraceValue(trace, "direct_count") },
    { label: "Index candidates", value: numericTraceValue(trace, "index_count") },
    { label: "Related fetched", value: numericTraceValue(trace, "relation_count") },
    { label: "Parent fetched", value: numericTraceValue(trace, "parent_count") },
    { label: "Final context", value: numericTraceValue(trace, "final_count") },
    { label: "Merged duplicates", value: numericTraceValue(trace, "semantic_deduped_count") },
  ].filter((stage) => stage.value > 0);

  if (!stages.length) {
    return null;
  }

  return (
    <section className="min-w-0 rounded-xl border bg-muted/15 px-3 py-2">
      <p className="text-xs font-semibold text-muted-foreground">Retrieval debug</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {stages.map((stage) => (
          <CompactBadge key={stage.label}>
            {stage.label}: {stage.value}
          </CompactBadge>
        ))}
      </div>
    </section>
  );
}

function ActionSteps({ steps }: { steps: string[] }) {
  return (
    <section className="min-w-0 rounded-xl border bg-muted/15 px-3 py-2.5">
      <p className="text-xs font-semibold text-muted-foreground">Action steps</p>
      <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm leading-6">
        {steps.map((step, index) => (
          <li className="break-words" key={`${step}-${index}`}>{step}</li>
        ))}
      </ol>
    </section>
  );
}

function Warnings({ showDebug, warnings }: { showDebug: boolean; warnings: string[] }) {
  const visibleWarnings = warnings
    .map((warning) => readableWarningLabel(warning, showDebug))
    .filter(Boolean)
    .filter((warning, index, list) => list.indexOf(warning) === index)
    .slice(0, 6);
  if (!visibleWarnings.length) {
    return null;
  }
  return (
    <section className="min-w-0 rounded-xl border border-destructive/25 bg-destructive/5 px-3 py-2.5">
      <p className="text-xs font-semibold text-destructive">Review warning</p>
      <div className="mt-2 flex max-w-full flex-wrap gap-1.5">
        {visibleWarnings.map((warning, index) => (
          <CompactBadge className="max-w-full text-destructive" key={`${warning}-${index}`}>
            {warning}
          </CompactBadge>
        ))}
      </div>
    </section>
  );
}

function readableWarningLabel(warning: string, showDebug: boolean) {
  const normalized = warning.toLowerCase().replace(/_/g, " ");
  if (normalized.includes("conflict") || normalized.includes("requires review")) {
    return "SOP guidance may conflict. Review with owner/QA.";
  }
  if (normalized.includes("no reliable source") || normalized.includes("insufficient")) {
    return "Not enough published SOP evidence.";
  }
  if (normalized.includes("grounded published sop units only")) {
    return "Answer is limited to published SOP evidence.";
  }
  if (normalized.includes("internal")) {
    return "Internal-only source needs care before customer wording.";
  }
  if (!showDebug && isDebugWarning(normalized)) {
    return "";
  }
  return warning.replace(/_/g, " ");
}

function isDebugWarning(normalizedWarning: string) {
  return [
    "raw_draft",
    "raw draft",
    "archived content excluded",
    "chat_kb_index",
    "chat kb index",
    "meili",
    "postgres",
    "qdrant",
    "vector",
    "rerank",
    "retrieval",
    "relation_expansion",
    "relation expansion",
    "openrouter",
    "model:",
    "model confidence",
    "cache",
    "timeout",
  ].some((token) => normalizedWarning.includes(token));
}

function sourceGroupsForResponse(response: NonNullable<ChatThreadMessage["response"]>): SourceGroup[] {
  const groups = (response.source_groups ?? []).filter((group) => group.sources.length);
  if (groups.length) {
    return groups;
  }
  return response.sources.length
    ? [{ role: "sources", label: "Published sources", sources: response.sources }]
    : [];
}

function hasRetrievalTrace(response: NonNullable<ChatThreadMessage["response"]>) {
  return Boolean(response.retrieval_trace && Object.keys(response.retrieval_trace).length);
}

function numericTraceValue(trace: Record<string, unknown> | undefined, key: string) {
  const value = trace?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function groupRouteOptions(routes: ChatModelRouteConfig[]) {
  const presets = routes.filter((route) => ["simple", "policy", "high_risk", "complex"].includes(route.route));
  const manuals = routes.filter((route) => !["simple", "policy", "high_risk", "complex"].includes(route.route));
  const groups: { label: string; routes: ChatModelRouteConfig[] }[] = [];
  if (presets.length) {
    groups.push({ label: "Routed by intent", routes: presets });
  }
  if (manuals.length) {
    groups.push({ label: "Manual override", routes: manuals });
  }
  return groups;
}

function formatSessionTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "no activity";
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function resizeComposerTextarea(textarea: HTMLTextAreaElement | null) {
  if (!textarea) {
    return 0;
  }
  textarea.style.height = "0px";
  const nextHeight = Math.min(textarea.scrollHeight, COMPOSER_MAX_HEIGHT);
  textarea.style.height = `${Math.max(nextHeight, 24)}px`;
  textarea.style.overflowY = textarea.scrollHeight > COMPOSER_MAX_HEIGHT ? "auto" : "hidden";
  return nextHeight;
}

function CompactBadge({
  children,
  className,
  variant = "outline",
}: {
  children: ReactNode;
  className?: string;
  variant?: "default" | "secondary" | "destructive" | "outline";
}) {
  return (
    <Badge className={cn("min-w-0 max-w-full truncate rounded-full px-2 text-[11px]", className)} variant={variant}>
      {children}
    </Badge>
  );
}
