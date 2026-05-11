import {
  AlertTriangle,
  ArrowUp,
  BookOpen,
  CheckCircle2,
  Clipboard,
  ClipboardList,
  Clock3,
  FileText,
  Gauge,
  Loader2,
  MessageSquareText,
  Route,
  Search,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";

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

const PROMPT_SUGGESTIONS: Array<{
  icon: LucideIcon;
  label: string;
  prompt: string;
}> = [
  {
    icon: ClipboardList,
    label: "Check next step",
    prompt: "case này cần kiểm tra thông tin nào trước?",
  },
  {
    icon: Route,
    label: "Escalation rule",
    prompt: "khi nào cần chuyển xử lý cho team liên quan?",
  },
  {
    icon: AlertTriangle,
    label: "Risk scan",
    prompt: "có cảnh báo bảo mật hoặc compliance nào không?",
  },
  {
    icon: FileText,
    label: "Draft macro",
    prompt: "macro phản hồi phù hợp là gì?",
  },
];

export function ChatWorkspace({
  busy,
  fallbackModel,
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
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const routeOptions = modelRoutes?.length ? modelRoutes : FALLBACK_CHAT_MODEL_ROUTES;
  const selectedModelRoute = routeOptions.find((route) => route.route === modelRoute) ?? routeOptions[0];
  const latestAssistantResponse = useMemo(
    () =>
      [...messages]
        .reverse()
        .find((message) => message.role === "assistant" && message.response)?.response,
    [messages],
  );

  function submit(question = draft) {
    const trimmed = question.trim();
    if (!trimmed || busy) {
      return;
    }
    onAsk(trimmed);
    setDraft("");
  }

  function primePrompt(prompt: string) {
    setDraft(prompt);
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(prompt.length, prompt.length);
    });
  }

  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <section className="min-w-0 overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="border-b bg-muted/20 px-4 py-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <MessageSquareText className="size-4 text-muted-foreground" />
                SOP-grounded assistant
              </div>
              <p className="mt-1 max-w-[72ch] text-xs leading-5 text-muted-foreground">
                Hỏi nhanh từ SOP đã publish. Câu trả lời cần citation, route và confidence rõ ràng.
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <StatusPill icon={ShieldCheck} text="published only" />
              <StatusPill icon={BookOpen} text="citations required" />
              <StatusPill icon={Gauge} text={selectedModelRoute.route.replace("_", " ")} />
            </div>
          </div>
        </div>

        <ScrollChatArea hasMessages={messages.length > 0}>
          {messages.length === 0 ? (
            <EmptyChatState onPromptClick={primePrompt} />
          ) : (
            messages.map((message) => (
              <ChatBubble
                key={message.id}
                message={message}
                onCopy={onCopy}
                onOpenDocument={onOpenDocument}
                onOpenQuickSource={onOpenQuickSource}
              />
            ))
          )}
        </ScrollChatArea>

        <div className="border-t bg-background p-3">
          <div className="rounded-xl border bg-card shadow-sm transition-shadow focus-within:shadow-md">
            <textarea
              ref={inputRef}
              className="min-h-20 max-h-40 w-full resize-none rounded-t-xl bg-transparent px-3 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={busy}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  submit();
                }
              }}
              placeholder="Ask a CS case question, ví dụ: KH không nhận được email thì CS xử lý sao?"
              value={draft}
            />
            <div className="flex min-h-11 flex-wrap items-center gap-2 border-t px-2 py-2">
              <Route className="size-4 text-muted-foreground" />
              <Select
                disabled={busy}
                onValueChange={(value) => onModelRouteChange(value as ChatModelRoute)}
                value={modelRoute}
              >
                <SelectTrigger
                  aria-label="Select model route"
                  className="h-7 border-0 bg-transparent px-0 text-muted-foreground shadow-none hover:text-foreground focus-visible:ring-0"
                  size="sm"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="start" className="w-72">
                  {routeOptions.map((route) => (
                    <SelectItem key={route.route} value={route.route}>
                      {route.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Badge className="hidden sm:inline-flex" variant="outline">
                {selectedModelRoute.model}
              </Badge>
              <span className="hidden text-xs text-muted-foreground md:inline">⌘ Enter</span>

              <Button
                aria-label="Send message"
                className={cn("ml-auto rounded-full", draft.trim() && "shadow-sm")}
                disabled={!draft.trim() || busy}
                onClick={() => submit()}
                size="icon-sm"
                title="Ask SOP"
                type="button"
              >
                {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
              </Button>
            </div>
          </div>

          <div className="mt-2 flex flex-wrap gap-2">
            {PROMPT_SUGGESTIONS.map((suggestion) => (
              <PromptButton
                busy={busy}
                key={suggestion.label}
                onClick={() => primePrompt(suggestion.prompt)}
                suggestion={suggestion}
              />
            ))}
          </div>
        </div>
      </section>

      <aside className="space-y-3">
        <RoutePanel
          fallbackModel={fallbackModel}
          latestAssistantResponse={latestAssistantResponse}
          selectedModelRoute={selectedModelRoute}
        />
        <GroundingPanel />
      </aside>
    </div>
  );
}

function ScrollChatArea({ children, hasMessages }: { children: ReactNode; hasMessages: boolean }) {
  return (
    <div
      className={cn(
        "h-[calc(100svh-23rem)] min-h-[28rem] overflow-y-auto",
        hasMessages ? "bg-background" : "bg-muted/10",
      )}
    >
      <div className="grid gap-3 p-4">{children}</div>
    </div>
  );
}

function EmptyChatState({ onPromptClick }: { onPromptClick: (prompt: string) => void }) {
  return (
    <div className="mx-auto grid min-h-[26rem] max-w-2xl place-items-center px-3 text-center">
      <div>
        <div className="mx-auto flex size-10 items-center justify-center rounded-xl border bg-card text-muted-foreground shadow-sm">
          <ShieldCheck className="size-5" />
        </div>
        <h2 className="mt-4 text-base font-semibold">Ask from approved SOPs</h2>
        <p className="mx-auto mt-2 max-w-[56ch] text-sm leading-6 text-muted-foreground">
          Dùng cho case cần câu trả lời có thể hành động, nhưng vẫn phải bám source published, citation và rule hiện hành.
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {PROMPT_SUGGESTIONS.slice(0, 3).map((suggestion) => (
            <PromptButton
              busy={false}
              key={suggestion.label}
              onClick={() => onPromptClick(suggestion.prompt)}
              suggestion={suggestion}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function PromptButton({
  busy,
  onClick,
  suggestion,
}: {
  busy: boolean;
  onClick: () => void;
  suggestion: {
    icon: LucideIcon;
    label: string;
    prompt: string;
  };
}) {
  const Icon = suggestion.icon;
  return (
    <Button
      className="h-8 rounded-full border bg-background px-3 text-xs text-foreground hover:bg-muted/60"
      disabled={busy}
      onClick={onClick}
      type="button"
      variant="ghost"
    >
      <Icon data-icon="inline-start" className="size-3.5 text-muted-foreground transition-colors group-hover/button:text-foreground" />
      {suggestion.label}
    </Button>
  );
}

function StatusPill({ icon: Icon, text }: { icon: LucideIcon; text: string }) {
  return (
    <span className="inline-flex h-7 items-center gap-1.5 rounded-full border bg-background px-2.5 text-xs font-medium text-muted-foreground">
      <Icon className="size-3.5" />
      {text}
    </span>
  );
}

function RoutePanel({
  fallbackModel,
  latestAssistantResponse,
  selectedModelRoute,
}: {
  fallbackModel?: string;
  latestAssistantResponse?: ChatThreadMessage["response"];
  selectedModelRoute: ChatModelRouteConfig;
}) {
  return (
    <section className="rounded-xl border bg-card p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <Route className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Route detail</h2>
      </div>
      <div className="mt-3 rounded-lg border bg-muted/20 p-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="default">{selectedModelRoute.label}</Badge>
          <Badge variant="outline">{selectedModelRoute.route}</Badge>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{selectedModelRoute.description}</p>
        <p className="mt-2 truncate text-[11px] text-muted-foreground">{selectedModelRoute.model}</p>
      </div>
      {latestAssistantResponse ? (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <MiniStat label="Cites" value={latestAssistantResponse.citations.length} />
          <MiniStat label="Conf" value={`${Math.round(latestAssistantResponse.confidence * 100)}%`} />
          <MiniStat label="ms" value={latestAssistantResponse.latency_ms} />
        </div>
      ) : null}
      {fallbackModel ? <p className="mt-3 truncate text-[11px] text-muted-foreground">Fallback: {fallbackModel}</p> : null}
    </section>
  );
}

function GroundingPanel() {
  return (
    <section className="rounded-xl border bg-card p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <ShieldCheck className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Grounding rules</h2>
      </div>
      <div className="mt-3 grid gap-2">
        <RuleRow icon={CheckCircle2} title="Published only" text="Không dùng draft, archived, raw upload." />
        <RuleRow icon={BookOpen} title="Citation gate" text="Không có source đáng tin thì phải từ chối." />
        <RuleRow icon={AlertTriangle} title="High-risk claims" text="Refund, privacy, payment phải được source rõ." />
      </div>
    </section>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border bg-background px-2 py-2">
      <div className="truncate text-sm font-semibold tabular-nums">{value}</div>
      <div className="mt-0.5 text-[10px] uppercase text-muted-foreground">{label}</div>
    </div>
  );
}

function RuleRow({ icon: Icon, text, title }: { icon: LucideIcon; text: string; title: string }) {
  return (
    <div className="flex gap-2 rounded-lg border bg-background px-2.5 py-2">
      <Icon className="mt-0.5 size-3.5 text-muted-foreground" />
      <div className="min-w-0">
        <p className="text-xs font-medium">{title}</p>
        <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{text}</p>
      </div>
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
    <article className={cn("min-w-0", isUser ? "ml-auto w-fit max-w-[82%]" : "mr-auto w-full max-w-[54rem]")}>
      <div
        className={cn(
          "rounded-xl px-3.5 py-3",
          isUser ? "bg-primary text-primary-foreground" : "border bg-card shadow-sm",
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge variant={isUser ? "secondary" : "outline"}>{isUser ? "CS question" : "Grounded answer"}</Badge>
          {message.pending ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
        </div>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        {response ? (
          <div className="mt-4 grid gap-3">
            <ResponseMeta response={response} onCopy={onCopy} />
            {response.steps.length ? (
              <section className="rounded-lg border bg-muted/15 p-3">
                <p className="text-xs font-semibold text-muted-foreground">Action steps</p>
                <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm leading-6">
                  {response.steps.map((step, index) => (
                    <li key={`${step}-${index}`}>{step}</li>
                  ))}
                </ol>
              </section>
            ) : null}
            {response.warnings.length ? (
              <section className="rounded-lg border border-destructive/25 bg-destructive/5 p-3">
                <p className="text-xs font-semibold text-destructive">Warnings</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {response.warnings.slice(0, 8).map((warning, index) => (
                    <Badge key={`${warning}-${index}`} variant="outline">
                      {warning}
                    </Badge>
                  ))}
                </div>
              </section>
            ) : null}
            {response.model_reason ? (
              <p className="rounded-lg bg-muted/25 px-3 py-2 text-xs leading-5 text-muted-foreground">
                Model routing: {response.model_reason}
              </p>
            ) : null}
            {response.sources.length ? (
              <section className="grid gap-2">
                <p className="text-xs font-semibold text-muted-foreground">Published sources used</p>
                <div className="grid gap-2 md:grid-cols-2">
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
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge variant={response.citations.length ? "secondary" : "destructive"}>
        {response.citations.length ? `${response.citations.length} citations` : "no citation"}
      </Badge>
      <Badge variant="outline">{Math.round(response.confidence * 100)}% confidence</Badge>
      {response.model_route ? <Badge variant="outline">{response.model_route}</Badge> : null}
      {response.model_used ? <Badge className="max-w-52 truncate" variant="outline">{response.model_used}</Badge> : null}
      <Badge variant="outline">
        <Clock3 data-icon="inline-start" className="size-3" />
        {response.latency_ms}ms
      </Badge>
      <Button className="ml-auto" onClick={() => onCopy(response.answer)} size="sm" type="button" variant="outline">
        <Clipboard data-icon="inline-start" className="size-4" />
        Copy
      </Button>
    </div>
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
    <div className="min-w-0 rounded-lg border bg-background p-3">
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline">{unitType}</Badge>
        <Badge variant="outline">v{source.version_number}</Badge>
        <Badge variant="outline">{source.rank_source.join("+") || "retrieval"}</Badge>
      </div>
      <p className="mt-2 line-clamp-2 text-sm font-semibold leading-5">{source.heading || source.title}</p>
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{source.content}</p>
      <p className="mt-2 truncate text-[11px] text-muted-foreground">{source.source_filename}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => onOpenQuickSource(source)} size="sm" type="button" variant="outline">
          <Search data-icon="inline-start" className="size-4" />
          Quick rule
        </Button>
        <Button onClick={() => onOpenDocument(source)} size="sm" type="button" variant="ghost">
          <BookOpen data-icon="inline-start" className="size-4" />
          Source
        </Button>
      </div>
    </div>
  );
}
