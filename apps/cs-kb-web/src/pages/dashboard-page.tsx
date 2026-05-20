import { lazy, Suspense } from "react";
import { useNavigate } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { workspacePaths, type Workspace } from "@/constants";
import { useDocuments } from "@/hooks/api/documents";
import { useFeedbackQueue, useOpsAnalytics } from "@/hooks/api/kb-index";
import { useAdminResetStatus, useMagicResetData, useSystemHealth } from "@/hooks/api/system";
import { useUrlSearch } from "@/hooks/use-url-search";
import { useFeedback } from "@/providers/feedback-context";

const DashboardWorkspace = lazy(() =>
  import("@/workspaces/dashboard-workspace").then((module) => ({ default: module.DashboardWorkspace })),
);

export function DashboardPage() {
  const navigate = useNavigate();
  const { getParam, setParams } = useUrlSearch();
  const query = getParam("q", "");
  const documentsQuery = useDocuments();
  const systemHealthQuery = useSystemHealth();
  const adminResetStatusQuery = useAdminResetStatus();
  const magicResetMutation = useMagicResetData();
  const feedbackQuery = useFeedbackQueue();
  const analyticsQuery = useOpsAnalytics(7);
  const { reportError, reportNotice } = useFeedback();
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

  function resetAllData(confirmation: string) {
    magicResetMutation.mutate(
      {
        actor: "cs-ops-ui",
        confirmation,
        reason: "dashboard_magic_button",
      },
      {
        onSuccess: (response) => {
          const deletedRows = Object.values(response.deleted_counts ?? {}).reduce((sum, count) => sum + count, 0);
          reportNotice(`Reset completed. Deleted ${deletedRows} row${deletedRows === 1 ? "" : "s"} and rebuilt vector schema at ${response.embedding_dimensions} dimensions.`);
          void systemHealthQuery.refetch();
          void adminResetStatusQuery.refetch();
          void documentsQuery.refetch();
          void feedbackQuery.refetch();
          void analyticsQuery.refetch();
        },
        onError: (error) => {
          reportError(error instanceof Error ? error.message : "Reset failed. Check AI service health and reset guard config.");
        },
      },
    );
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading dashboard" />}>
      <DashboardWorkspace
        documents={documents}
        feedbackItems={feedbackQuery.data ?? []}
        adminResetStatus={adminResetStatusQuery.data}
        isAdminResetStatusLoading={adminResetStatusQuery.isLoading}
        isResettingData={magicResetMutation.isPending}
        opsAnalytics={analyticsQuery.data}
        isSystemHealthLoading={systemHealthQuery.isLoading}
        onRunSearch={runLookup}
        onMagicReset={resetAllData}
        onWorkspaceChange={navigateWorkspace}
        query={query}
        refetchSystemHealth={() => void systemHealthQuery.refetch()}
        setQuery={setQuery}
        systemHealth={systemHealthQuery.data}
      />
    </Suspense>
  );
}
