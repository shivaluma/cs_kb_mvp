import type { RetrievalResult, SourceAnchor } from "../types.ts";

export const SOP_SOURCE_STORAGE_KEY = "kb:selected-sop-source";

export type SopSourceLink = {
  sopId: string;
  search: {
    q?: string;
    source: string;
  };
};

export function buildSopSourceLink(match: RetrievalResult, query = ""): SopSourceLink | null {
  const sopId = sopIdForSourceMatch(match);
  if (!sopId || !match.chunk_id) {
    return null;
  }
  const trimmedQuery = query.trim();
  return {
    sopId,
    search: {
      ...(trimmedQuery ? { q: trimmedQuery } : {}),
      source: match.chunk_id,
    },
  };
}

export function sourceMatchBelongsToSop(
  match: RetrievalResult,
  target: { sourceChunkId: string; sopId: string },
) {
  if (!target.sourceChunkId || match.chunk_id !== target.sourceChunkId) {
    return false;
  }
  const sopId = sopIdForSourceMatch(match);
  return !sopId || sopId === target.sopId;
}

function sopIdForSourceMatch(match: RetrievalResult) {
  return (
    cleanText(match.sop_id) ||
    cleanText(match.source_anchor?.sop_id) ||
    cleanText(match.citation?.sop_id) ||
    cleanText(sourceAnchorFromMetadata(match.metadata)?.sop_id)
  );
}

function sourceAnchorFromMetadata(metadata: Record<string, unknown>): SourceAnchor | null {
  const value = metadata.source_anchor;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as SourceAnchor;
}

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}
