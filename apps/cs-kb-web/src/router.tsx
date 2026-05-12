import { createRootRoute, createRoute, createRouter, Navigate } from "@tanstack/react-router";

import { App } from "@/App";
import { workspacePaths } from "@/constants";
import { ChatPage } from "@/pages/chat-page";
import { DashboardPage } from "@/pages/dashboard-page";
import { DocumentsPage } from "@/pages/documents-page";
import { LookupPage } from "@/pages/lookup-page";
import { RelationsPage } from "@/pages/relations-page";
import { RetrievalPage } from "@/pages/retrieval-page";
import { SynonymsPage } from "@/pages/synonyms-page";

const rootRoute = createRootRoute({
  component: App,
  notFoundComponent: () => <Navigate replace to={workspacePaths.dashboard} />,
});

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: workspacePaths.dashboard,
  component: DashboardPage,
});

const lookupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: workspacePaths.lookup,
  component: LookupPage,
});

const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: workspacePaths.chat,
  component: ChatPage,
});

const documentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: workspacePaths.documents,
  component: DocumentsPage,
});

const relationsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: workspacePaths.relations,
  component: RelationsPage,
});

const synonymsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: workspacePaths.synonyms,
  component: SynonymsPage,
});

const retrievalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: workspacePaths.retrieval,
  component: RetrievalPage,
});

const routeTree = rootRoute.addChildren([
  dashboardRoute,
  lookupRoute,
  chatRoute,
  documentsRoute,
  relationsRoute,
  synonymsRoute,
  retrievalRoute,
]);

export const router = createRouter({
  defaultPreload: "intent",
  routeTree,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
