import { useEffect, useRef, useState } from "react";

import { useCollections, useIssueRouter, useTools, useRecordKBEvent } from "@/hooks/api/kb-index";
import { useSearchFilterOptions } from "@/hooks/api/search";
import { optionizeFilterValues } from "@/lib/format";
import { IssueRouterWorkspace } from "@/workspaces/issue-router-workspace";

export function IssueRouterPage() {
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("");
  const [audience, setAudience] = useState("");
  const [vertical, setVertical] = useState("");
  const [taskType, setTaskType] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const routerQuery = useIssueRouter({ query, collection, audience, vertical, taskType, riskLevel });
  const collectionsQuery = useCollections();
  const filterOptionsQuery = useSearchFilterOptions();
  const toolsQuery = useTools();
  const eventMutation = useRecordKBEvent();
  const searchEventRef = useRef("");
  const audienceOptions = optionizeFilterValues(filterOptionsQuery.data?.audience, "All audiences");
  const verticalOptions = optionizeFilterValues(filterOptionsQuery.data?.vertical, "All verticals");
  const taskTypeOptions = optionizeFilterValues(filterOptionsQuery.data?.task_types, "All tasks");

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }
    const searchEventId = crypto.randomUUID();
    searchEventRef.current = searchEventId;
    const handle = window.setTimeout(() => {
      eventMutation.mutate({
        action: "issue_router_search",
        entity_type: "issue_router",
        metadata: {
          search_event_id: searchEventId,
          query: trimmed,
          filters: { collection, audience, vertical, task_type: taskType, risk_level: riskLevel },
        },
      });
    }, 600);
    return () => window.clearTimeout(handle);
  }, [audience, collection, query, riskLevel, taskType, vertical]);

  return (
    <IssueRouterWorkspace
      audience={audience}
      audienceOptions={audienceOptions}
      collection={collection}
      collections={collectionsQuery.data ?? []}
      loading={routerQuery.isLoading}
      onSelectResult={(item, rank) =>
        eventMutation.mutate({
          action: "issue_router_result_click",
          entity_type: "chunk",
          entity_id: item.chunk_id,
          metadata: {
            search_event_id: searchEventRef.current,
            query,
            rank,
            target_title: item.title,
            target_sop_title: item.target_sop_title,
          },
        })
      }
      query={query}
      riskLevel={riskLevel}
      results={routerQuery.data ?? []}
      setAudience={setAudience}
      setCollection={setCollection}
      setQuery={setQuery}
      setRiskLevel={setRiskLevel}
      setTaskType={setTaskType}
      setVertical={setVertical}
      taskType={taskType}
      taskTypeOptions={taskTypeOptions}
      tools={toolsQuery.data ?? []}
      vertical={vertical}
      verticalOptions={verticalOptions}
    />
  );
}
