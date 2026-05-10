import { lazy, Suspense } from "react";
import { useNavigate } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { workspacePaths, type Workspace } from "@/constants";
import { useDocuments } from "@/hooks/api/documents";
import { useHomepage } from "@/hooks/api/homepage";
import { useSynonyms } from "@/hooks/api/synonyms";
import { useUrlSearch } from "@/hooks/use-url-search";

const DashboardWorkspace = lazy(() =>
  import("@/workspaces/dashboard-workspace").then((module) => ({ default: module.DashboardWorkspace })),
);

export function DashboardPage() {
  const navigate = useNavigate();
  const { getParam, setParams } = useUrlSearch();
  const query = getParam("q", "khach khong nhan du mon co duoc refund khong");
  const homepageQuery = useHomepage();
  const documentsQuery = useDocuments();
  const synonymsQuery = useSynonyms("active");
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
    void navigate({
      to: workspacePaths.lookup,
      search: { q: query } as never,
    });
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading dashboard" />}>
      <DashboardWorkspace
        documents={documents}
        homepage={homepageQuery.data}
        onRunSearch={runLookup}
        onWorkspaceChange={navigateWorkspace}
        query={query}
        setQuery={setQuery}
        synonyms={synonymsQuery.data ?? []}
      />
    </Suspense>
  );
}
