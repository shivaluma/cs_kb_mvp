import type { FilterState } from "@/types";

export const queryKeys = {
  homepage: ["homepage"] as const,
  systemHealth: ["system-health"] as const,
  documents: ["ai-documents"] as const,
  versions: (documentId: string) => ["ai-document-versions", documentId] as const,
  chunks: (documentId: string, versionId: string) =>
    ["ai-document-chunks", documentId, versionId] as const,
  extractionUnits: (documentId: string, versionId: string) =>
    ["ai-extraction-units", documentId, versionId] as const,
  extractionPipeline: (versionId: string) => ["ai-extraction-pipeline", versionId] as const,
  extractionPipelineInspection: (versionId: string) => ["ai-extraction-pipeline-inspection", versionId] as const,
  publishReadiness: (versionId: string) => ["ai-publish-readiness", versionId] as const,
  relations: (status: string) => ["ai-document-relations", status] as const,
  versionRaw: (versionId: string) => ["ai-version-raw", versionId] as const,
  synonyms: (status: string) => ["search-synonyms", status] as const,
  suggestions: ["search-synonym-suggestions"] as const,
  searchFilterOptions: ["search-filter-options"] as const,
  search: (query: string, filters: FilterState) => ["search", query, filters] as const,
  retrieval: (query: string, mode: string, filters: FilterState) =>
    ["retrieval", query, mode, filters] as const,
  collections: ["kb-collections"] as const,
  collection: (id: string) => ["kb-collection", id] as const,
  chatSessions: (status: string) => ["chat-sessions", status] as const,
  chatSessionMessages: (sessionId: string) => ["chat-session-messages", sessionId] as const,
  issueRouter: (params: Record<string, string>) => ["issue-router", params] as const,
  tools: (collection: string) => ["tool-links", collection] as const,
  actionTemplates: (collection: string) => ["action-templates", collection] as const,
};
