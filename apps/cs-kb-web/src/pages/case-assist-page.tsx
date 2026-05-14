import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { RouteLoading } from "@/components/route-loading";
import { defaultFilters } from "@/constants";
import { useActionTemplates, useCollections, useIssueRouter, useRecordKBEvent, useTools } from "@/hooks/api/kb-index";
import { useSearch, useSearchFilterOptions } from "@/hooks/api/search";
import { compactFilters, optionizeFilterValues } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { CaseAssistCandidate } from "@/workspaces/case-assist-workspace";
import type { ActionTemplateSummary, FilterOption, FilterState, ToolLinkSummary } from "@/types";

const CaseAssistWorkspace = lazy(() =>
  import("@/workspaces/case-assist-workspace").then((module) => ({ default: module.CaseAssistWorkspace })),
);

export function CaseAssistPage() {
  const { reportError, reportNotice } = useFeedback();
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<FilterState>({
    collection: defaultFilters.collection,
    audience: defaultFilters.audience,
    contentType: defaultFilters.contentType,
    taskType: defaultFilters.taskType,
    vertical: defaultFilters.vertical,
    category: defaultFilters.category,
  });
  const [riskLevel, setRiskLevel] = useState("all");
  const searchEventRef = useRef("");
  const trimmedQuery = query.trim();
  const collectionFilter = filters.collection === "all" ? "" : filters.collection;
  const audienceFilter = filters.audience === "all" ? "" : filters.audience;
  const verticalFilter = filters.vertical === "all" ? "" : filters.vertical;
  const taskTypeFilter = filters.taskType === "all" ? "" : filters.taskType;
  const riskFilter = riskLevel === "all" ? "" : riskLevel;
  const routerQuery = useIssueRouter({
    query: trimmedQuery,
    collection: collectionFilter,
    audience: audienceFilter,
    vertical: verticalFilter,
    taskType: taskTypeFilter,
    riskLevel: riskFilter,
  });
  const collectionsQuery = useCollections();
  const toolsQuery = useTools(collectionFilter);
  const actionTemplatesQuery = useActionTemplates(collectionFilter);
  const filterOptionsQuery = useSearchFilterOptions();
  const searchMutation = useSearch();
  const eventMutation = useRecordKBEvent();
  const collectionOptions: FilterOption[] = useMemo(
    () =>
      (collectionsQuery.data ?? []).map((collection) => ({
        label: collection.name,
        value: collection.slug,
      })),
    [collectionsQuery.data],
  );
  const dynamicFilterOptions = useMemo(
    () => ({
      audience: optionizeFilterValues(filterOptionsQuery.data?.audience, "All audiences"),
      vertical: optionizeFilterValues(filterOptionsQuery.data?.vertical, "All verticals"),
      category: optionizeFilterValues(filterOptionsQuery.data?.category, "All categories"),
      taskType: optionizeFilterValues(filterOptionsQuery.data?.task_types, "All tasks"),
    }),
    [filterOptionsQuery.data],
  );

  useEffect(() => {
    if (!trimmedQuery) {
      return;
    }
    const handle = window.setTimeout(() => {
      runAssistSearch();
    }, 450);
    return () => window.clearTimeout(handle);
  }, [filters, riskLevel, trimmedQuery]);

  function updateFilter(key: keyof FilterState, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function runAssistSearch() {
    if (!trimmedQuery) {
      searchMutation.reset();
      return;
    }
    const searchEventId = crypto.randomUUID();
    searchEventRef.current = searchEventId;
    const compacted = compactFilters(filters);
    eventMutation.mutate({
      action: "sop_search",
      entity_type: "search",
      metadata: {
        search_event_id: searchEventId,
        query: trimmedQuery,
        surface: "case_assist",
        filters: { ...compacted, risk_level: riskFilter },
      },
    });
    eventMutation.mutate({
      action: "issue_router_search",
      entity_type: "issue_router",
      metadata: {
        search_event_id: searchEventId,
        query: trimmedQuery,
        surface: "case_assist",
        filters: { collection: collectionFilter, audience: audienceFilter, vertical: verticalFilter, task_type: taskTypeFilter, risk_level: riskFilter },
      },
    });
    searchMutation.mutate(
      {
        query: trimmedQuery,
        include_semantic: true,
        filters: compacted,
      },
      {
        onError: () => reportError("Case Assist search failed. Try SOP Lookup if you need a direct keyword fallback."),
      },
    );
  }

  function recordCandidateEvent(candidate: CaseAssistCandidate, action: string, rank?: number) {
    eventMutation.mutate({
      action,
      entity_type: "chunk",
      entity_id: candidate.chunkId,
      metadata: {
        search_event_id: searchEventRef.current,
        query: trimmedQuery,
        surface: "case_assist",
        rank,
        source_role: candidate.sourceRole,
        unit_type: candidate.unitType,
        target_title: candidate.title,
        parent_title: candidate.parentTitle,
      },
    });
  }

  async function copyText(text: string, notice: string, metadata: Record<string, unknown>, action = "quick_answer_open") {
    try {
      await navigator.clipboard.writeText(text);
      eventMutation.mutate({
        action,
        entity_type: "case_assist",
        metadata: {
          search_event_id: searchEventRef.current,
          query: trimmedQuery,
          surface: "case_assist",
          ...metadata,
        },
      });
      reportNotice(notice);
    } catch {
      reportError("Clipboard permission blocked. You can still select the text manually.");
    }
  }

  function openTool(tool: ToolLinkSummary) {
    eventMutation.mutate({
      action: "tool_link_open",
      entity_type: "tool",
      entity_id: tool.id,
      metadata: {
        search_event_id: searchEventRef.current,
        query: trimmedQuery,
        surface: "case_assist",
        tool_name: tool.name,
        tool_type: tool.tool_type,
      },
    });
  }

  async function copyActionTemplate(template: ActionTemplateSummary) {
    await copyText(
      template.copy_template || template.description || template.name,
      `Copied action template: ${template.name}.`,
      { template_id: template.id, template_name: template.name, action_type: template.action_type },
      "action_template_copy",
    );
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading Case Assist" />}>
      <CaseAssistWorkspace
        actionTemplates={actionTemplatesQuery.data ?? []}
        collectionOptions={collectionOptions}
        dynamicFilterOptions={dynamicFilterOptions}
        filters={filters}
        loading={routerQuery.isLoading || searchMutation.isPending}
        onCopyActionTemplate={copyActionTemplate}
        onCopyChecklist={(candidate, checklist) =>
          copyText(
            checklist.map((item) => `- [ ] ${item}`).join("\n"),
            "Copied checklist.",
            { chunk_id: candidate.chunkId, target_title: candidate.title, source_role: candidate.sourceRole },
            "action_template_copy",
          )
        }
        onCopyQuickAnswer={(candidate) =>
          copyText(
            candidate.content,
            "Copied quick answer.",
            { chunk_id: candidate.chunkId, target_title: candidate.title, source_role: candidate.sourceRole },
            "quick_answer_open",
          )
        }
        onOpenFullSop={(candidate) => recordCandidateEvent(candidate, "full_sop_open")}
        onOpenQuickAnswer={(candidate) => recordCandidateEvent(candidate, "quick_answer_open")}
        onOpenTool={openTool}
        onRunSearch={runAssistSearch}
        onSelectCandidate={(candidate, rank) => recordCandidateEvent(candidate, candidate.sourceRole === "issue_router" ? "issue_router_result_click" : "search_result_click", rank)}
        onUpdateFilter={updateFilter}
        query={query}
        results={trimmedQuery ? (searchMutation.data?.semantic_results ?? []) : []}
        riskLevel={riskLevel}
        routerResults={trimmedQuery ? (routerQuery.data ?? []) : []}
        searchEventId={searchEventRef.current}
        setQuery={setQuery}
        setRiskLevel={setRiskLevel}
        tools={toolsQuery.data ?? []}
      />
    </Suspense>
  );
}
