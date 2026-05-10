import { lazy, Suspense } from "react";

import { useKbApp } from "@/app-context";
import { RouteLoading } from "@/components/route-loading";

const LookupWorkspace = lazy(() =>
  import("@/workspaces/lookup-workspace").then((module) => ({ default: module.LookupWorkspace })),
);

export function LookupPage() {
  const { lookupProps } = useKbApp();
  return (
    <Suspense fallback={<RouteLoading label="Loading lookup" />}>
      <LookupWorkspace {...lookupProps} />
    </Suspense>
  );
}
