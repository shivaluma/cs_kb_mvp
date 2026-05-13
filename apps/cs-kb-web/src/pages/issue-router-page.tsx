import { useState } from "react";

import { useCollections, useIssueRouter, useTools } from "@/hooks/api/kb-index";
import { IssueRouterWorkspace } from "@/workspaces/issue-router-workspace";

export function IssueRouterPage() {
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("");
  const [audience, setAudience] = useState("");
  const routerQuery = useIssueRouter({ query, collection, audience });
  const collectionsQuery = useCollections();
  const toolsQuery = useTools();

  return (
    <IssueRouterWorkspace
      audience={audience}
      collection={collection}
      collections={collectionsQuery.data ?? []}
      loading={routerQuery.isLoading}
      query={query}
      results={routerQuery.data ?? []}
      setAudience={setAudience}
      setCollection={setCollection}
      setQuery={setQuery}
      tools={toolsQuery.data ?? []}
    />
  );
}
