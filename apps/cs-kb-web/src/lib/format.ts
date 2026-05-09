import type { FilterState, SearchResult, SOP } from "@/types";

export function toSearchResult(sop: SOP): SearchResult {
  return {
    sop_id: sop.id,
    title: sop.title,
    snippet: sop.summary,
    category: sop.category,
    audience: sop.audience,
    vertical: sop.vertical,
    tags: sop.tags,
    updated_at: sop.updated_at,
    version: sop.current_version.version_number,
    confidence: 0.8,
  };
}

export function compactFilters(filters: FilterState) {
  return {
    audience: filters.audience === "all" ? [] : [filters.audience],
    vertical: filters.vertical === "all" ? [] : [filters.vertical],
    category: filters.category === "all" ? [] : [filters.category],
  };
}

export function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function fileExternalId(name: string) {
  return name
    .toLowerCase()
    .replace(/\.[^.]+$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}
