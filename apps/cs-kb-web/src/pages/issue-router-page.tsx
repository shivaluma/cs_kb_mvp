import { useState } from "react";

import { useCollections, useIssueRouter, useTools } from "@/hooks/api/kb-index";
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
  const toolsQuery = useTools();

  return (
    <IssueRouterWorkspace
      audience={audience}
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
      tools={toolsQuery.data ?? []}
      vertical={vertical}
    />
  );
}
