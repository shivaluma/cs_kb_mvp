import {
  IconRobot as Bot,
  IconBoxMultiple as Boxes,
  IconFileText as FileText,
  IconGitBranch as GitBranch,
  IconLayoutDashboard as LayoutDashboard,
  IconMessage as MessageSquareText,
  IconMessageReport as MessageReport,
  IconRoute as Route,
  IconSearch as Search,
  IconWand as WandSparkles,
  IconTool as Wrench
} from "@tabler/icons-react";

import type { FilterOption, FilterState, SynonymDraft, UploadState } from "@/types";

export const workspacePaths = {
  dashboard: "/",
  lookup: "/lookup",
  chat: "/chat",
  caseAssist: "/case-assist",
  issueRouter: "/issue-router",
  tools: "/tools",
  collections: "/collections",
  documents: "/documents",
  documentUpload: "/documents/upload",
  documentQueue: "/documents/queue",
  feedback: "/feedback",
  relations: "/relations",
  synonyms: "/synonyms",
  retrieval: "/retrieval",
} as const;

export type Workspace = keyof typeof workspacePaths;

export const defaultFilters: FilterState = {
  collection: "all",
  audience: "all",
  contentType: "all",
  taskType: "all",
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
  riskLevel: "",
  reviewFrequency: "",
  lastReviewedAt: "",
  nextReviewDue: "",
  collectionSlug: "",
  collectionName: "",
  collectionType: "",
  collectionAssignmentStatus: "unassigned",
  collectionSource: "",
  collectionConfidence: 0,
  suggestedCollectionSlug: "",
  suggestedCollectionName: "",
  suggestedCollectionType: "",
  suggestedCollectionConfidence: 0,
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

export const filterOptions: Record<Exclude<keyof FilterState, "collection">, FilterOption[]> = {
  audience: [{ label: "All audiences", value: "all" }],
  contentType: [
    { label: "All approved content", value: "all" },
    { label: "SOP rules", value: "sop_rules" },
    { label: "Issue router", value: "issue_router" },
    { label: "Tool links", value: "tool_link" },
    { label: "Action templates", value: "action_template" },
    { label: "Full SOP pages", value: "full_sop" },
  ],
  taskType: [{ label: "All tasks", value: "all" }],
  vertical: [{ label: "All verticals", value: "all" }],
  category: [{ label: "All categories", value: "all" }],
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
    id: "caseAssist",
    path: workspacePaths.caseAssist,
    label: "Case Assist",
    icon: Route,
    description: "Start from an issue and get the approved rule, checklist, tools, and action templates.",
  },
  {
    id: "tools",
    path: workspacePaths.tools,
    label: "Tool Directory",
    icon: Wrench,
    description: "Approved CS working links, systems, forms, and their SOP usage.",
  },
  {
    id: "collections",
    path: workspacePaths.collections,
    label: "Collections",
    icon: Boxes,
    description: "Operational groupings by audience, task, channel, owner, and risk.",
  },
  {
    id: "documents",
    path: workspacePaths.documents,
    label: "Document Review",
    icon: FileText,
    description: "Review extracted units, verify readiness, and publish approved source versions.",
  },
  {
    id: "documentUpload",
    path: workspacePaths.documentUpload,
    label: "Upload",
    icon: FileText,
    description: "Add one source file or raw text draft for extraction.",
  },
  {
    id: "documentQueue",
    path: workspacePaths.documentQueue,
    label: "Source Queue",
    icon: FileText,
    description: "Select active or archived sources for review.",
  },
  {
    id: "feedback",
    path: workspacePaths.feedback,
    label: "Feedback",
    icon: MessageReport,
    description: "Triage wrong, outdated, missing-step, macro, and search-quality reports.",
  },
  {
    id: "relations",
    path: workspacePaths.relations,
    label: "Relations",
    icon: GitBranch,
    description: "Resolve suggested and unresolved SOP dependencies before AI can expand across documents.",
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

export const navGroups = [
  {
    label: "Agent surfaces",
    items: navItems.filter((item) => ["dashboard", "lookup", "chat", "caseAssist", "tools", "collections"].includes(item.id)),
  },
  {
    label: "Review operations",
    items: navItems.filter((item) => ["documentUpload", "documentQueue", "documents", "feedback", "relations"].includes(item.id)),
  },
  {
    label: "Admin and debug",
    items: navItems.filter((item) => ["synonyms", "retrieval"].includes(item.id)),
  },
] as const;

export function pathForWorkspace(workspace: Workspace) {
  return workspacePaths[workspace];
}

export function workspaceFromPath(pathname: string): Workspace {
  if (pathname === workspacePaths.chat || pathname.startsWith(`${workspacePaths.chat}/`)) {
    return "chat";
  }
  const current = navItems.find((item) => item.path === pathname);
  return current?.id ?? "dashboard";
}
