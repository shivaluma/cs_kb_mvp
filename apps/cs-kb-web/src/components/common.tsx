import type { ElementType } from "react";
import {
  Bot,
  CheckCircle2,
  Copy,
  FileClock,
  Search,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { filterOptions } from "@/constants";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  AISuggestion,
  FilterState,
  Macro,
  SearchResult,
} from "@/types";

export function FilterSelect({
  label,
  onValueChange,
  options,
  value,
}: {
  label: string;
  onValueChange: (value: string) => void;
  options: string[];
  value: string;
}) {
  return (
    <div className="grid gap-1.5">
      <label className="text-xs font-medium capitalize text-muted-foreground">
        {label}
      </label>
      <Select onValueChange={onValueChange} value={value}>
        <SelectTrigger className="w-full" size="default">
          <SelectValue placeholder={label} />
        </SelectTrigger>
        <SelectContent align="start">
          <SelectItem value="all">All {label}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function FilterGrid({
  filters,
  onUpdateFilter,
}: {
  filters: FilterState;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
}) {
  return (
    <>
      {Object.entries(filterOptions).map(([key, options]) => (
        <FilterSelect
          key={key}
          label={key}
          onValueChange={(value) =>
            onUpdateFilter(key as keyof FilterState, value)
          }
          options={options}
          value={filters[key as keyof FilterState]}
        />
      ))}
    </>
  );
}

export function Field({
  label,
  onChange,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return (
    <div className="grid gap-1.5">
      <label className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <Input
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder ?? label}
        value={value}
      />
    </div>
  );
}

export function ResultButton({
  item,
  onClick,
  selected,
}: {
  item: SearchResult;
  onClick: () => void;
  selected: boolean;
}) {
  return (
    <button
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        selected && "border-primary bg-primary/5",
      )}
      onClick={onClick}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-sm font-semibold leading-5">
          {item.title}
        </h3>
        <Badge variant="secondary">v{item.version}</Badge>
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-5 text-muted-foreground">
        {item.snippet}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{item.category}</Badge>
        <Badge variant="outline">{item.vertical}</Badge>
        <span className="text-xs text-muted-foreground">
          {formatDate(item.updated_at)}
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${Math.max(item.confidence * 100, 8)}%` }}
        />
      </div>
    </button>
  );
}

export function AISuggestionPanel({ suggestion }: { suggestion: AISuggestion }) {
  return (
    <section className="rounded-2xl border bg-muted/30 p-4">
      <div className="flex items-center gap-2">
        <Bot className="size-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Grounded AI suggestion</h3>
      </div>
      <p className="mt-2 text-sm leading-6">{suggestion.answer}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {(suggestion.citations ?? []).map((citation) => (
          <Badge
            key={`${citation.version_id}-${citation.section}`}
            variant="outline"
          >
            {citation.sop_id} / {citation.section}
          </Badge>
        ))}
        {(suggestion.warnings ?? []).map((warning) => (
          <Badge
            key={warning}
            variant="outline"
          >
            {warning}
          </Badge>
        ))}
      </div>
    </section>
  );
}

export function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border bg-card px-3 py-2 shadow-sm">
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function Fact({
  icon: Icon,
  label,
  value,
}: {
  icon: ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border bg-muted/25 p-3">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Icon className="size-3.5" />
        {label}
      </div>
      <p className="mt-1 truncate text-sm font-semibold">{value}</p>
    </div>
  );
}

export function TextBlock({ title, value }: { title: string; value: string }) {
  return (
    <section>
      <SectionTitle title={title} />
      <p className="mt-2 rounded-xl border bg-muted/25 px-3 py-2 text-sm leading-6 text-muted-foreground">
        {value}
      </p>
    </section>
  );
}

export function SectionTitle({ title }: { title: string }) {
  return <h3 className="text-sm font-semibold">{title}</h3>;
}

export function GovernanceItem({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border bg-muted/25 p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm">{value}</p>
    </div>
  );
}

export function EmptyResults({ query }: { query: string }) {
  return (
    <div className="rounded-xl border border-dashed p-6 text-center">
      <Search className="mx-auto size-8 text-muted-foreground" />
      <h3 className="mt-3 text-sm font-semibold">No reliable source matched</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Try a tag, CRM case reason, or add a governed synonym for{" "}
        <span className="font-medium text-foreground">{query}</span>.
      </p>
    </div>
  );
}

export function EmptyPanel({
  compact = false,
  icon: Icon,
  text,
  title,
}: {
  compact?: boolean;
  icon: ElementType;
  text: string;
  title: string;
}) {
  return (
    <div
      className={cn(
        "grid place-items-center rounded-2xl border border-dashed p-8 text-center",
        !compact && "min-h-[32rem]",
      )}
    >
      <div className="max-w-sm">
        <Icon className="mx-auto size-9 text-muted-foreground" />
        <h2 className="mt-3 text-base font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{text}</p>
      </div>
    </div>
  );
}

export function StatusMessage({
  message,
  onDismiss,
  tone,
}: {
  message: string;
  onDismiss: () => void;
  tone: "success" | "error";
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-xl border px-3 py-2 text-sm",
        tone === "success"
          ? "bg-secondary text-secondary-foreground"
          : "border-destructive/25 bg-destructive/10 text-destructive",
      )}
    >
      <span>{message}</span>
      <button
        className="rounded-md px-2 py-1 text-xs hover:bg-background/60"
        onClick={onDismiss}
        type="button"
      >
        Dismiss
      </button>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  if (status === "published" || status === "active") {
    return (
      <Badge variant="secondary">
        {status}
      </Badge>
    );
  }
  if (status === "in_review" || status === "draft") {
    return (
      <Badge variant="outline">
        {status}
      </Badge>
    );
  }
  if (status === "archived") {
    return <Badge variant="outline">{status}</Badge>;
  }
  return <Badge variant="secondary">{status}</Badge>;
}

export function Rule({ icon: Icon, text }: { icon: ElementType; text: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2">
      <Icon className="size-3.5 text-primary" />
      <span>{text}</span>
    </div>
  );
}

export function ResultSkeleton() {
  return (
    <>
      {[0, 1, 2].map((item) => (
        <div className="rounded-xl border p-3" key={item}>
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-2/3" />
          <div className="mt-4 flex gap-2">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
        </div>
      ))}
    </>
  );
}

export function MacroCopyButton({
  macro,
  onCopyMacro,
}: {
  macro: Macro;
  onCopyMacro: (macro: Macro) => void;
}) {
  return (
    <Button
      aria-label={`Copy macro ${macro.title}`}
      onClick={() => onCopyMacro(macro)}
      size="icon"
      type="button"
      variant="outline"
    >
      <Copy className="size-4" />
    </Button>
  );
}

export function LoadingIcon() {
  return <Sparkles data-icon="inline-start" className="size-4" />;
}

export { filterOptions, FileClock };
