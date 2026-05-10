import { Bot, FileText, LayoutDashboard, MessageSquareText, Search, WandSparkles } from "lucide-react";

import type { FilterState, SynonymDraft, UploadState } from "@/types";

export const workspacePaths = {
  dashboard: "/",
  lookup: "/lookup",
  chat: "/chat",
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
  asyncExtraction: true,
};

export const defaultSynonymDraft: SynonymDraft = {
  canonicalKey: "",
  synonymType: "one_way",
  status: "draft",
  domain: "",
  audience: "",
  terms: "",
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
    id: "chat",
    path: workspacePaths.chat,
    label: "SOP Chat",
    icon: MessageSquareText,
    description: "Grounded assistant that answers only from published curated SOP units.",
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
