import { Bot, FileText, LayoutDashboard, Search, WandSparkles } from "lucide-react";

import type { FilterState, SynonymDraft, UploadState } from "@/types";

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
  vertical: "food",
  category: "case_handling",
  audience: "customer",
  tags: "missing_item, refund",
  caseReasons: "CR_FOOD_MISSING_ITEM",
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
    label: "Dashboard",
    icon: LayoutDashboard,
    description: "Triage workload, readiness, and governance signals.",
  },
  {
    id: "lookup",
    label: "SOP Lookup",
    icon: Search,
    description: "Agent-facing SOP and approved document lookup.",
  },
  {
    id: "documents",
    label: "Documents",
    icon: FileText,
    description: "Upload, extract, review, publish, and archive source files.",
  },
  {
    id: "synonyms",
    label: "Synonyms",
    icon: WandSparkles,
    description: "Govern query expansion and Meilisearch relevance config.",
  },
  {
    id: "retrieval",
    label: "Retrieval Lab",
    icon: Bot,
    description: "Debug hybrid retrieval, citations, and ranking signals.",
  },
] as const;

export type Workspace = (typeof navItems)[number]["id"];
