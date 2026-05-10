import { lazy, Suspense } from "react";

import { useKbApp } from "@/app-context";
import { RouteLoading } from "@/components/route-loading";

const DashboardWorkspace = lazy(() =>
  import("@/workspaces/dashboard-workspace").then((module) => ({ default: module.DashboardWorkspace })),
);

export function DashboardPage() {
  const { dashboardProps } = useKbApp();
  return (
    <Suspense fallback={<RouteLoading label="Loading dashboard" />}>
      <DashboardWorkspace {...dashboardProps} />
    </Suspense>
  );
}
