import { lazy, Suspense } from "react";
import { useNavigate } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { workspacePaths, type Workspace } from "@/constants";
import { useDocuments } from "@/hooks/api/documents";
import { useFeedbackQueue, useOpsAnalytics } from "@/hooks/api/kb-index";
import { useSystemHealth } from "@/hooks/api/system";
import { useUrlSearch } from "@/hooks/use-url-search";

const DashboardWorkspace = lazy(() =>
  import("@/workspaces/dashboard-workspace").then((module) => ({ default: module.DashboardWorkspace })),
);

export function DashboardPage() {
  const navigate = useNavigate();
  const { getParam, setParams } = useUrlSearch();
  const query = getParam("q", "");
  const documentsQuery = useDocuments();
  const systemHealthQuery = useSystemHealth();
  const feedbackQuery = useFeedbackQueue();
  const analyticsQuery = useOpsAnalytics(7);
  const documents = [...(documentsQuery.data ?? [])].sort((left, right) => {
    if (left.status !== right.status) {
      return left.status === "active" ? -1 : 1;
    }
    return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  });

  function navigateWorkspace(workspace: Workspace) {
    void navigate({ to: workspacePaths[workspace] });
  }

  function setQuery(nextQuery: string) {
    setParams({ q: nextQuery });
  }

  function runLookup() {
    const trimmedQuery = query.trim();
    void navigate({
      to: workspacePaths.lookup,
      search: (trimmedQuery ? { q: trimmedQuery } : {}) as never,
    });
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading dashboard" />}>
      <DashboardWorkspace
        documents={documents}
        feedbackItems={feedbackQuery.data ?? []}
        opsAnalytics={analyticsQuery.data}
        isSystemHealthLoading={systemHealthQuery.isLoading}
        onRunSearch={runLookup}
        onWorkspaceChange={navigateWorkspace}
        query={query}
        refetchSystemHealth={() => void systemHealthQuery.refetch()}
        setQuery={setQuery}
        systemHealth={systemHealthQuery.data}
      />
    </Suspense>
  );
}
