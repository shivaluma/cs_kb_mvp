import {
  IconRobot as Bot,
  IconBoxMultiple as Boxes,
  IconFileText as FileText,
  IconFileUpload as FileUpload,
  IconFolderOpen as FolderOpen,
  IconGitBranch as GitBranch,
  IconGauge as Gauge,
  IconLayoutDashboard as LayoutDashboard,
  IconMessage as MessageSquareText,
  IconMessageReport as MessageReport,
  IconRoute as Route,
  IconSearch as Search,
  IconWand as WandSparkles,
  IconTool as Wrench
} from "@tabler/icons-react";

import type { FilterOption, FilterState, SynonymDraft, UploadState } from "@/types";
import { buildNavGroups, commandGroupSpecs, documentWorkflowStepIds, sidebarGroupSpecs } from "@/lib/navigation-model";

export const workspacePaths = {
  dashboard: "/",
  operations: "/operations",
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
    { label: "Document overviews", value: "full_sop" },
    { label: "Source evidence", value: "source_evidence" },
  ],
  taskType: [{ label: "All tasks", value: "all" }],
  vertical: [{ label: "All verticals", value: "all" }],
  category: [{ label: "All categories", value: "all" }],
};

export const navItems = [
  {
    id: "dashboard",
    path: workspacePaths.dashboard,
    label: "Portal",
    icon: FolderOpen,
    description: "Browse approved SOPs and jump into grounded answers.",
    section: "agent",
  },
  {
    id: "lookup",
    path: workspacePaths.lookup,
    label: "Lookup",
    icon: Search,
    description: "Search SOPs and approved document units by keyword or natural language.",
    section: "agent",
  },
  {
    id: "chat",
    path: workspacePaths.chat,
    label: "Chat",
    icon: MessageSquareText,
    description: "Ask a question. Answers come only from published, cited SOP sources.",
    section: "agent",
  },
  {
    id: "caseAssist",
    path: workspacePaths.caseAssist,
    label: "Case Assist",
    icon: Route,
    description: "Start from an issue. Get the matched rule, checklist, tools, and templates.",
    section: "agent",
  },
  {
    id: "collections",
    path: workspacePaths.collections,
    label: "Collections",
    icon: Boxes,
    description: "Manage curated operational packages with ownership, routing, tools, templates, risk, and relation gaps.",
    section: "library",
  },
  {
    id: "tools",
    path: workspacePaths.tools,
    label: "Tools",
    icon: Wrench,
    description: "Approved CS working links, systems, forms, and their SOP usage.",
    section: "library",
  },
  {
    id: "operations",
    path: workspacePaths.operations,
    label: "Ops console",
    icon: Gauge,
    description: "Triage workload, readiness, governance, and system health.",
    section: "ops",
  },
  {
    id: "documents",
    path: workspacePaths.documents,
    label: "Documents",
    icon: FileText,
    description: "Review extracted units, verify readiness, and publish approved source versions.",
    section: "ops",
  },
  {
    id: "documentUpload",
    path: workspacePaths.documentUpload,
    label: "Upload document",
    icon: FileUpload,
    description: "Add a source file or raw text draft for extraction.",
    section: "ops",
  },
  {
    id: "documentQueue",
    path: workspacePaths.documentQueue,
    label: "Document list",
    icon: LayoutDashboard,
    description: "Select active or archived sources for review.",
    section: "ops",
  },
  {
    id: "feedback",
    path: workspacePaths.feedback,
    label: "Feedback",
    icon: MessageReport,
    description: "Triage wrong, outdated, missing-step, macro, and search-quality reports.",
    section: "ops",
  },
  {
    id: "relations",
    path: workspacePaths.relations,
    label: "Relations",
    icon: GitBranch,
    description: "Resolve suggested and unresolved SOP dependencies before retrieval expands across documents.",
    section: "ops",
  },
  {
    id: "synonyms",
    path: workspacePaths.synonyms,
    label: "Synonyms",
    icon: WandSparkles,
    description: "Govern query expansion and Meilisearch relevance config.",
    section: "ai",
  },
  {
    id: "retrieval",
    path: workspacePaths.retrieval,
    label: "Retrieval lab",
    icon: Bot,
    description: "Debug hybrid retrieval, citations, and ranking signals.",
    section: "ai",
  },
] as const;

export const documentWorkflowItems = documentWorkflowStepIds.map((id) => navItems.find((item) => item.id === id)!);

export const sidebarNavGroups = buildNavGroups(navItems, sidebarGroupSpecs);
export const commandNavGroups = buildNavGroups(navItems, commandGroupSpecs);
export const navGroups = sidebarNavGroups;

export function pathForWorkspace(workspace: Workspace) {
  return workspacePaths[workspace];
}

export function workspaceFromPath(pathname: string): Workspace {
  if (pathname === workspacePaths.chat || pathname.startsWith(`${workspacePaths.chat}/`)) {
    return "chat";
  }
  if (pathname === "/search") {
    return "lookup";
  }
  if (pathname.startsWith("/sop/")) {
    return "lookup";
  }
  if (pathname.startsWith("/category/")) {
    return "dashboard";
  }
  const current = navItems.find((item) => item.path === pathname);
  return current?.id ?? "dashboard";
}
