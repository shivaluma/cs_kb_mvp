import { lazy, Suspense } from "react";

import { useKbApp } from "@/app-context";
import { RouteLoading } from "@/components/route-loading";

const DocumentsWorkspace = lazy(() =>
  import("@/workspaces/documents-workspace").then((module) => ({ default: module.DocumentsWorkspace })),
);

export function DocumentsPage() {
  const { documentsProps } = useKbApp();
  return (
    <Suspense fallback={<RouteLoading label="Loading documents" />}>
      <DocumentsWorkspace {...documentsProps} />
    </Suspense>
  );
}
