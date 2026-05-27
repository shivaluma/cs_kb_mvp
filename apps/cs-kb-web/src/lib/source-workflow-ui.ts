import type { UploadState } from "../types.ts";

export type SourceSurface = "upload" | "queue";

export function sourceSurfaceIntro(
  surface: SourceSurface,
  {
    activeCount,
    archivedCount,
  }: {
    activeCount: number;
    archivedCount: number;
  },
) {
  if (surface === "upload") {
    return {
      title: "New source",
      description: "Upload a source as a draft. Extraction runs in the background, then reviewers publish it when ready.",
    };
  }

  return {
    title: "Source queue",
    description: `Choose a source to review. ${activeCount} active, ${archivedCount} archived.`,
  };
}

export function uploadMetadataDisclosureState(upload: UploadState) {
  const hasSuggestion = Boolean(upload.suggestedCollectionSlug);
  const hasManualRouting = [
    upload.vertical,
    upload.audience,
    upload.category,
    upload.ownerTeam && upload.ownerTeam !== "CS Ops" ? upload.ownerTeam : "",
    upload.collectionSlug,
    upload.riskLevel,
    upload.reviewFrequency,
    upload.lastReviewedAt,
    upload.nextReviewDue,
    upload.tags,
    upload.caseReasons,
  ].some((value) => String(value ?? "").trim().length > 0);

  return {
    badge: hasSuggestion ? "AI suggestion" : hasManualRouting ? "filled" : "optional",
    label: "Routing details",
    open: hasSuggestion,
  };
}
