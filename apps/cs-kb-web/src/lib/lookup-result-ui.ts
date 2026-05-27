import { formatDate } from "./format.ts";
import type { SearchResult } from "../types.ts";

export function sopResultActionLabel() {
  return "Open in SOP";
}

export function sopResultFacts(item: SearchResult, options: { debug?: boolean } = {}) {
  const facts = [
    `v${item.version}`,
    item.category,
    item.vertical,
    item.updated_at ? `updated ${formatDate(item.updated_at)}` : "",
  ].filter(Boolean);

  if (!options.debug) {
    return facts;
  }

  return [
    ...facts,
    item.chunk_type ?? "",
    typeof item.score === "number" ? `score ${item.score.toFixed(4)}` : "",
  ].filter(Boolean);
}

export function sopResultMatchHint(item: SearchResult) {
  if (item.section_path?.length) {
    return `Matched ${item.section_path.join(" / ")}`;
  }
  if (item.chunk_type) {
    return `Matched ${humanizeChunkType(item.chunk_type)}`;
  }
  return "Matched published SOP text";
}

function humanizeChunkType(value: string) {
  return value.replace(/_/g, " ").trim() || "SOP text";
}
