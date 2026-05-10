import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { RouteLoading } from "@/components/route-loading";
import { defaultUpload } from "@/constants";
import {
  useArchiveDocument,
  useBulkReviewVersion,
  useDocumentChunks,
  useDocumentMetadataPreview,
  useDocuments,
  useDocumentVersions,
  useExtractionUnits,
  usePublishVersion,
  useUpdateExtractionUnit,
  useUploadDocument,
  useVersionRawText,
} from "@/hooks/api/documents";
import { useUrlSearch } from "@/hooks/use-url-search";
import { fileExternalId, splitList } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { DocumentSummary, ExtractionUnit, ExtractionUnitUpdate, UploadState } from "@/types";

const DocumentsWorkspace = lazy(() =>
  import("@/workspaces/documents-workspace").then((module) => ({ default: module.DocumentsWorkspace })),
);

export function DocumentsPage() {
  const { getParam, setParams } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const [upload, setUpload] = useState<UploadState>(defaultUpload);
  const selectedDocumentId = getParam("document", "");
  const selectedChunkVersionId = getParam("version", "");
  const documentsQuery = useDocuments();
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
  const versionRawQuery = useVersionRawText(effectiveVersionId);
  const uploadMutation = useUploadDocument();
  const metadataPreviewMutation = useDocumentMetadataPreview();
  const publishMutation = usePublishVersion();
  const bulkReviewMutation = useBulkReviewVersion();
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
      title: "",
      externalId: "",
      vertical: "",
      category: "",
      audience: "",
      tags: "",
      caseReasons: "",
      ownerTeam: current.ownerTeam || "CS Ops",
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
            title: preview.title || current.title || file.name,
            externalId: current.externalId || fileExternalId(file.name),
            vertical: metadata.vertical || current.vertical,
            category: metadata.category || current.category,
            audience: metadata.audience?.join(", ") || current.audience,
            tags: metadata.tags?.join(", ") || current.tags,
            caseReasons: metadata.case_reasons?.join(", ") || current.caseReasons,
            ownerTeam: metadata.owner_team || current.ownerTeam || "CS Ops",
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
      reportError("File is too large for the demo pipeline. Keep uploads under 15MB.");
      return;
    }

    const form = new FormData();
    form.append("file", upload.file);
    form.append("external_id", upload.externalId || fileExternalId(upload.file.name));
    form.append("title", upload.title || upload.file.name);
    form.append("status", upload.status);
    form.append("created_by", "cs-ops-ui");
    form.append("change_summary", "Uploaded from CS KB web console");
    form.append(
      "metadata",
      JSON.stringify({
        audience: splitList(upload.audience),
        vertical: upload.vertical,
        category: upload.category,
        tags: splitList(upload.tags),
        case_reasons: splitList(upload.caseReasons),
        owner_team: upload.ownerTeam,
        source: "web_upload",
      }),
    );

    uploadMutation.mutate(form, {
      onSuccess: (data) => {
        reportNotice(`Uploaded ${data.title} v${data.version_number}, ${data.chunk_count} chunks extracted for review.`);
        setUpload((current) => ({ ...current, file: null, title: "", externalId: "" }));
      },
      onError: () => reportError("Upload failed. Confirm file type, size, and AI service health."),
    });
  }

  function publishVersion(versionId: string) {
    publishMutation.mutate(
      { versionId, actor: "cs-lead-ui" },
      {
        onSuccess: () => {
          setParams({ version: versionId });
          reportNotice("Version published. Previous published version was archived and Meilisearch was updated.");
        },
        onError: () =>
          reportError(
            "Publish blocked. Finish readiness checks first: full SOP, reviewed units, source refs, workflow graph, owner, effective date, and high-risk warnings.",
          ),
      },
    );
  }

  function bulkReviewVersion(versionId: string, scope: "all" | "atomic" = "all") {
    bulkReviewMutation.mutate(
      { versionId, actor: "cs-ops-ui", reviewStatus: "reviewed", scope },
      {
        onSuccess: () => {
          setParams({ version: versionId });
          reportNotice(
            scope === "atomic"
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

  function archiveDocument(document: DocumentSummary) {
    const confirmed = window.confirm(`Archive "${document.title}"? It will be removed from active retrieval and Meilisearch.`);
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
    archiveDocumentMutation.isPending ? "archive-document" :
    publishMutation.isPending ? "publishing" :
    bulkReviewMutation.isPending ? "bulk-review" :
    "";

  return (
    <Suspense fallback={<RouteLoading label="Loading documents" />}>
      <DocumentsWorkspace
        busyKey={busyKey}
        chunks={chunksQuery.data ?? []}
        chunksLoading={chunksQuery.isFetching}
        documents={documents}
        extractionUnits={extractionUnitsQuery.data ?? []}
        extractionUnitsLoading={extractionUnitsQuery.isFetching}
        metadataPreview={metadataPreviewMutation.data ?? null}
        onArchiveDocument={archiveDocument}
        onBulkReviewVersion={bulkReviewVersion}
        onFileSelected={previewFileMetadata}
        onInspectVersion={(versionId) => setParams({ version: versionId })}
        onPublishVersion={publishVersion}
        onRefreshDocuments={() => void documentsQuery.refetch()}
        onSelectDocument={selectDocument}
        onUpdateExtractionUnit={updateExtractionUnit}
        onUpload={handleUpload}
        savingUnitId={updateExtractionUnitMutation.variables?.unitId ?? ""}
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
