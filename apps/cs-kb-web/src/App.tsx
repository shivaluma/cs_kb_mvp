import { useState } from "react";
import { Outlet, useNavigate, useRouterState } from "@tanstack/react-router";

import { AppShell } from "@/components/app-shell";
import { pathForWorkspace, workspaceFromPath, workspacePaths, type Workspace } from "@/constants";
import { useDocuments } from "@/hooks/api/documents";
import { useSynonyms } from "@/hooks/api/synonyms";
import { FeedbackProvider, useFeedback } from "@/providers/feedback-context";

export function App() {
  return (
    <FeedbackProvider>
      <AppFrame />
    </FeedbackProvider>
  );
}

function AppFrame() {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const workspace = workspaceFromPath(pathname);
  const [commandQuery, setCommandQuery] = useState("");
  const documentsQuery = useDocuments();
  const synonymsQuery = useSynonyms("active");
  const { clearError, clearNotice, error, notice } = useFeedback();

  const documents = documentsQuery.data ?? [];
  const synonyms = synonymsQuery.data ?? [];

  function navigateWorkspace(nextWorkspace: Workspace) {
    void navigate({ to: pathForWorkspace(nextWorkspace) });
  }

  function commandSearch(nextQuery: string) {
    const trimmed = nextQuery.trim();
    if (!trimmed) {
      return;
    }
    setCommandQuery(trimmed);
    void navigate({
      to: workspacePaths.lookup,
      search: { q: trimmed } as never,
    });
  }

  return (
    <AppShell
      documentCount={documents.length}
      error={error || (documentsQuery.error ? "Cannot reach the API. Check API service and port 8080." : "")}
      latency="route-owned"
      notice={notice}
      onCommandSearch={commandSearch}
      onDismissError={clearError}
      onDismissNotice={clearNotice}
      onWorkspaceChange={navigateWorkspace}
      query={commandQuery}
      setQuery={setCommandQuery}
      synonymCount={synonyms.length}
      workspace={workspace}
    >
      <Outlet />
    </AppShell>
  );
}
