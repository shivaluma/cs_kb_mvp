import { Bot, FileText, LayoutDashboard, Search, WandSparkles } from "lucide-react";

import type { FilterState, SynonymDraft, UploadState } from "@/types";

export const workspacePaths = {
  dashboard: "/",
  lookup: "/lookup",
  documents: "/documents",
  synonyms: "/synonyms",
  retrieval: "/retrieval",
} as const;

export type Workspace = keyof typeof workspacePaths;

export const defaultFilters: FilterState = {
  audience: "all",
  vertical: "all",
  category: "all",
};

export const defaultUpload: UploadState = {
  file: null,
  title: "",
  externalId: "",
  status: "draft",
  vertical: "",
  category: "",
  audience: "",
  tags: "",
  caseReasons: "",
  ownerTeam: "CS Ops",
};

export const defaultSynonymDraft: SynonymDraft = {
  canonicalKey: "missing_item",
  synonymType: "one_way",
  status: "draft",
  domain: "food",
  audience: "customer",
  terms: "khach khong nhan du mon, thieu topping",
};

export const filterOptions = {
  audience: ["customer", "driver", "merchant", "internal"],
  vertical: ["food", "payment", "safety", "delivery", "promotion"],
  category: ["case_handling", "verification", "escalation", "policy"],
};

export const navItems = [
  {
    id: "dashboard",
    path: workspacePaths.dashboard,
    label: "Dashboard",
    icon: LayoutDashboard,
    description: "Triage workload, readiness, and governance signals.",
  },
  {
    id: "lookup",
    path: workspacePaths.lookup,
    label: "SOP Lookup",
    icon: Search,
    description: "Agent-facing SOP and approved document lookup.",
  },
  {
    id: "documents",
    path: workspacePaths.documents,
    label: "Documents",
    icon: FileText,
    description: "Upload, extract, review, publish, and archive source files.",
  },
  {
    id: "synonyms",
    path: workspacePaths.synonyms,
    label: "Synonyms",
    icon: WandSparkles,
    description: "Govern query expansion and Meilisearch relevance config.",
  },
  {
    id: "retrieval",
    path: workspacePaths.retrieval,
    label: "Retrieval Lab",
    icon: Bot,
    description: "Debug hybrid retrieval, citations, and ranking signals.",
  },
] as const;

export function pathForWorkspace(workspace: Workspace) {
  return workspacePaths[workspace];
}

export function workspaceFromPath(pathname: string): Workspace {
  const current = navItems.find((item) => item.path === pathname);
  return current?.id ?? "dashboard";
}
