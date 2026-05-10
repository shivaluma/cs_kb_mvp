import { createContext, useContext, type ComponentProps } from "react";

import type { DashboardWorkspace } from "@/workspaces/dashboard-workspace";
import type { DocumentsWorkspace } from "@/workspaces/documents-workspace";
import type { LookupWorkspace } from "@/workspaces/lookup-workspace";
import type { RetrievalWorkspace } from "@/workspaces/retrieval-workspace";
import type { SynonymsWorkspace } from "@/workspaces/synonyms-workspace";

export type KbAppContextValue = {
  dashboardProps: ComponentProps<typeof DashboardWorkspace>;
  documentsProps: ComponentProps<typeof DocumentsWorkspace>;
  lookupProps: ComponentProps<typeof LookupWorkspace>;
  retrievalProps: ComponentProps<typeof RetrievalWorkspace>;
  synonymsProps: ComponentProps<typeof SynonymsWorkspace>;
};

const KbAppContext = createContext<KbAppContextValue | null>(null);

export const KbAppProvider = KbAppContext.Provider;

export function useKbApp() {
  const context = useContext(KbAppContext);
  if (!context) {
    throw new Error("useKbApp must be used inside KbAppProvider");
  }
  return context;
}
