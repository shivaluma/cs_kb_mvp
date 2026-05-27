import assert from "node:assert/strict";
import test from "node:test";

import { sourceSurfaceIntro, uploadMetadataDisclosureState } from "./source-workflow-ui.ts";
import type { UploadState } from "../types.ts";

test("source workflow intro copy avoids step-by-step process framing", () => {
  const uploadIntro = sourceSurfaceIntro("upload", { activeCount: 4, archivedCount: 2 });
  const queueIntro = sourceSurfaceIntro("queue", { activeCount: 4, archivedCount: 2 });

  assert.equal(uploadIntro.title, "New source");
  assert.equal(queueIntro.title, "Source queue");
  assert.ok(!uploadIntro.description.includes("Step"));
  assert.ok(!queueIntro.description.includes("Step"));
  assert.ok(queueIntro.description.includes("4 active"));
  assert.ok(queueIntro.description.includes("2 archived"));
});

test("upload routing details are optional until populated or suggested", () => {
  assert.deepEqual(uploadMetadataDisclosureState(uploadState()), {
    badge: "optional",
    label: "Routing details",
    open: false,
  });

  assert.deepEqual(uploadMetadataDisclosureState(uploadState({ category: "Refunds" })), {
    badge: "filled",
    label: "Routing details",
    open: false,
  });

  assert.deepEqual(uploadMetadataDisclosureState(uploadState({ suggestedCollectionSlug: "refund-ops" })), {
    badge: "AI suggestion",
    label: "Routing details",
    open: true,
  });
});

function uploadState(overrides: Partial<UploadState> = {}): UploadState {
  return {
    asyncExtraction: true,
    audience: "",
    caseReasons: "",
    category: "",
    collectionAssignmentStatus: "unassigned",
    collectionConfidence: 0,
    collectionName: "",
    collectionSlug: "",
    collectionSource: "",
    collectionType: "",
    externalId: "",
    file: null,
    lastReviewedAt: "",
    nextReviewDue: "",
    ownerTeam: "CS Ops",
    reviewFrequency: "",
    riskLevel: "",
    status: "draft",
    suggestedCollectionConfidence: 0,
    suggestedCollectionName: "",
    suggestedCollectionSlug: "",
    suggestedCollectionType: "",
    tags: "",
    title: "",
    vertical: "",
    ...overrides,
  };
}
