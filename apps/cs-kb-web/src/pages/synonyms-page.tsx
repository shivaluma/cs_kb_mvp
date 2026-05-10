import { lazy, Suspense } from "react";

import { useKbApp } from "@/app-context";
import { RouteLoading } from "@/components/route-loading";

const SynonymsWorkspace = lazy(() =>
  import("@/workspaces/synonyms-workspace").then((module) => ({ default: module.SynonymsWorkspace })),
);

export function SynonymsPage() {
  const { synonymsProps } = useKbApp();
  return (
    <Suspense fallback={<RouteLoading label="Loading synonyms" />}>
      <SynonymsWorkspace {...synonymsProps} />
    </Suspense>
  );
}
