import { AlertTriangle, BookOpen, Clipboard, Loader2, MessageSquareText, Search, Send, ShieldCheck, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyPanel } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChatThreadMessage, RetrievalResult } from "@/types";

export function ChatWorkspace({
  busy,
  messages,
  onAsk,
  onCopy,
  onOpenDocument,
  onOpenQuickSource,
}: {
  busy: boolean;
  messages: ChatThreadMessage[];
  onAsk: (question: string) => void;
  onCopy: (text: string) => void;
  onOpenDocument: (source: RetrievalResult) => void;
  onOpenQuickSource: (source: RetrievalResult) => void;
}) {
  const [draft, setDraft] = useState("");
  const examples = useMemo(
    () => [
      "case này cần kiểm tra thông tin nào trước?",
      "khi nào cần chuyển xử lý cho team liên quan?",
      "có cảnh báo bảo mật hoặc compliance nào không?",
      "macro phản hồi phù hợp là gì?",
    ],
    [],
  );

  function submit(question = draft) {
    const trimmed = question.trim();
    if (!trimmed || busy) {
      return;
    }
    onAsk(trimmed);
    setDraft("");
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem]">
      <section className="min-w-0 rounded-xl border bg-card">
        <div className="border-b p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <MessageSquareText className="size-4" />
                SOP-grounded assistant
              </div>
              <p className="mt-1 max-w-[76ch] text-sm leading-5 text-muted-foreground">
                Answers are generated only after retrieving published curated SOP units. No raw uploads, drafts, archived versions, or model memory.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">published only</Badge>
              <Badge variant="outline">citations required</Badge>
              <Badge variant="outline">no policy invention</Badge>
            </div>
          </div>
        </div>

        <ScrollArea className="h-[calc(100svh-22rem)] min-h-[34rem]">
          <div className="grid gap-4 p-4">
            {messages.length === 0 ? (
              <EmptyPanel
                icon={ShieldCheck}
                title="Ask from approved SOPs"
                text="Use this when you need an actionable answer but do not yet know which SOP or rule to open."
              />
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
          </div>
        </ScrollArea>

        <div className="border-t bg-background p-3">
          <div className="mb-2 flex flex-wrap gap-2">
            {examples.map((example) => (
              <Button
                disabled={busy}
                key={example}
                onClick={() => submit(example)}
                size="sm"
                type="button"
                variant="outline"
              >
                {example}
              </Button>
            ))}
          </div>
          <div className="grid gap-2 rounded-xl border bg-card p-2">
            <textarea
              className="min-h-24 resize-none rounded-lg bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/30"
              disabled={busy}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  submit();
                }
              }}
              placeholder="Ask a CS case question, for example: KH không nhận được email thì CS xử lý sao?"
              value={draft}
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">⌘ Enter to ask. The assistant will refuse unsupported answers.</p>
              <Button disabled={!draft.trim() || busy} onClick={() => submit()} type="button">
                {busy ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Send data-icon="inline-start" className="size-4" />}
                Ask SOP
              </Button>
            </div>
          </div>
        </div>
      </section>

      <aside className="space-y-4">
        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle>Guardrails</CardTitle>
            <CardDescription>Designed as an SOP assistant, not a general chatbot.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <Guardrail icon={ShieldCheck} title="Source scope" text="Only latest published document versions are retrieved." />
            <Guardrail icon={BookOpen} title="Citation gate" text="No reliable citation means no operational answer." />
            <Guardrail icon={AlertTriangle} title="Policy safety" text="Refund, compensation, security, and escalation claims must be explicitly sourced." />
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle>Good prompts</CardTitle>
            <CardDescription>Use operational wording and include the case context you know.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {examples.map((example) => (
              <button
                className="w-full rounded-lg border bg-background px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
                key={example}
                onClick={() => submit(example)}
                type="button"
              >
                {example}
              </button>
            ))}
          </CardContent>
        </Card>
      </aside>
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
    <article className={isUser ? "ml-auto max-w-[80%]" : "mr-auto max-w-[92%]"}>
      <div className={isUser ? "rounded-xl bg-primary px-4 py-3 text-primary-foreground" : "rounded-xl border bg-background px-4 py-3"}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge variant={isUser ? "secondary" : "outline"}>{isUser ? "CS question" : "Grounded answer"}</Badge>
          {message.pending ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
        </div>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        {response ? (
          <div className="mt-4 grid gap-4">
            {response.steps.length ? (
              <div className="rounded-lg border bg-muted/15 p-3">
                <p className="text-xs font-semibold text-muted-foreground">Action steps</p>
                <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm leading-6">
                  {response.steps.map((step, index) => (
                    <li key={`${step}-${index}`}>{step}</li>
                  ))}
                </ol>
              </div>
            ) : null}
            {response.warnings.length ? (
              <div className="rounded-lg border border-destructive/25 bg-destructive/5 p-3">
                <p className="text-xs font-semibold text-destructive">Warnings</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {response.warnings.slice(0, 8).map((warning, index) => (
                    <Badge key={`${warning}-${index}`} variant="outline">{warning}</Badge>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={response.citations.length ? "secondary" : "destructive"}>
                {response.citations.length ? `${response.citations.length} citations` : "no citation"}
              </Badge>
              <Badge variant="outline">{Math.round(response.confidence * 100)}% confidence</Badge>
              {response.model_route ? <Badge variant="outline">{response.model_route}</Badge> : null}
              {response.model_used ? <Badge variant="outline">{response.model_used}</Badge> : null}
              <Badge variant="outline">{response.latency_ms}ms</Badge>
              <Button onClick={() => onCopy(response.answer)} size="sm" type="button" variant="outline">
                <Clipboard data-icon="inline-start" className="size-4" />
                Copy answer
              </Button>
            </div>
            {response.model_reason ? <p className="text-xs text-muted-foreground">Model routing: {response.model_reason}</p> : null}
            {response.sources.length ? (
              <div className="grid gap-2">
                <p className="text-xs font-semibold text-muted-foreground">Published sources used</p>
                {response.sources.slice(0, 4).map((source) => (
                  <SourceCard
                    key={source.chunk_id}
                    onOpenDocument={onOpenDocument}
                    onOpenQuickSource={onOpenQuickSource}
                    source={source}
                  />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
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
    <div className="rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline">{unitType}</Badge>
            <Badge variant="outline">v{source.version_number}</Badge>
            <Badge variant="outline">{source.rank_source.join("+") || "retrieval"}</Badge>
          </div>
          <p className="mt-2 text-sm font-semibold leading-5">{source.heading || source.title}</p>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{source.content}</p>
          <p className="mt-2 truncate text-[11px] text-muted-foreground">{source.source_filename}</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => onOpenQuickSource(source)} size="sm" type="button" variant="outline">
          <Search data-icon="inline-start" className="size-4" />
          Open quick rule
        </Button>
        <Button onClick={() => onOpenDocument(source)} size="sm" type="button" variant="ghost">
          <BookOpen data-icon="inline-start" className="size-4" />
          Open source
        </Button>
      </div>
    </div>
  );
}

function Guardrail({
  icon: Icon,
  text,
  title,
}: {
  icon: LucideIcon;
  text: string;
  title: string;
}) {
  return (
    <div className="flex gap-3 rounded-lg border bg-background p-3">
      <Icon className="mt-0.5 size-4 text-muted-foreground" />
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p>
      </div>
    </div>
  );
}
