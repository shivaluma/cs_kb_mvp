import { useState } from "react";

import { useCollections, useIssueRouter, useTools } from "@/hooks/api/kb-index";
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
  const audienceOptions = optionizeFilterValues(filterOptionsQuery.data?.audience, "All audiences");
  const verticalOptions = optionizeFilterValues(filterOptionsQuery.data?.vertical, "All verticals");
  const taskTypeOptions = optionizeFilterValues(filterOptionsQuery.data?.task_types, "All tasks");

  return (
    <IssueRouterWorkspace
      audience={audience}
      audienceOptions={audienceOptions}
      collection={collection}
      collections={collectionsQuery.data ?? []}
      loading={routerQuery.isLoading}
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
