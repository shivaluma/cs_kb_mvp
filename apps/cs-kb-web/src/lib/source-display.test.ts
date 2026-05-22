import assert from "node:assert/strict";
import test from "node:test";

import { blockMatchesHighlight, groupResultsByDisplaySource, highlightedSegments } from "./source-display.ts";
import type { RetrievalResult } from "../types.ts";

test("exact offset highlight splits the source content", () => {
  const content = "Before. Refund after delivery is allowed with lead approval. After.";
  const segments = highlightedSegments(content, [
    {
      chunk_id: "chunk-1",
      text: "Refund after delivery is allowed",
      start_offset: 8,
      end_offset: 40,
      match_strategy: "exact",
    },
  ]);

  assert.equal(segments.filter((segment) => segment.highlighted)[0]?.text, "Refund after delivery is allowed");
});

test("text-match fallback normalizes punctuation and line breaks", () => {
  const content = "Refund after delivery:\nonly allowed when the customer has proof.";
  const segments = highlightedSegments(content, [
    {
      chunk_id: "chunk-2",
      text: "Refund after delivery only allowed",
      start_offset: null,
      end_offset: null,
      match_strategy: "unmatched",
    },
  ]);

  assert.ok(segments.some((segment) => segment.highlighted && segment.text.includes("Refund after delivery")));
});

test("multiple chunks from the same SOP are grouped together", () => {
  const first = result("chunk-1", "Refund SOP", "Refund after delivery is allowed.", 0, 33);
  const second = result("chunk-2", "Refund SOP", "Lead approval is required.", 34, 60);

  const groups = groupResultsByDisplaySource([first, second]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].matches.length, 2);
  assert.deepEqual(groups[0].matches.map((match) => match.chunkId), ["chunk-1", "chunk-2"]);
});

test("missing section_id still produces a display group", () => {
  const item = result("chunk-3", "Refund SOP", "Refund after delivery is allowed.", 0, 33);
  delete (item as Partial<RetrievalResult>).section_id;
  item.display_context!.section_id = "";

  const groups = groupResultsByDisplaySource([item]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].matches[0].sectionTitle, "Refund policy");
});

test("failed highlight fallback keeps a relevant excerpt", () => {
  const item = result("chunk-4", "Refund SOP", "Missing text", null, null);
  item.display_context = {
    ...item.display_context!,
    content: "Parent source section without the exact retrieval text.",
    fallback_excerpt: "Missing text",
    highlight_failed: true,
    highlights: [{ chunk_id: "chunk-4", text: "Missing text", start_offset: null, end_offset: null, match_strategy: "unmatched" }],
  };

  const groups = groupResultsByDisplaySource([item]);

  assert.equal(groups[0].fallbackExcerpts[0], "Missing text");
});

test("table row chunks use structural row highlight anchors", () => {
  const item = result("chunk-table-2", "Refund SOP", "Action: refund", null, null);
  item.display_context = {
    ...item.display_context!,
    display_unit_type: "table_section",
    section_id: "refund-table",
    section_title: "Refund table",
    content: "Action rows",
    blocks: [
      tableBlock("row-1", 1, "Service: BF; Case: Delay; Action: Apology."),
      tableBlock("row-2", 2, "Service: BF; Case: Cancel; Action: Refund."),
    ],
    highlights: [
      {
        chunk_id: "chunk-table-2",
        text: "Action: refund",
        start_offset: null,
        end_offset: null,
        match_strategy: "table_row_anchor",
        source_anchor: { sop_id: "sop-1", sop_version_id: "version-1", section_id: "refund-table", table_id: "table_1", row_index: 2 },
      },
    ],
    highlight_failed: false,
  };

  const group = groupResultsByDisplaySource([item])[0];

  assert.equal(group.displayUnitType, "table_section");
  assert.equal(blockMatchesHighlight(group.blocks[0], group.highlights), false);
  assert.equal(blockMatchesHighlight(group.blocks[1], group.highlights), true);
});

test("table row fallback parses numeric row anchors from metadata strings", () => {
  const item = result("chunk-table-string", "Refund SOP", "Action: refund", null, null);
  item.metadata = { ...item.metadata, table_id: "table_1", row_index: "2" };
  item.source_anchor = undefined;
  item.display_context = {
    ...item.display_context!,
    display_unit_type: "table_section",
    section_id: "refund-table",
    blocks: [
      tableBlock("row-1", 1, "Service: BF; Case: Delay; Action: Apology."),
      tableBlock("row-2", 2, "Service: BF; Case: Cancel; Action: Refund."),
    ],
    highlights: [],
  };

  const group = groupResultsByDisplaySource([item])[0];

  assert.equal(blockMatchesHighlight(group.blocks[1], group.highlights), true);
});

test("same SOP results in different sections are not collapsed", () => {
  const first = result("chunk-a", "Refund SOP", "Refund after delivery is allowed.", 0, 33);
  const second = result("chunk-b", "Refund SOP", "Cancellation before pickup.", 0, 27);
  second.display_context = {
    ...second.display_context!,
    section_id: "cancel-policy",
    section_title: "Cancellation policy",
  };

  const groups = groupResultsByDisplaySource([first, second]);

  assert.equal(groups.length, 2);
});

test("workflow diagram chunks keep workflow display mode when grouped", () => {
  const first = workflowResult("workflow-branch-8-no", "Decision 8: No -> 8.2");
  const second = workflowResult("workflow-step-8-2", "8.2 Thông báo KH không cung cấp email");

  const group = groupResultsByDisplaySource([first, second])[0];

  assert.equal(group.displayUnitType, "workflow_diagram");
  assert.equal(group.matches.length, 2);
});

test("missing display context uses safe parent-missing fallback", () => {
  const item = result("chunk-unsafe", "Refund SOP", "Raw chunk text", null, null);
  item.display_context = null;

  const group = groupResultsByDisplaySource([item])[0];

  assert.equal(group.displayUnitType, "missing_source");
  assert.ok(!group.content.includes("Raw chunk text"));
});

function result(
  chunkId: string,
  title: string,
  chunkText: string,
  start: number | null,
  end: number | null,
): RetrievalResult {
  const content = "Refund after delivery is allowed. Lead approval is required.";
  return {
    document_id: "sop-1",
    version_id: "version-1",
    chunk_id: chunkId,
    title,
    source_filename: "refund.md",
    version_number: 3,
    chunk_index: 1,
    section: "policy_rule",
    heading: "Refund policy",
    content: chunkText,
    score: 0.87,
    lexical_score: 0.8,
    vector_score: 0.7,
    rank_source: ["lexical"],
    metadata: { unit_type: "policy_rule", collection_name: "Refund Ops" },
    citation: {
      document_id: "sop-1",
      version_id: "version-1",
      chunk_id: chunkId,
      chunk_index: 1,
      section: "policy_rule",
      title,
      version_number: 3,
      source_filename: "refund.md",
    },
    display_context: {
      display_unit_type: "source_section",
      document_id: "sop-1",
      document_title: title,
      section_id: "refund-policy",
      section_title: "Refund policy",
      category: "Refund",
      collections: [{ id: "refund", name: "Refund Ops" }],
      version_number: 3,
      last_updated: "2026-05-22T00:00:00Z",
      content,
      blocks: [{ id: "source-1", title: "Refund policy", content, unit_type: "source_evidence_section", chunk_id: "source-1", source_anchor: { sop_id: "sop-1", sop_version_id: "version-1", section_id: "refund-policy", block_id: "source-1" } }],
      highlights: [{ chunk_id: chunkId, text: chunkText, start_offset: start, end_offset: end, match_strategy: start === null ? "unmatched" : "exact", source_anchor: { sop_id: "sop-1", sop_version_id: "version-1", section_id: "refund-policy", block_id: "source-1" } }],
      fallback_excerpt: "",
      highlight_failed: start === null,
    },
  };
}

function workflowResult(chunkId: string, chunkText: string): RetrievalResult {
  const item = result(chunkId, "Inbound call workflow", chunkText, null, null);
  item.section = "decision_branch";
  item.metadata = {
    unit_type: "decision_branch",
    open_mode: "workflow_diagram",
    display_unit_type: "workflow_diagram",
    source_refs: [{ source_type: "pdf_diagram", page: 1, bbox: [100, 100, 200, 160], block_id: chunkId }],
  };
  item.display_context = {
    ...item.display_context!,
    display_unit_type: "workflow_diagram",
    section_id: "workflow_phase_open",
    section_title: "Open / Agent / Step 8",
    content: chunkText,
    blocks: [],
    highlights: [
      {
        chunk_id: chunkId,
        text: chunkText,
        start_offset: null,
        end_offset: null,
        match_strategy: "visual_bbox",
        source_anchor: { sop_id: "sop-1", sop_version_id: "version-1", section_id: "workflow_phase_open", block_id: chunkId },
      },
    ],
    highlight_failed: false,
  };
  return item;
}

function tableBlock(id: string, rowIndex: number, content: string) {
  return {
    id,
    title: `Row ${rowIndex}`,
    content,
    unit_type: "policy_rule",
    chunk_id: id,
    block_type: "table_row",
    source_anchor: { sop_id: "sop-1", sop_version_id: "version-1", section_id: "refund-table", table_id: "table_1", row_index: rowIndex },
  };
}
