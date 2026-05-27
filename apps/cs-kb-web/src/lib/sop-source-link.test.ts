import assert from "node:assert/strict";
import test from "node:test";

import { buildSopSourceLink, sourceMatchBelongsToSop } from "./sop-source-link.ts";
import type { RetrievalResult } from "../types.ts";

test("build SOP source link from direct SOP id and query", () => {
  const match = retrievalResult({
    chunk_id: "chunk-1",
    sop_id: "sop-1",
    title: "Refund SOP",
  });

  assert.deepEqual(buildSopSourceLink(match, "refund after delivery"), {
    sopId: "sop-1",
    search: {
      q: "refund after delivery",
      source: "chunk-1",
    },
  });
});

test("build SOP source link from source anchor when result SOP id is absent", () => {
  const match = retrievalResult({
    chunk_id: "chunk-2",
    sop_id: "",
    title: "Appeals SOP",
    source_anchor: {
      sop_id: "sop-from-anchor",
      block_id: "block-7",
    },
  });

  assert.equal(buildSopSourceLink(match, "appeal")?.sopId, "sop-from-anchor");
});

test("source match hydration requires the stored chunk to belong to the open SOP", () => {
  const match = retrievalResult({
    chunk_id: "chunk-3",
    sop_id: "sop-current",
    title: "Refund SOP",
  });

  assert.equal(sourceMatchBelongsToSop(match, { sourceChunkId: "chunk-3", sopId: "sop-current" }), true);
  assert.equal(sourceMatchBelongsToSop(match, { sourceChunkId: "chunk-3", sopId: "other-sop" }), false);
  assert.equal(sourceMatchBelongsToSop(match, { sourceChunkId: "other-chunk", sopId: "sop-current" }), false);
});

function retrievalResult(overrides: Partial<RetrievalResult>): RetrievalResult {
  return {
    document_id: "doc-1",
    version_id: "version-1",
    chunk_id: "chunk-1",
    title: "SOP",
    source_filename: "source.docx",
    version_number: 1,
    chunk_index: 0,
    section: "Policy",
    heading: "Refund policy",
    content: "Refund after delivery is allowed when policy conditions are met.",
    score: 0.91,
    lexical_score: 0.8,
    vector_score: 0.7,
    rank_source: ["vector"],
    metadata: {},
    citation: {
      document_id: "doc-1",
      version_id: "version-1",
      chunk_id: "chunk-1",
      chunk_index: 0,
      section: "Policy",
      title: "SOP",
      version_number: 1,
      source_filename: "source.docx",
    },
    ...overrides,
  };
}
