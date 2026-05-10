import { lazy, Suspense } from "react";

import { useKbApp } from "@/app-context";
import { RouteLoading } from "@/components/route-loading";

const RetrievalWorkspace = lazy(() =>
  import("@/workspaces/retrieval-workspace").then((module) => ({ default: module.RetrievalWorkspace })),
);

export function RetrievalPage() {
  const { retrievalProps } = useKbApp();
  return (
    <Suspense fallback={<RouteLoading label="Loading retrieval lab" />}>
      <RetrievalWorkspace {...retrievalProps} />
    </Suspense>
  );
}
