import { lazy, Suspense } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { useHomepage } from "@/hooks/api/homepage";
import { useRecordKBEvent } from "@/hooks/api/kb-index";
import { useSOPList } from "@/hooks/api/search";
import { categoryKey, labelFromKey } from "@/lib/format";
import type { SOP } from "@/types";

const CategoryWorkspace = lazy(() =>
  import("@/workspaces/category-workspace").then((module) => ({ default: module.CategoryWorkspace })),
);

export function CategoryPage() {
  const navigate = useNavigate();
  const { categoryKey: routeCategoryKey } = useParams({ from: "/category/$categoryKey" });
  const sopsQuery = useSOPList();
  const homepageQuery = useHomepage();
  const eventMutation = useRecordKBEvent();
  const allSops = sopsQuery.data?.items ?? [];
  const categoryLabel =
    homepageQuery.data?.category_shortcuts.find((item) => categoryKey(item.key || item.label) === routeCategoryKey)?.label ??
    allSops.find((sop) => categoryKey(sop.category) === routeCategoryKey)?.category ??
    labelFromKey(routeCategoryKey);
  const sops = allSops.filter((sop) => categoryKey(sop.category || "uncategorized") === routeCategoryKey);

  function openSOP(sop: SOP) {
    eventMutation.mutate({
      action: "category_sop_open",
      entity_type: "sop_version",
      entity_id: sop.current_version_id,
      metadata: { category: categoryLabel, sop_id: sop.id, title: sop.title },
    });
    void navigate({
      to: "/sop/$sopId",
      params: { sopId: sop.id },
    });
  }

  function searchCategory() {
    void navigate({
      to: "/search",
      search: { q: categoryLabel, category: categoryLabel } as never,
    });
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading category" />}>
      <CategoryWorkspace
        categoryKey={routeCategoryKey}
        categoryLabel={categoryLabel}
        loading={sopsQuery.isLoading || homepageQuery.isLoading}
        onOpenSOP={openSOP}
        onSearchCategory={searchCategory}
        sops={sops}
        totalSops={allSops.length}
      />
    </Suspense>
  );
}
