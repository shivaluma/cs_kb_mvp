import { lazy, Suspense } from "react";
import { useNavigate } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { workspacePaths } from "@/constants";
import { useHomepage } from "@/hooks/api/homepage";
import { useRecordKBEvent, useOpsAnalytics } from "@/hooks/api/kb-index";
import { useSearchAutocomplete, useSOPList } from "@/hooks/api/search";
import { useUrlSearch } from "@/hooks/use-url-search";
import type { Homepage, SOP } from "@/types";

const PortalWorkspace = lazy(() =>
  import("@/workspaces/portal-workspace").then((module) => ({ default: module.PortalWorkspace })),
);

export function PortalPage() {
  const navigate = useNavigate();
  const { getParam, setParams } = useUrlSearch();
  const query = getParam("q", "");
  const homepageQuery = useHomepage();
  const sopsQuery = useSOPList();
  const autocompleteQuery = useSearchAutocomplete(query);
  const analyticsQuery = useOpsAnalytics(14);
  const eventMutation = useRecordKBEvent();
  const homepage = homepageQuery.data ?? emptyHomepage();
  const sops = sopsQuery.data?.items ?? [];

  function setQuery(nextQuery: string) {
    setParams({ q: nextQuery });
  }

  function runSearch(nextQuery = query) {
    const trimmed = nextQuery.trim();
    if (!trimmed) {
      return;
    }
    eventMutation.mutate({
      action: "portal_search",
      entity_type: "search",
      metadata: { query: trimmed, surface: "portal_home" },
    });
    void navigate({
      to: "/search",
      search: { q: trimmed } as never,
    });
  }

  function openSOP(sop: SOP) {
    eventMutation.mutate({
      action: "portal_sop_open",
      entity_type: "sop_version",
      entity_id: sop.current_version_id,
      metadata: { sop_id: sop.id, title: sop.title, surface: "portal_home" },
    });
    void navigate({
      to: "/sop/$sopId",
      params: { sopId: sop.id },
    });
  }

  function openCategory(categoryKey: string) {
    void navigate({
      to: "/category/$categoryKey",
      params: { categoryKey },
    });
  }

  function openChat(nextQuery: string) {
    const trimmed = nextQuery.trim();
    void navigate({
      to: workspacePaths.chat,
      search: (trimmed ? { q: trimmed } : {}) as never,
    });
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading SOP portal" />}>
      <PortalWorkspace
        analytics={analyticsQuery.data}
        homepage={homepage}
        loading={homepageQuery.isLoading || sopsQuery.isLoading}
        onOpenCategory={openCategory}
        onOpenChat={openChat}
        onOpenSOP={openSOP}
        onSearch={runSearch}
        query={query}
        suggestions={autocompleteQuery.data?.suggestions ?? []}
        setQuery={setQuery}
        sops={sops}
      />
    </Suspense>
  );
}

function emptyHomepage(): Homepage {
  return {
    category_shortcuts: [],
    most_viewed: [],
    recently_updated: [],
  };
}
