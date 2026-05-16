import {
  IconLoader2 as Loader2,
  IconSearch as Search,
  IconX as X,
} from "@tabler/icons-react";
import type { KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type SearchBarProps = {
  actionLabel?: string;
  autoFocus?: boolean;
  className?: string;
  clearable?: boolean;
  disabled?: boolean;
  id?: string;
  loading?: boolean;
  multiline?: boolean;
  onChange: (value: string) => void;
  onSearch?: () => void;
  placeholder: string;
  rows?: number;
  value: string;
};

export function SearchBar({
  actionLabel = "Search",
  autoFocus,
  className,
  clearable = true,
  disabled,
  id,
  loading,
  multiline,
  onChange,
  onSearch,
  placeholder,
  rows = 4,
  value,
}: SearchBarProps) {
  const canSearch = value.trim().length > 0 && !disabled && !loading;

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) {
    if (event.key !== "Enter" || !onSearch) {
      return;
    }
    if (multiline && (event.shiftKey || event.metaKey || event.ctrlKey)) {
      return;
    }
    event.preventDefault();
    onSearch();
  }

  const searchIcon = (
    <Search className={cn("pointer-events-none absolute left-3 size-4 text-muted-foreground", multiline ? "top-3.5" : "top-1/2 -translate-y-1/2")} />
  );
  const clearButton =
    clearable && value ? (
      <Button
        aria-label="Clear search"
        className={cn("absolute right-2 size-7", multiline ? "top-2" : "top-1/2 -translate-y-1/2")}
        onClick={() => onChange("")}
        size="icon"
        type="button"
        variant="ghost"
      >
        <X className="size-3.5" />
      </Button>
    ) : null;

  return (
    <div className={cn("grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]", className)}>
      <div className="relative min-w-0">
        {searchIcon}
        {multiline ? (
          <textarea
            autoFocus={autoFocus}
            className="min-h-28 w-full resize-y rounded-md border border-input bg-background px-3 py-2 pl-9 pr-10 text-sm leading-6 shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled}
            id={id}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={rows}
            value={value}
          />
        ) : (
          <Input
            autoFocus={autoFocus}
            className="h-10 pl-9 pr-10"
            disabled={disabled}
            id={id}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            value={value}
          />
        )}
        {clearButton}
      </div>
      {onSearch ? (
        <Button className="h-10 px-4" disabled={!canSearch} onClick={onSearch} type="button">
          {loading ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Search data-icon="inline-start" className="size-4" />}
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
