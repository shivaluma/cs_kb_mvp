import type { DisplayBlock, DisplayContext, DisplayHighlight, RetrievalResult, SourceAnchor } from "@/types";

export type HighlightSegment = {
  text: string;
  highlighted: boolean;
  chunkIds: string[];
  strategy: string;
};

export type SourceDisplayMatch = {
  chunkId: string;
  title: string;
  sectionTitle: string;
  unitType: string;
  score: number;
  excerpt: string;
  result: RetrievalResult;
};

export type SourceDisplayGroup = {
  id: string;
  documentId: string;
  versionId: string;
  title: string;
  category: string;
  collections: string[];
  versionNumber: number;
  lastUpdated: string;
  publishedAt: string;
  effectiveDate: string;
  score: number;
  displayUnitType: string;
  content: string;
  blocks: DisplayBlock[];
  highlights: DisplayHighlight[];
  fallbackExcerpts: string[];
  matches: SourceDisplayMatch[];
  results: RetrievalResult[];
  sourceResolutionStatus: string;
  sourceResolutionReason: string;
};

type ResolvedRange = {
  start: number;
  end: number;
  chunkIds: string[];
  strategy: string;
};

export function groupResultsByDisplaySource(results: RetrievalResult[]): SourceDisplayGroup[] {
  const groups = new Map<string, SourceDisplayGroup>();
  for (const result of results) {
    const context = displayContextForResult(result);
    const documentId = context.document_id || result.document_id;
    const versionId = result.version_id;
    const sectionId = context.section_id || result.section_id || result.section || "source";
    const key = `${documentId}:${versionId}:${sectionId}`;
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, createSourceDisplayGroup(result, context));
      continue;
    }
    addResultToGroup(existing, result, context);
  }
  return [...groups.values()].sort((left, right) => right.score - left.score);
}

export function displayContextForResult(result: RetrievalResult): DisplayContext {
  const context = result.display_context;
  if (context?.content) {
    return context;
  }
  return {
    display_unit_type: "missing_source",
    document_id: result.document_id,
    document_title: result.document_title || result.title,
    section_id: result.section_id || result.section,
    section_title: result.section_title || result.heading || result.section,
    category: result.category || metadataText(result.metadata.category),
    collections: result.collections ?? [],
    version_number: result.version_number,
    last_updated: null,
    content: "Source section could not be loaded for this published result.",
    blocks: [],
    highlights: [],
    fallback_excerpt: "",
    highlight_failed: true,
    source_anchor: sourceAnchorForResult(result),
    source_resolution_status: "parent_missing",
    source_resolution_reason: "display_context_missing",
  };
}

export function highlightedSegments(content: string, highlights: DisplayHighlight[]): HighlightSegment[] {
  if (!content || !highlights.length) {
    return content ? [{ text: content, highlighted: false, chunkIds: [], strategy: "" }] : [];
  }
  const ranges = mergeRanges(
    highlights
      .map((highlight) => resolveHighlight(content, highlight))
      .filter((range): range is ResolvedRange => Boolean(range)),
  );
  if (!ranges.length) {
    return [{ text: content, highlighted: false, chunkIds: [], strategy: "" }];
  }

  const segments: HighlightSegment[] = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start > cursor) {
      segments.push({ text: content.slice(cursor, range.start), highlighted: false, chunkIds: [], strategy: "" });
    }
    segments.push({
      text: content.slice(range.start, range.end),
      highlighted: true,
      chunkIds: range.chunkIds,
      strategy: range.strategy,
    });
    cursor = range.end;
  }
  if (cursor < content.length) {
    segments.push({ text: content.slice(cursor), highlighted: false, chunkIds: [], strategy: "" });
  }
  return segments;
}

export function sourceDisplayLabel(displayUnitType: string) {
  if (displayUnitType === "source_document") return "Source document";
  if (displayUnitType === "source_section") return "Source section";
  if (displayUnitType === "table_section") return "Table section";
  if (displayUnitType === "section") return "SOP section";
  if (displayUnitType === "missing_source") return "Source unavailable";
  return "Source context";
}

function createSourceDisplayGroup(result: RetrievalResult, context: DisplayContext): SourceDisplayGroup {
  const highlights = normalizeHighlightsForResult(result, context);
  return {
    id: `${context.document_id || result.document_id}:${result.version_id}:${context.section_id || result.section_id || result.section}`,
    documentId: context.document_id || result.document_id,
    versionId: result.version_id,
    title: context.document_title || result.document_title || result.title,
    category: context.category || result.category || metadataText(result.metadata.category),
    collections: collectionNames(context, result),
    versionNumber: context.version_number ?? result.version_number,
    lastUpdated: context.last_updated ?? "",
    publishedAt: context.published_at ?? "",
    effectiveDate: context.effective_date ?? metadataText(result.metadata.effective_from) ?? "",
    score: result.score,
    displayUnitType: context.display_unit_type,
    content: context.content || result.content,
    blocks: context.blocks ?? [],
    highlights,
    fallbackExcerpts: fallbackExcerpt(context, result),
    matches: [matchFromResult(result, context)],
    results: [result],
    sourceResolutionStatus: context.source_resolution_status || "resolved",
    sourceResolutionReason: context.source_resolution_reason || "",
  };
}

function addResultToGroup(group: SourceDisplayGroup, result: RetrievalResult, context: DisplayContext) {
  group.score = Math.max(group.score, result.score);
  group.category ||= context.category || result.category || metadataText(result.metadata.category);
  group.collections = [...new Set([...group.collections, ...collectionNames(context, result)])];
  if (group.matches.length < 3) {
    group.matches.push(matchFromResult(result, context));
  }
  group.results.push(result);
  group.fallbackExcerpts.push(...fallbackExcerpt(context, result));

  const sameContent = context.content && context.content === group.content;
  if (sameContent) {
    if (group.highlights.length < 3) {
      group.highlights.push(...normalizeHighlightsForResult(result, context).slice(0, 3 - group.highlights.length));
    }
    group.blocks = mergeBlocks(group.blocks, context.blocks ?? []);
    return;
  }

  const separator = group.content ? "\n\n" : "";
  const heading = context.section_title && !context.content.startsWith(context.section_title)
    ? `${context.section_title}\n`
    : "";
  const offset = group.content.length + separator.length + heading.length;
  group.content = `${group.content}${separator}${heading}${context.content}`.trim();
  group.displayUnitType = "source_document";
  group.blocks = mergeBlocks(group.blocks, context.blocks ?? []);
  for (const highlight of normalizeHighlightsForResult(result, context).slice(0, Math.max(0, 3 - group.highlights.length))) {
    group.highlights.push(shiftHighlight(highlight, offset));
  }
}

function normalizeHighlightsForResult(result: RetrievalResult, context: DisplayContext): DisplayHighlight[] {
  const highlights = context.highlights?.length
    ? context.highlights
    : [
        {
          chunk_id: result.chunk_id,
          text: result.chunk_text || result.content,
          start_offset: result.highlight_start_offset ?? null,
          end_offset: result.highlight_end_offset ?? null,
          match_strategy: "client_fallback",
          source_anchor: sourceAnchorForResult(result),
        },
      ];
  return highlights.map((highlight) => ({
    ...highlight,
    chunk_id: highlight.chunk_id || result.chunk_id,
    text: highlight.text || result.chunk_text || result.content,
    source_anchor: highlight.source_anchor ?? sourceAnchorForResult(result),
  }));
}

function matchFromResult(result: RetrievalResult, context: DisplayContext): SourceDisplayMatch {
  return {
    chunkId: result.chunk_id,
    title: result.heading || context.section_title || result.title,
    sectionTitle: context.section_title || result.section_title || result.section,
    unitType: metadataText(result.metadata.unit_type) || result.section,
    score: result.score,
    excerpt: result.chunk_text || result.content,
    result,
  };
}

function collectionNames(context: DisplayContext, result: RetrievalResult) {
  const names = [
    ...(context.collections ?? []).map((collection) => collection.name || collection.id),
    ...(result.collections ?? []).map((collection) => collection.name || collection.id),
    metadataText(result.metadata.collection_name),
    metadataText(result.metadata.collection_slug),
  ];
  return names.map((item) => item.trim()).filter(Boolean);
}

function fallbackExcerpt(context: DisplayContext, result: RetrievalResult) {
  if (["parent_missing", "version_mismatch", "permission_denied"].includes(context.source_resolution_status || "")) {
    return [];
  }
  const excerpt = context.fallback_excerpt || (context.highlight_failed ? result.chunk_text || result.content : "");
  return excerpt ? [excerpt] : [];
}

function shiftHighlight(highlight: DisplayHighlight, offset: number): DisplayHighlight {
  return {
    ...highlight,
    start_offset: typeof highlight.start_offset === "number" ? highlight.start_offset + offset : highlight.start_offset,
    end_offset: typeof highlight.end_offset === "number" ? highlight.end_offset + offset : highlight.end_offset,
  };
}

function mergeBlocks(left: DisplayBlock[], right: DisplayBlock[]) {
  const blocks = [...left];
  const seen = new Set(blocks.map((block) => block.id || `${block.source_anchor?.table_id}:${block.source_anchor?.row_index}`));
  for (const block of right) {
    const key = block.id || `${block.source_anchor?.table_id}:${block.source_anchor?.row_index}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    blocks.push(block);
  }
  return blocks;
}

export function blockMatchesHighlight(block: DisplayBlock, highlights: DisplayHighlight[]) {
  return highlights.some((highlight) => anchorsMatch(block.source_anchor, highlight.source_anchor));
}

function anchorsMatch(blockAnchor?: SourceAnchor, highlightAnchor?: SourceAnchor) {
  if (!blockAnchor || !highlightAnchor) {
    return false;
  }
  if (highlightAnchor.table_id && blockAnchor.table_id === highlightAnchor.table_id) {
    if (highlightAnchor.row_index == null) {
      return true;
    }
    return blockAnchor.row_index === highlightAnchor.row_index;
  }
  if (highlightAnchor.block_id && blockAnchor.block_id === highlightAnchor.block_id) {
    return true;
  }
  return false;
}

function resolveHighlight(content: string, highlight: DisplayHighlight): ResolvedRange | null {
  if (highlight.match_strategy === "table_row_anchor") {
    return null;
  }
  const offsetRange = validOffsetRange(content, highlight.start_offset, highlight.end_offset);
  if (offsetRange) {
    return { ...offsetRange, chunkIds: [highlight.chunk_id], strategy: highlight.match_strategy || "offset" };
  }
  const textRange = findTextRange(content, highlight.text);
  if (textRange) {
    return { ...textRange, chunkIds: [highlight.chunk_id], strategy: textRange.strategy };
  }
  return null;
}

function sourceAnchorForResult(result: RetrievalResult): SourceAnchor {
  const metadataAnchor = typeof result.metadata.source_anchor === "object" && result.metadata.source_anchor
    ? result.metadata.source_anchor as SourceAnchor
    : {};
  return {
    sop_id: result.document_id,
    sop_version_id: result.version_id,
    section_id: result.section_id || metadataText(result.metadata.section_id) || result.section,
    block_id: result.display?.scroll_target?.block_id || metadataText(result.metadata.block_id) || result.chunk_id,
    table_id: metadataText(result.metadata.table_id),
    row_index: result.display?.scroll_target?.row_index ?? metadataNumber(result.metadata.row_index),
    column_key: metadataText(result.metadata.column_key),
    ...metadataAnchor,
    ...result.source_anchor,
  };
}

function validOffsetRange(content: string, start: number | null | undefined, end: number | null | undefined) {
  if (typeof start !== "number" || typeof end !== "number") {
    return null;
  }
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > content.length) {
    return null;
  }
  return { start, end };
}

export function findTextRange(content: string, needle: string): (ResolvedRange & { strategy: string }) | null {
  if (!content || !needle.trim()) {
    return null;
  }
  const exact = content.indexOf(needle);
  if (exact >= 0) {
    return { start: exact, end: exact + needle.length, chunkIds: [], strategy: "exact" };
  }
  const normalized = normalizedMatchRange(content, needle);
  if (normalized) {
    return { ...normalized, chunkIds: [], strategy: "normalized" };
  }
  const paragraph = paragraphMatchRange(content, needle);
  if (paragraph) {
    return { ...paragraph, chunkIds: [], strategy: "paragraph" };
  }
  return null;
}

function normalizedMatchRange(content: string, needle: string) {
  const source = normalizeWithMap(content);
  const target = normalizeWithMap(needle).text.trim();
  if (!source.text || !target) {
    return null;
  }
  const start = source.text.indexOf(target);
  if (start < 0) {
    return null;
  }
  const end = start + target.length;
  return {
    start: source.map[start],
    end: source.map[end - 1] + 1,
  };
}

function paragraphMatchRange(content: string, needle: string) {
  const targetTokens = new Set(normalizeForTokens(needle).split(" ").filter((token) => token.length > 2));
  if (!targetTokens.size) {
    return null;
  }
  const paragraphs = paragraphRanges(content);
  let best: { start: number; end: number; score: number } | null = null;
  for (const paragraph of paragraphs) {
    const paragraphTokens = new Set(normalizeForTokens(content.slice(paragraph.start, paragraph.end)).split(" "));
    const score = [...targetTokens].filter((token) => paragraphTokens.has(token)).length;
    if (!best || score > best.score) {
      best = { ...paragraph, score };
    }
  }
  const threshold = Math.min(5, Math.max(2, Math.ceil(targetTokens.size * 0.45)));
  return best && best.score >= threshold ? { start: best.start, end: best.end } : null;
}

function paragraphRanges(content: string) {
  const ranges: Array<{ start: number; end: number }> = [];
  const pattern = /\n\s*\n/g;
  let start = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(content))) {
    const end = match.index;
    if (content.slice(start, end).trim()) {
      ranges.push(trimRange(content, start, end));
    }
    start = pattern.lastIndex;
  }
  if (content.slice(start).trim()) {
    ranges.push(trimRange(content, start, content.length));
  }
  return ranges.length ? ranges : [{ start: 0, end: content.length }];
}

function trimRange(content: string, start: number, end: number) {
  while (start < end && /\s/.test(content[start])) start += 1;
  while (end > start && /\s/.test(content[end - 1])) end -= 1;
  return { start, end };
}

function normalizeWithMap(value: string) {
  const chars: string[] = [];
  const map: number[] = [];
  let lastSpace = false;
  for (let index = 0; index < value.length; index += 1) {
    const normalized = normalizeChar(value[index]);
    if (/^[a-z0-9]$/.test(normalized)) {
      chars.push(normalized);
      map.push(index);
      lastSpace = false;
    } else if ((/\s/.test(value[index]) || normalized === "") && chars.length && !lastSpace) {
      chars.push(" ");
      map.push(index);
      lastSpace = true;
    } else if (normalized === " " && chars.length && !lastSpace) {
      chars.push(" ");
      map.push(index);
      lastSpace = true;
    }
  }
  if (chars[chars.length - 1] === " ") {
    chars.pop();
    map.pop();
  }
  return { text: chars.join(""), map };
}

function normalizeForTokens(value: string) {
  return normalizeWithMap(value).text;
}

function normalizeChar(char: string) {
  const normalized = char.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
  if (/^[a-z0-9]$/.test(normalized)) {
    return normalized;
  }
  if (/\s/.test(char) || /[^\p{L}\p{N}]/u.test(char)) {
    return " ";
  }
  return "";
}

function mergeRanges(ranges: ResolvedRange[]) {
  const sorted = [...ranges].sort((left, right) => left.start - right.start || right.end - left.end);
  const merged: ResolvedRange[] = [];
  for (const range of sorted) {
    const previous = merged[merged.length - 1];
    if (!previous || range.start > previous.end) {
      merged.push({ ...range });
      continue;
    }
    previous.end = Math.max(previous.end, range.end);
    previous.chunkIds = [...new Set([...previous.chunkIds, ...range.chunkIds])];
    previous.strategy = previous.strategy === range.strategy ? previous.strategy : "merged";
  }
  return merged;
}

function metadataText(value: unknown) {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "";
}

function metadataNumber(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
