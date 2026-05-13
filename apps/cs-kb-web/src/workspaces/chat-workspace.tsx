import {
  ArrowUp,
  BookOpen,
  ChevronDown,
  Clipboard,
  Clock3,
  Loader2,
  Search,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import {
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type {
  ChatModelRoute,
  ChatModelRouteConfig,
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

export function ChatWorkspace({
  busy,
  collectionOptions,
  dynamicFilterOptions,
  filters,
  messages,
  modelRoutes,
  modelRoute,
  onAsk,
  onCopy,
  onModelRouteChange,
  onOpenDocument,
  onOpenQuickSource,
  onUpdateFilter,
}: {
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
  onCopy: (text: string) => void;
  onModelRouteChange: (route: ChatModelRoute) => void;
  onOpenDocument: (source: RetrievalResult) => void;
  onOpenQuickSource: (source: RetrievalResult) => void;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const [isExpanded, setIsExpanded] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const routeOptions = modelRoutes?.length ? modelRoutes : FALLBACK_CHAT_MODEL_ROUTES;
  const hasMessages = messages.length > 0;

  function resetComposer() {
    setDraft("");
    setIsExpanded(false);
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }
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
    setDraft(value);
    setIsExpanded(value.length > 120 || value.includes("\n"));

    const target = event.currentTarget;
    target.style.height = "auto";
    target.style.height = `${Math.min(target.scrollHeight, 176)}px`;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <div className={cn("min-h-0 flex-1 overflow-y-auto", hasMessages ? "px-1 py-2" : "grid place-items-center px-4 py-10")}>
        {hasMessages ? (
          <div className="mx-auto grid w-full max-w-3xl gap-6 pb-6">
            {messages.map((message) => (
              <ChatBubble
                key={message.id}
                message={message}
                onCopy={onCopy}
                onOpenDocument={onOpenDocument}
                onOpenQuickSource={onOpenQuickSource}
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
        />
      </div>
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
}) {
  const [scopeOpen, setScopeOpen] = useState(false);
  const scopedValues = [filters.collection, filters.audience, filters.vertical, filters.taskType];
  const activeScopeCount = scopedValues.filter((value) => value && value !== "all").length;
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
            <div className="max-h-52 flex-1 overflow-auto">
              <textarea
                ref={inputRef}
                className="block w-full min-h-0 resize-none rounded-none border-0 bg-transparent p-0 text-base leading-6 outline-none placeholder:text-muted-foreground focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-60"
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
              <div className="hidden min-w-0 sm:block">
                <Select
                  disabled={busy}
                  onValueChange={(value) => onModelRouteChange(value as ChatModelRoute)}
                  value={modelRoute}
                >
                  <SelectTrigger
                    aria-label="Select model route"
                    className="h-9 max-w-[12rem] rounded-full border-0 bg-transparent px-2 text-base text-muted-foreground shadow-none hover:bg-accent hover:text-foreground focus-visible:ring-0"
                    size="sm"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align="end" className="w-80">
                    {routeOptions.map((route) => (
                      <SelectItem key={route.route} value={route.route}>
                        {route.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

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
  onOpenQuickSource,
}: {
  message: ChatThreadMessage;
  onCopy: (text: string) => void;
  onOpenDocument: (source: RetrievalResult) => void;
  onOpenQuickSource: (source: RetrievalResult) => void;
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
            <ResponseMeta response={response} onCopy={onCopy} />
            {response.steps.length ? <ActionSteps steps={response.steps} /> : null}
            {response.warnings.length ? <Warnings warnings={response.warnings} /> : null}
            {response.model_reason ? (
              <p className="max-w-full rounded-xl bg-muted/35 px-3 py-2 text-xs leading-5 text-muted-foreground">
                Model routing: {response.model_reason}
              </p>
            ) : null}
            {hasRetrievalTrace(response) ? <RetrievalTrace trace={response.retrieval_trace ?? {}} /> : null}
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
                          {group.sources.map((source) => (
                            <SourceCard
                              key={`${group.role}-${source.chunk_id}`}
                              onOpenDocument={onOpenDocument}
                              onOpenQuickSource={onOpenQuickSource}
                              source={source}
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
}: {
  onCopy: (text: string) => void;
  response: NonNullable<ChatThreadMessage["response"]>;
}) {
  const finalSourceCount = numericTraceValue(response.retrieval_trace, "final_count");
  return (
    <div className="flex max-w-full flex-wrap items-center gap-1.5">
      <CompactBadge variant={response.citations.length ? "secondary" : "destructive"}>
        {response.citations.length ? `${response.citations.length} citations` : "no citation"}
      </CompactBadge>
      <CompactBadge>{Math.round(response.confidence * 100)}% confidence</CompactBadge>
      {finalSourceCount ? <CompactBadge>{finalSourceCount} sources</CompactBadge> : null}
      {response.model_route ? <CompactBadge>{response.model_route}</CompactBadge> : null}
      {response.model_used ? <CompactBadge className="max-w-[13rem]">{response.model_used}</CompactBadge> : null}
      <CompactBadge>
        <Clock3 data-icon="inline-start" className="size-3" />
        {response.latency_ms}ms
      </CompactBadge>
      <Button className="ml-auto h-7 rounded-full px-2" onClick={() => onCopy(response.answer)} size="sm" type="button" variant="outline">
        <Clipboard data-icon="inline-start" className="size-3.5" />
        Copy
      </Button>
    </div>
  );
}

function RetrievalTrace({ trace }: { trace: Record<string, unknown> }) {
  const stages = [
    { label: "Direct SOP", value: numericTraceValue(trace, "direct_count") },
    { label: "Index", value: numericTraceValue(trace, "index_count") },
    { label: "Related", value: numericTraceValue(trace, "relation_count") },
    { label: "Parent", value: numericTraceValue(trace, "parent_count") },
  ].filter((stage) => stage.value > 0);

  if (!stages.length) {
    return null;
  }

  return (
    <section className="min-w-0 rounded-xl border bg-muted/15 px-3 py-2">
      <p className="text-xs font-semibold text-muted-foreground">Retrieval trace</p>
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

function Warnings({ warnings }: { warnings: string[] }) {
  return (
    <section className="min-w-0 rounded-xl border border-destructive/25 bg-destructive/5 px-3 py-2.5">
      <p className="text-xs font-semibold text-destructive">Warnings</p>
      <div className="mt-2 flex max-w-full flex-wrap gap-1.5">
        {warnings.slice(0, 8).map((warning, index) => (
          <CompactBadge className="max-w-full text-destructive" key={`${warning}-${index}`}>
            {warning}
          </CompactBadge>
        ))}
      </div>
    </section>
  );
}

function SourceCard({
  onOpenDocument,
  onOpenQuickSource,
  source,
}: {
  onOpenDocument: (source: RetrievalResult) => void;
  onOpenQuickSource: (source: RetrievalResult) => void;
  source: RetrievalResult;
}) {
  const unitType = String(source.metadata.unit_type ?? source.section);
  const role = metadataText(source.metadata.chat_source_role);
  const reason = metadataText(source.metadata.chat_retrieval_reason);
  const relationType = metadataText(source.metadata.relation_type);
  const collectionSlug = metadataText(source.metadata.collection_slug ?? source.metadata.collection);
  const taskTypes = metadataValues(source.metadata.task_type ?? source.metadata.task_types);
  return (
    <div className="min-w-0 rounded-xl border bg-card px-3 py-2.5">
      <div className="flex max-w-full flex-wrap gap-1.5">
        {role ? <CompactBadge variant="secondary">{sourceRoleLabel(role)}</CompactBadge> : null}
        <CompactBadge>{unitType}</CompactBadge>
        <CompactBadge>v{source.version_number}</CompactBadge>
        {relationType ? <CompactBadge>{relationType}</CompactBadge> : null}
        {collectionSlug ? <CompactBadge className="max-w-[12rem]">{collectionSlug}</CompactBadge> : null}
        {taskTypes.slice(0, 2).map((taskType) => (
          <CompactBadge className="max-w-[10rem]" key={taskType}>{taskType}</CompactBadge>
        ))}
      </div>
      <p className="mt-2 line-clamp-2 break-words text-sm font-semibold leading-5">{source.heading || source.title}</p>
      <p className="mt-1 line-clamp-2 break-words text-xs leading-5 text-muted-foreground">{source.content}</p>
      {reason ? <p className="mt-1 truncate text-[11px] text-muted-foreground">{reason}</p> : null}
      <p className="mt-2 truncate text-[11px] text-muted-foreground">{source.source_filename}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button className="h-7 rounded-full px-2" onClick={() => onOpenQuickSource(source)} size="sm" type="button" variant="outline">
          <Search data-icon="inline-start" className="size-3.5" />
          Quick rule
        </Button>
        <Button className="h-7 rounded-full px-2" onClick={() => onOpenDocument(source)} size="sm" type="button" variant="ghost">
          <BookOpen data-icon="inline-start" className="size-3.5" />
          Source
        </Button>
      </div>
    </div>
  );
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

function metadataText(value: unknown) {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "";
}

function metadataValues(value: unknown) {
  if (Array.isArray(value)) {
    return value.map(metadataText).filter(Boolean);
  }
  const text = metadataText(value);
  return text ? [text] : [];
}

function sourceRoleLabel(role: string) {
  const labels: Record<string, string> = {
    direct_sop: "Direct SOP",
    issue_router: "Issue router",
    related_sop: "Related SOP",
    action_template: "Action template",
    tool_link: "Tool",
    parent_sop: "Parent SOP",
  };
  return labels[role] ?? role;
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
