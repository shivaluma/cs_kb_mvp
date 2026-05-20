import { useMemo, useState, type ComponentProps, type ElementType } from "react";
import {
  IconRobot as Bot,
  IconCircleCheck as CheckCircle2,
  IconCopy as Copy,
  IconFileTime as FileClock,
  IconSearch as Search,
  IconAdjustmentsHorizontal as SlidersHorizontal,
  IconSparkles as Sparkles
} from "@tabler/icons-react";

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
import { filterOptions as defaultFilterOptions } from "@/constants";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  AISuggestion,
  FilterOption,
  FilterState,
  Macro,
  SearchResult,
} from "@/types";

type MetadataItem = string | number | false | null | undefined;
type BadgeVariant = ComponentProps<typeof Badge>["variant"];

function normalizeMetadataItems(items: MetadataItem[]) {
  return items
    .filter((item): item is string | number => item !== false && item !== null && item !== undefined)
    .map((item) => String(item).trim())
    .filter(Boolean);
}

export function MetaLine({
  className,
  items,
  maxItems = 5,
}: {
  className?: string;
  items: MetadataItem[];
  maxItems?: number;
}) {
  const values = normalizeMetadataItems(items);
  if (!values.length) {
    return null;
  }
  const visible = values.slice(0, maxItems);
  const hidden = Math.max(values.length - visible.length, 0);

  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-5 text-muted-foreground", className)}>
      {visible.map((item, index) => (
        <span className="inline-flex min-w-0 items-center gap-x-2" key={`${item}-${index}`}>
          {index > 0 ? <span className="text-border">•</span> : null}
          <span className="max-w-full truncate">{item}</span>
        </span>
      ))}
      {hidden ? (
        <span className="inline-flex items-center gap-x-2">
          <span className="text-border">•</span>
          <span>+{hidden} more</span>
        </span>
      ) : null}
    </div>
  );
}

export function TagSummary({
  className,
  items,
  maxItems = 4,
  variant = "outline",
}: {
  className?: string;
  items: MetadataItem[];
  maxItems?: number;
  variant?: BadgeVariant;
}) {
  const values = normalizeMetadataItems(items);
  if (!values.length) {
    return null;
  }
  const visible = values.slice(0, maxItems);
  const hidden = Math.max(values.length - visible.length, 0);

  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-1.5", className)}>
      {visible.map((item, index) => (
        <Badge className="max-w-full truncate" key={`${item}-${index}`} variant={variant}>
          {item}
        </Badge>
      ))}
      {hidden ? (
        <span className="rounded-full px-1.5 text-xs leading-5 text-muted-foreground">+{hidden}</span>
      ) : null}
    </div>
  );
}

export function FilterSelect({
  label,
  onValueChange,
  options,
  value,
}: {
  label: string;
  onValueChange: (value: string) => void;
  options: FilterOption[];
  value: string;
}) {
  return (
    <div className="grid gap-1.5">
      <label className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <Select onValueChange={onValueChange} value={value}>
        <SelectTrigger className="w-full" size="default">
          <SelectValue placeholder={label} />
        </SelectTrigger>
        <SelectContent align="start">
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function FilterGrid({
  collectionOptions = [],
  filterOptions = {},
  filters,
  onUpdateFilter,
  showAdvancedByDefault = false,
}: {
  collectionOptions?: FilterOption[];
  filterOptions?: Partial<Record<Exclude<keyof FilterState, "collection">, FilterOption[]>>;
  filters: FilterState;
  onUpdateFilter: (key: keyof FilterState, value: string) => void;
  showAdvancedByDefault?: boolean;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(showAdvancedByDefault);
  const collections = useMemo(
    () => [
      { label: "All collections", value: "all" },
      ...collectionOptions.filter((option) => option.value !== "all"),
    ],
    [collectionOptions],
  );
  const advancedFilters: Array<{
    key: keyof FilterState;
    label: string;
    options: FilterOption[];
  }> = [
    { key: "taskType", label: "Task type", options: filterOptions.taskType ?? defaultFilterOptions.taskType },
    { key: "vertical", label: "Vertical", options: filterOptions.vertical ?? defaultFilterOptions.vertical },
    { key: "category", label: "Category", options: filterOptions.category ?? defaultFilterOptions.category },
  ];
  const advancedActiveCount = advancedFilters.filter(({ key }) => filters[key] !== "all").length;
  return (
    <div className="space-y-2">
      <div className="grid gap-2 md:grid-cols-3">
        <FilterSelect
          label="Collection"
          onValueChange={(value) => onUpdateFilter("collection", value)}
          options={collections}
          value={filters.collection}
        />
        <FilterSelect
          label="Audience"
          onValueChange={(value) => onUpdateFilter("audience", value)}
          options={filterOptions.audience ?? defaultFilterOptions.audience}
          value={filters.audience}
        />
        <FilterSelect
          label="Content type"
          onValueChange={(value) => onUpdateFilter("contentType", value)}
          options={filterOptions.contentType ?? defaultFilterOptions.contentType}
          value={filters.contentType}
        />
      </div>

      <div className="space-y-2">
        <Button
          className="h-8 px-2 text-xs text-muted-foreground"
          onClick={() => setAdvancedOpen((current) => !current)}
          type="button"
          variant="ghost"
        >
          <SlidersHorizontal data-icon="inline-start" className="size-3.5" />
          Advanced filters
          {advancedActiveCount > 0 ? <Badge variant="secondary">{advancedActiveCount}</Badge> : null}
        </Button>

        {advancedOpen ? (
          <div className="grid gap-2 md:grid-cols-3">
            {advancedFilters.map(({ key, label, options }) => (
              <FilterSelect
                key={key}
                label={label}
                onValueChange={(value) => onUpdateFilter(key, value)}
                options={options}
                value={filters[key]}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
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
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-5 text-muted-foreground">
        {item.snippet}
      </p>
      <MetaLine className="mt-3" items={[`v${item.version}`, item.category, item.vertical, formatDate(item.updated_at)]} />
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
  if (status === "rejected") {
    return <Badge variant="destructive">{status}</Badge>;
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

export { defaultFilterOptions as filterOptions, FileClock };
