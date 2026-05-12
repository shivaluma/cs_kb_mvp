import {
  ArrowUp,
  BookOpen,
  Clipboard,
  Clock3,
  Loader2,
  Mic,
  Plus,
  Search,
  ShieldCheck,
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
import type { ChatModelRoute, ChatModelRouteConfig, ChatThreadMessage, RetrievalResult } from "@/types";

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
];

export function ChatWorkspace({
  busy,
  messages,
  modelRoutes,
  modelRoute,
  onAsk,
  onCopy,
  onModelRouteChange,
  onOpenDocument,
  onOpenQuickSource,
}: {
  busy: boolean;
  fallbackModel?: string;
  messages: ChatThreadMessage[];
  modelRoutes?: ChatModelRouteConfig[];
  modelRoute: ChatModelRoute;
  onAsk: (question: string) => void;
  onCopy: (text: string) => void;
  onModelRouteChange: (route: ChatModelRoute) => void;
  onOpenDocument: (source: RetrievalResult) => void;
  onOpenQuickSource: (source: RetrievalResult) => void;
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
          draft={draft}
          inputRef={inputRef}
          isExpanded={isExpanded}
          onDraftChange={handleDraftChange}
          onKeyDown={handleKeyDown}
          onModelRouteChange={onModelRouteChange}
          onSubmit={handleSubmit}
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
        Ask a case question. SOP Chat only answers from published SOP units with citations.
      </p>
    </section>
  );
}

function Composer({
  busy,
  draft,
  inputRef,
  isExpanded,
  modelRoute,
  onDraftChange,
  onKeyDown,
  onModelRouteChange,
  onSubmit,
  routeOptions,
}: {
  busy: boolean;
  draft: string;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  isExpanded: boolean;
  modelRoute: ChatModelRoute;
  onDraftChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onModelRouteChange: (route: ChatModelRoute) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  routeOptions: ChatModelRouteConfig[];
}) {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <form className="group/composer w-full" onSubmit={onSubmit}>
        <div
          className={cn(
            "grid w-full cursor-text overflow-clip border border-border bg-transparent bg-clip-padding p-2.5 shadow-lg transition-[border-radius] duration-200 ease-out dark:bg-muted/50",
            isExpanded
              ? "rounded-3xl [grid-template-areas:'header'_'primary'_'footer'] [grid-template-columns:1fr] [grid-template-rows:auto_1fr_auto]"
              : "rounded-3xl [grid-template-areas:'header_header_header'_'leading_primary_trailing'_'._footer_.'] [grid-template-columns:auto_1fr_auto] [grid-template-rows:auto_1fr_auto]",
          )}
        >
          <div className={cn("flex items-center", isExpanded && "hidden")} style={{ gridArea: "leading" }}>
            <Button
              aria-label="Published SOP scope"
              className="rounded-full text-muted-foreground outline-none ring-0 hover:bg-accent hover:text-foreground"
              onClick={() => inputRef.current?.focus()}
              size="icon"
              title="Answers are limited to published SOPs"
              type="button"
              variant="ghost"
            >
              <Plus className="size-6" />
            </Button>
          </div>

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
                placeholder="Ask anything"
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

              <Button
                aria-label="Voice input unavailable"
                className={cn("rounded-full text-muted-foreground hover:bg-accent hover:text-foreground", draft.trim() && "hidden")}
                disabled={busy}
                size="icon"
                title="Voice input is not connected yet"
                type="button"
                variant="ghost"
              >
                <Mic className="size-5" />
              </Button>

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
            {response.sources.length ? (
              <section className="min-w-0">
                <p className="text-xs font-semibold text-muted-foreground">Published sources used</p>
                <div className="mt-2 grid min-w-0 gap-2">
                  {response.sources.slice(0, 4).map((source) => (
                    <SourceCard
                      key={source.chunk_id}
                      onOpenDocument={onOpenDocument}
                      onOpenQuickSource={onOpenQuickSource}
                      source={source}
                    />
                  ))}
                </div>
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
  return (
    <div className="flex max-w-full flex-wrap items-center gap-1.5">
      <CompactBadge variant={response.citations.length ? "secondary" : "destructive"}>
        {response.citations.length ? `${response.citations.length} citations` : "no citation"}
      </CompactBadge>
      <CompactBadge>{Math.round(response.confidence * 100)}% confidence</CompactBadge>
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
  return (
    <div className="min-w-0 rounded-xl border bg-card px-3 py-2.5">
      <div className="flex max-w-full flex-wrap gap-1.5">
        <CompactBadge>{unitType}</CompactBadge>
        <CompactBadge>v{source.version_number}</CompactBadge>
        <CompactBadge>{source.rank_source.join("+") || "retrieval"}</CompactBadge>
      </div>
      <p className="mt-2 line-clamp-2 break-words text-sm font-semibold leading-5">{source.heading || source.title}</p>
      <p className="mt-1 line-clamp-2 break-words text-xs leading-5 text-muted-foreground">{source.content}</p>
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
