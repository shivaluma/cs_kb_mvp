import type { FilterOption, FilterState, SearchResult, SOP } from "@/types";

const contentTypeUnitTypes: Record<string, string[]> = {
  sop_rules: [
    "policy_rule",
    "handling_rule",
    "routing_rule",
    "operational_instruction",
    "validation_rule",
    "decision_rule",
    "sla_rule",
    "escalation_rule",
    "case_creation_rule",
    "handoff_rule",
    "workflow_overview",
    "workflow_graph",
    "workflow_step",
    "decision_point",
    "warning",
    "operational_note",
    "macro_script",
  ],
  issue_router: [
    "issue_router_unit",
    "sop_reference",
    "vip_overlay_rule",
    "product_update_note",
  ],
  tool_link: ["tool_link"],
  action_template: ["quick_action_rule"],
  full_sop: ["full_sop"],
};

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
    audience: toFilterList(filters.audience),
    vertical: toFilterList(filters.vertical),
    category: toFilterList(filters.category),
    collections: toFilterList(filters.collection),
    task_types: toFilterList(filters.taskType),
    unit_types: contentTypeUnitTypes[filters.contentType] ?? [],
  };
}

function toFilterList(value: string) {
  return value && value !== "all" ? [value] : [];
}

export function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function optionizeFilterValues(values: string[] | undefined, allLabel: string): FilterOption[] {
  const seen = new Set<string>();
  const options = [{ label: allLabel, value: "all" }];
  for (const value of values ?? []) {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized) || normalized === "all") {
      continue;
    }
    seen.add(normalized);
    options.push({ label: humanizeFilterValue(normalized), value: normalized });
  }
  return options;
}

export function humanizeFilterValue(value: string) {
  const normalized = value.replace(/[-_]+/g, " ").trim();
  const special = normalized.toLowerCase();
  if (special === "mcu") {
    return "MCU";
  }
  if (special === "vip customer") {
    return "VIP customer";
  }
  if (special === "cs l2") {
    return "CS L2";
  }
  return normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
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
