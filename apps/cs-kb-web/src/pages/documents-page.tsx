import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { RouteLoading } from "@/components/route-loading";
import { defaultUpload } from "@/constants";
import {
  useArchiveDocument,
  useBulkReviewVersion,
  useCreateExtractionUnit,
  useDeleteExtractionUnit,
  useDocumentChunks,
  useDocumentMetadataPreview,
  useDocuments,
  useDocumentVersions,
  useExtractionPipeline,
  useExtractionPipelineInspection,
  useExtractionUnits,
  usePublishReadiness,
  usePublishVersion,
  useRetryVersionIndexing,
  useUpdateExtractionUnit,
  useUploadDocument,
  useUploadDocumentAsync,
  useVersionRawText,
} from "@/hooks/api/documents";
import { useCollections } from "@/hooks/api/kb-index";
import { useUrlSearch } from "@/hooks/use-url-search";
import { fileExternalId, splitList } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { DocumentSummary, ExtractionUnit, ExtractionUnitCreate, ExtractionUnitUpdate, KBCollectionSummary, UploadState } from "@/types";

const DocumentsWorkspace = lazy(() =>
  import("@/workspaces/documents-workspace").then((module) => ({ default: module.DocumentsWorkspace })),
);

export function DocumentsPage() {
  const { getParam, setParams } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const [upload, setUpload] = useState<UploadState>(defaultUpload);
  const selectedDocumentId = getParam("document", "");
  const selectedChunkVersionId = getParam("version", "");
  const uploadTitlePrefill = getParam("upload_title", "");
  const relationPrefill = getParam("relation", "");
  const documentsQuery = useDocuments();
  const collectionsQuery = useCollections();
  const documents = useMemo(
    () =>
      [...(documentsQuery.data ?? [])].sort((left, right) => {
        if (left.status !== right.status) {
          return left.status === "active" ? -1 : 1;
        }
        return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      }),
    [documentsQuery.data],
  );
  const selectedDocument =
    documents.find((document) => document.document_id === selectedDocumentId) ??
    documents.find((document) => document.status === "active") ??
    documents[0] ??
    null;
  const effectiveVersionId = selectedChunkVersionId || selectedDocument?.latest_version_id || "";
  const versionsQuery = useDocumentVersions(selectedDocument?.document_id);
  const chunksQuery = useDocumentChunks(selectedDocument?.document_id, effectiveVersionId);
  const extractionUnitsQuery = useExtractionUnits(selectedDocument?.document_id, effectiveVersionId);
  const extractionPipelineQuery = useExtractionPipeline(effectiveVersionId);
  const extractionPipelineInspectionQuery = useExtractionPipelineInspection(effectiveVersionId);
  const publishReadinessQuery = usePublishReadiness(effectiveVersionId);
  const versionRawQuery = useVersionRawText(effectiveVersionId);
  const uploadMutation = useUploadDocument();
  const uploadAsyncMutation = useUploadDocumentAsync();
  const metadataPreviewMutation = useDocumentMetadataPreview();
  const publishMutation = usePublishVersion();
  const retryIndexingMutation = useRetryVersionIndexing();
  const bulkReviewMutation = useBulkReviewVersion();
  const createExtractionUnitMutation = useCreateExtractionUnit();
  const deleteExtractionUnitMutation = useDeleteExtractionUnit();
  const updateExtractionUnitMutation = useUpdateExtractionUnit();
  const archiveDocumentMutation = useArchiveDocument();

  useEffect(() => {
    if (!selectedDocument) {
      return;
    }
    const patch: Record<string, string> = {};
    if (!selectedDocumentId) {
      patch.document = selectedDocument.document_id;
    }
    if (!selectedChunkVersionId && selectedDocument.latest_version_id) {
      patch.version = selectedDocument.latest_version_id;
    }
    if (Object.keys(patch).length) {
      setParams(patch);
    }
  }, [selectedDocument, selectedDocumentId, selectedChunkVersionId, setParams]);

  useEffect(() => {
    if (!uploadTitlePrefill) {
      return;
    }
    setUpload((current) => ({
      ...current,
      externalId: current.externalId || fileExternalId(uploadTitlePrefill),
      title: current.title || uploadTitlePrefill,
    }));
  }, [uploadTitlePrefill]);

  function selectDocument(documentId: string) {
    const document = documents.find((item) => item.document_id === documentId);
    if (!document) {
      return;
    }
    setParams({
      document: document.document_id,
      version: document.latest_version_id ?? "",
      unit: "",
    });
  }

  function previewFileMetadata(file: File | null) {
    metadataPreviewMutation.reset();
    setUpload((current) => ({
      ...current,
      file,
      status: "draft",
      title: uploadTitlePrefill || "",
      externalId: uploadTitlePrefill ? fileExternalId(uploadTitlePrefill) : "",
      vertical: "",
      category: "",
      audience: "",
      tags: "",
      caseReasons: "",
      ownerTeam: current.ownerTeam || "CS Ops",
      riskLevel: current.riskLevel,
      reviewFrequency: current.reviewFrequency,
      lastReviewedAt: current.lastReviewedAt,
      nextReviewDue: current.nextReviewDue,
      collectionSlug: "",
      collectionName: "",
      collectionType: "",
      collectionAssignmentStatus: "unassigned",
      collectionSource: "",
      collectionConfidence: 0,
      suggestedCollectionSlug: "",
      suggestedCollectionName: "",
      suggestedCollectionType: "",
      suggestedCollectionConfidence: 0,
    }));
    if (!file) {
      return;
    }

    const form = new FormData();
    form.append("file", file);
    metadataPreviewMutation.mutate(form, {
      onSuccess: (preview) => {
        const metadata = preview.suggested_metadata;
        setUpload((current) => {
          if (current.file !== file) {
            return current;
          }
          return {
            ...current,
            title: current.title || preview.title || file.name,
            externalId: current.externalId || fileExternalId(file.name),
            vertical: metadata.vertical || current.vertical,
            category: metadata.category || current.category,
            audience: metadata.audience?.join(", ") || current.audience,
            tags: metadata.tags?.join(", ") || current.tags,
            caseReasons: metadata.case_reasons?.join(", ") || current.caseReasons,
            ownerTeam: metadata.owner_team || current.ownerTeam || "CS Ops",
            riskLevel: metadata.risk_level || current.riskLevel,
            reviewFrequency: metadata.review_frequency || current.reviewFrequency,
            lastReviewedAt: metadata.last_reviewed_at || current.lastReviewedAt,
            nextReviewDue: metadata.next_review_due || current.nextReviewDue,
            collectionSlug: "",
            collectionName: "",
            collectionType: "",
            collectionAssignmentStatus: metadata.suggested_collection_slug ? "suggested" : "unassigned",
            collectionSource: metadata.suggested_collection_slug ? "ai_suggested" : "",
            collectionConfidence: 0,
            suggestedCollectionSlug: metadata.suggested_collection_slug || "",
            suggestedCollectionName: metadata.suggested_collection_name || "",
            suggestedCollectionType: metadata.suggested_collection_type || "",
            suggestedCollectionConfidence: metadata.suggested_collection_confidence || 0,
            status: "draft",
          };
        });
        reportNotice(
          `Auto-filled metadata from ${preview.document_type}: ${preview.chunk_count} chunks, ${Math.round(preview.extraction_confidence * 100)}% confidence.`,
        );
      },
      onError: () => reportError("Could not auto-fill metadata. You can still enter the fields manually."),
    });
  }

  function handleUpload() {
    if (!upload.file) {
      reportError("Choose a TXT, MD, PDF, DOCX, Excel, or image file before uploading.");
      return;
    }
    const maxBytes = 15 * 1024 * 1024;
    const allowedExtensions = [".txt", ".md", ".markdown", ".pdf", ".docx", ".xlsx", ".xlsm", ".xls", ".png", ".jpg", ".jpeg", ".webp"];
    const lowerName = upload.file.name.toLowerCase();
    const validType = allowedExtensions.some((extension) => lowerName.endsWith(extension));
    if (!validType) {
      reportError("Unsupported file type. Use TXT, MD, PDF, DOCX, Excel, PNG, JPG, or WebP.");
      return;
    }
    if (upload.file.size > maxBytes) {
      reportError("File is too large for extraction. Keep uploads under 15MB.");
      return;
    }

    const form = new FormData();
    form.append("file", upload.file);
    form.append("external_id", upload.externalId || fileExternalId(upload.file.name));
    form.append("title", upload.title || upload.file.name);
    form.append("status", upload.status);
    form.append("created_by", "cs-ops-ui");
    form.append("change_summary", "Uploaded from CS KB web console");
    const approvedCollection =
      upload.collectionAssignmentStatus === "approved" && upload.collectionSlug
        ? {
            collection_slug: upload.collectionSlug,
            collection_name: upload.collectionName,
            collection_type: upload.collectionType,
            collection_assignment_status: "approved",
            collection_source: upload.collectionSource || "manual",
            collection_confidence: upload.collectionConfidence || 1,
          }
        : {};
    form.append(
      "metadata",
      JSON.stringify({
        audience: splitList(upload.audience),
        vertical: upload.vertical,
        category: upload.category,
        tags: splitList(upload.tags),
        case_reasons: splitList(upload.caseReasons),
        owner_team: upload.ownerTeam,
        risk_level: upload.riskLevel,
        review_frequency: upload.reviewFrequency,
        last_reviewed_at: upload.lastReviewedAt,
        next_review_due: upload.nextReviewDue,
        suggested_collection_slug: upload.suggestedCollectionSlug,
        suggested_collection_name: upload.suggestedCollectionName,
        suggested_collection_type: upload.suggestedCollectionType,
        suggested_collection_confidence: upload.suggestedCollectionConfidence,
        unresolved_relation_id: relationPrefill,
        source: "web_upload",
        ...approvedCollection,
      }),
    );

    const mutation = upload.asyncExtraction ? uploadAsyncMutation : uploadMutation;
    mutation.mutate(form, {
      onSuccess: (data) => {
        reportNotice(
          upload.asyncExtraction
            ? `Queued ${data.title} v${data.version_number} for background extraction. Refresh the source queue to see extracted units.`
            : `Uploaded ${data.title} v${data.version_number}, ${data.chunk_count} chunks extracted for review.`,
        );
        setUpload((current) => ({
          ...current,
          file: null,
          title: "",
          externalId: "",
          collectionSlug: "",
          collectionName: "",
          collectionType: "",
          collectionAssignmentStatus: "unassigned",
          collectionSource: "",
          collectionConfidence: 0,
          suggestedCollectionSlug: "",
          suggestedCollectionName: "",
          suggestedCollectionType: "",
          suggestedCollectionConfidence: 0,
        }));
      },
      onError: () => reportError("Upload failed. Confirm file type, size, and AI service health."),
    });
  }

  function publishVersion(versionId: string, force = false) {
    publishMutation.mutate(
      { versionId, actor: force ? "cs-lead-ui-force" : "cs-lead-ui", force },
      {
        onSuccess: () => {
          setParams({ version: versionId });
          reportNotice(
            force
              ? "Version force published for MVP testing. Indexing is being verified before agent visibility."
              : "Version published. Indexing is being verified before agent visibility.",
          );
        },
        onError: () =>
          reportError(
            force
              ? "Force publish failed. Confirm this is an editable draft version and retry."
              : "Publish blocked. Finish readiness checks first: full SOP, reviewed units, source refs, workflow graph, owner, effective date, and high-risk review SLA.",
          ),
      },
    );
  }

  function retryVersionIndexing(versionId: string) {
    retryIndexingMutation.mutate(
      { versionId, actor: "cs-ops-ui" },
      {
        onSuccess: () => reportNotice("Indexing retry started. Lookup and Chat will use this version after it reaches published_ready."),
        onError: () => reportError("Indexing retry failed. Check AI service, Meilisearch, and chunk availability."),
      },
    );
  }

  function bulkReviewVersion(versionId: string, scope: "all" | "atomic" = "all", reviewStatus: "reviewed" | "approved" = "reviewed", force = false) {
    if (force && reviewStatus === "approved") {
      const confirmed = window.confirm(
        scope === "atomic"
          ? "Approve all atomic units in this draft? Use this for test runs only after checking source quality."
          : "Approve all extraction units in this draft? Use this for test runs only after checking source quality.",
      );
      if (!confirmed) {
        return;
      }
    }
    bulkReviewMutation.mutate(
      { versionId, actor: "cs-ops-ui", reviewStatus, scope, force },
      {
        onSuccess: () => {
          setParams({ version: versionId });
          reportNotice(
            reviewStatus === "approved"
              ? scope === "atomic"
                ? "Atomic retrieval units approved. Review the full SOP page separately before publishing."
                : "Extraction units approved. Publish gate still validates source refs, owner, effective date, and graph requirements."
              : scope === "atomic"
                ? "Atomic retrieval units marked reviewed. Review the full SOP page separately before publishing."
                : "Extraction units marked reviewed. Lead can publish after the remaining readiness checks pass.",
          );
        },
        onError: () => reportError("Bulk review failed. Only editable draft versions can be reviewed."),
      },
    );
  }

  function updateExtractionUnit(unit: ExtractionUnit, update: ExtractionUnitUpdate) {
    updateExtractionUnitMutation.mutate(
      { unitId: unit.unit_id, update },
      {
        onSuccess: () => reportNotice(`Saved extraction unit ${unit.unit_index}. Retrieval embedding was refreshed.`),
        onError: () => reportError("Could not save this extraction unit. Published versions are immutable."),
      },
    );
  }

  async function applyCollectionToUnits(units: ExtractionUnit[], collection: KBCollectionSummary | null) {
    if (!units.length) {
      reportError("No extraction units available to assign.");
      return;
    }
    const metadataPatch = collection
      ? {
          collection_slug: collection.slug,
          collection_name: collection.name,
          collection_type: collection.collection_type,
          collection_assignment_status: "approved",
          collection_source: "manual_review",
          collection_confidence: 1,
        }
      : {
          collection_slug: "",
          collection_name: "",
          collection_type: "",
          collection_assignment_status: "unassigned",
          collection_source: "manual_review",
          collection_confidence: 0,
        };
    try {
      await Promise.all(
        units.map((unit) =>
          updateExtractionUnitMutation.mutateAsync({
            unitId: unit.unit_id,
            update: {
              title: unit.title,
              content: unit.content,
              unit_type: unit.unit_type,
              confidence: unit.confidence,
              review_status: unit.review_status,
              metadata: {
                ...unit.metadata,
                ...metadataPatch,
              },
              actor: "cs-ops-ui",
            },
          }),
        ),
      );
      reportNotice(collection ? `Assigned ${units.length} units to ${collection.name}.` : `Cleared collection from ${units.length} units.`);
    } catch {
      reportError("Could not assign collection. Only editable draft versions can be changed.");
    }
  }

  function createExtractionUnit(versionId: string, unit: ExtractionUnitCreate) {
    createExtractionUnitMutation.mutate(
      { versionId, unit },
      {
        onSuccess: () => reportNotice(`Created ${unit.unit_type} review stub. Fill it from source evidence before approval.`),
        onError: () => reportError("Could not create this workflow unit. Only editable draft versions can be changed."),
      },
    );
  }

  function deleteExtractionUnit(unit: ExtractionUnit) {
    deleteExtractionUnitMutation.mutate(
      { unitId: unit.unit_id, actor: "cs-ops-ui" },
      {
        onSuccess: () => reportNotice(`Deleted extraction unit ${unit.unit_index}.`),
        onError: () => reportError("Could not delete this extraction unit. Only editable draft versions can be changed."),
      },
    );
  }

  function archiveDocument(document: DocumentSummary) {
    const confirmed = window.confirm(`Archive "${document.title}"? It will be removed from active retrieval, Meilisearch, collection membership, and approved relation expansion.`);
    if (!confirmed) {
      return;
    }
    archiveDocumentMutation.mutate(
      { documentId: document.document_id, actor: "cs-ops-ui" },
      {
        onSuccess: () => {
          reportNotice(`Archived ${document.title}.`);
          setParams({ document: "", version: "", unit: "" });
        },
        onError: () => reportError("Archive failed. Check AI service and document state."),
      },
    );
  }

  const busyKey =
    metadataPreviewMutation.isPending ? "metadata-preview" :
    uploadMutation.isPending ? "upload" :
    uploadAsyncMutation.isPending ? "upload" :
    archiveDocumentMutation.isPending ? "archive-document" :
    publishMutation.isPending ? "publishing" :
    retryIndexingMutation.isPending ? "indexing" :
    bulkReviewMutation.isPending ? "bulk-review" :
    createExtractionUnitMutation.isPending ? "create-unit" :
    deleteExtractionUnitMutation.isPending ? "delete-unit" :
    "";

  return (
    <Suspense fallback={<RouteLoading label="Loading documents" />}>
      <DocumentsWorkspace
        busyKey={busyKey}
        chunks={chunksQuery.data ?? []}
        chunksLoading={chunksQuery.isFetching}
        collections={collectionsQuery.data ?? []}
        documents={documents}
        extractionUnits={extractionUnitsQuery.data ?? []}
        extractionUnitsLoading={extractionUnitsQuery.isFetching}
        extractionPipeline={extractionPipelineQuery.data ?? []}
        extractionPipelineInspection={extractionPipelineInspectionQuery.data ?? null}
        extractionPipelineLoading={extractionPipelineQuery.isFetching || extractionPipelineInspectionQuery.isFetching}
        metadataPreview={metadataPreviewMutation.data ?? null}
        onArchiveDocument={archiveDocument}
        onApplyCollection={applyCollectionToUnits}
        onBulkReviewVersion={bulkReviewVersion}
        onCreateExtractionUnit={createExtractionUnit}
        onDeleteExtractionUnit={deleteExtractionUnit}
        onFileSelected={previewFileMetadata}
        onInspectVersion={(versionId) => setParams({ version: versionId })}
        onPublishVersion={publishVersion}
        onRefreshDocuments={() => void documentsQuery.refetch()}
        onRetryIndexing={retryVersionIndexing}
        onSelectDocument={selectDocument}
        onUpdateExtractionUnit={updateExtractionUnit}
        onUpload={handleUpload}
        publishReadiness={publishReadinessQuery.data ?? null}
        publishReadinessLoading={publishReadinessQuery.isFetching}
        deletingUnitId={deleteExtractionUnitMutation.isPending ? deleteExtractionUnitMutation.variables?.unitId ?? "" : ""}
        savingUnitId={updateExtractionUnitMutation.isPending ? updateExtractionUnitMutation.variables?.unitId ?? "" : ""}
        selectedChunkVersionId={effectiveVersionId}
        selectedDocument={selectedDocument}
        setSelectedDocument={(document) => selectDocument(document.document_id)}
        setUpload={setUpload}
        upload={upload}
        versionRaw={versionRawQuery.data ?? null}
        versionRawLoading={versionRawQuery.isFetching}
        versions={versionsQuery.data ?? []}
      />
    </Suspense>
  );
}
