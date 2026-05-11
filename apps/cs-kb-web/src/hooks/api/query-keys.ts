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
  versionRaw: (versionId: string) => ["ai-version-raw", versionId] as const,
  synonyms: (status: string) => ["search-synonyms", status] as const,
  suggestions: ["search-synonym-suggestions"] as const,
  search: (query: string, filters: FilterState) => ["search", query, filters] as const,
  retrieval: (query: string, mode: string, filters: FilterState) =>
    ["retrieval", query, mode, filters] as const,
};
