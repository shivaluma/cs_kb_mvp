import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Archive, BookOpen, CheckCircle2, ClipboardList, Database, FileText, GitBranch, History, Layers3, Loader2, MessageSquareText, Network, Plus, RefreshCw, Search, ShieldCheck, TriangleAlert, Upload, WandSparkles } from "lucide-react";

import { DraftRetrievalPreview, ExtractionPipelineTrace, PublishTaskList, SopQualityAuditPanel, buildPublishTasks, buildSopQualityAudit } from "@/components/documents-review-insights";
import { DocumentFact, ReadinessCheck } from "@/components/operations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyPanel, Field, StatusBadge } from "@/components/common";
import { ExtractionReviewEditor } from "@/components/extraction-review-editor";
import { API_BASE_URL } from "@/config";
import { workspacePaths } from "@/constants";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentChunk, DocumentMetadataPreview, DocumentSummary, ExtractionJobSummary, ExtractionUnit, ExtractionUnitCreate, ExtractionUnitUpdate, UploadState, VersionRawText, VersionSummary } from "@/types";

type WorkflowGraphMetadata = {
  workflow_id?: string;
  title?: string;
  start_node_id?: string;
  graph_confidence?: number;
  requires_human_review?: boolean;
  review_reason?: string;
  nodes?: Array<{ id?: string; type?: string; actor?: string; phase?: string; title?: string; question?: string }>;
  edges?: Array<{ from_node?: string; to_node?: string; condition?: string; review_reason?: string; review_status?: string }>;
  annotations?: Array<{ id?: string; type?: string; attached_to?: string; title?: string; content?: string; risk_level?: string }>;
  uncertain_edges?: Array<{ from_node?: string; to_node?: string; condition?: string; reason?: string; confidence?: number }>;
  validation_errors?: string[];
};
type WorkflowEdgeMetadata = NonNullable<WorkflowGraphMetadata["edges"]>[number];
type WorkflowNodeMetadata = NonNullable<WorkflowGraphMetadata["nodes"]>[number];
type WorkflowNodeKind = "decision" | "end" | "note" | "orderHistory" | "script" | "start" | "step";
type ReviewFilter = "needs_review" | "reviewed" | "approved" | "atomic" | "all";
type RequiredWorkflowUnit = {
  key: string;
  label: string;
  types: string[];
};
type WorkflowRequirementStatus = RequiredWorkflowUnit & {
  candidateUnits: ExtractionUnit[];
  matchingUnits: ExtractionUnit[];
  reviewedUnits: ExtractionUnit[];
  status: "missing" | "needs_review" | "ready";
};

export function DocumentsWorkspace({
  busyKey,
  chunks,
  chunksLoading,
  documents,
  extractionUnits,
  extractionUnitsLoading,
  extractionPipeline,
  extractionPipelineLoading,
  onArchiveDocument,
  onBulkReviewVersion,
  onCreateExtractionUnit,
  onInspectVersion,
  onFileSelected,
  onPublishVersion,
  onRefreshDocuments,
  onSelectDocument,
  onUpdateExtractionUnit,
  onUpload,
  metadataPreview,
  selectedDocument,
  selectedChunkVersionId,
  savingUnitId,
  setSelectedDocument,
  setUpload,
  upload,
  versionRaw,
  versionRawLoading,
  versions,
}: {
  busyKey: string;
  chunks: DocumentChunk[];
  chunksLoading: boolean;
  documents: DocumentSummary[];
  extractionUnits: ExtractionUnit[];
  extractionUnitsLoading: boolean;
  extractionPipeline: ExtractionJobSummary[];
  extractionPipelineLoading: boolean;
  onArchiveDocument: (document: DocumentSummary) => void;
  onBulkReviewVersion: (versionId: string, scope?: "all" | "atomic", reviewStatus?: "reviewed" | "approved", force?: boolean) => void;
  onCreateExtractionUnit: (versionId: string, unit: ExtractionUnitCreate) => void;
  onInspectVersion: (versionId: string) => void;
  onFileSelected: (file: File | null) => void;
  onPublishVersion: (versionId: string) => void;
  onRefreshDocuments: () => void;
  onSelectDocument: (documentId: string) => void;
  onUpload: () => void;
  metadataPreview: DocumentMetadataPreview | null;
  selectedDocument: DocumentSummary | null;
  selectedChunkVersionId: string;
  setSelectedDocument: (document: DocumentSummary) => void;
  setUpload: Dispatch<SetStateAction<UploadState>>;
  onUpdateExtractionUnit: (unit: ExtractionUnit, update: ExtractionUnitUpdate) => void;
  savingUnitId: string;
  upload: UploadState;
  versionRaw: VersionRawText | null;
  versionRawLoading: boolean;
  versions: VersionSummary[];
}) {
  const selectedFile = upload.file;
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const rawTextRef = useRef<HTMLTextAreaElement | null>(null);
  const reviewSectionRef = useRef<HTMLDivElement | null>(null);
  const maxBytes = 15 * 1024 * 1024;
  const maxChars = maxBytes;
  const allowedExtensions = [".txt", ".md", ".markdown", ".pdf", ".docx", ".xlsx", ".xlsm", ".xls", ".png", ".jpg", ".jpeg", ".webp"];
  const validType = selectedFile
    ? allowedExtensions.some((extension) => selectedFile.name.toLowerCase().endsWith(extension))
    : false;
  const validSize = selectedFile ? selectedFile.size <= maxBytes : false;
  const uploadReady = Boolean(selectedFile && validType && validSize);
  const uploadSteps = ["Upload", "Extract", "Chunk", "Embed", "Index"];
  const selectedVersion = versions.find((version) => version.version_id === selectedChunkVersionId);
  const selectedDocumentTitle = selectedDocument?.title || upload.title || "published SOP";
  const [sourceMode, setSourceMode] = useState<"file" | "text">("file");
  const [confirmingPublishVersionId, setConfirmingPublishVersionId] = useState("");
  const [rawTextError, setRawTextError] = useState("");
  const [rawTextName, setRawTextName] = useState("raw-sop-draft.md");
  const [rawTextStats, setRawTextStats] = useState({ bytes: 0, chars: 0, lines: 0 });
  const [sourceFilter, setSourceFilter] = useState<"active" | "archived" | "all">("active");
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("needs_review");
  const [requiredUnitFocus, setRequiredUnitFocus] = useState<RequiredWorkflowUnit | null>(null);
  const [draftPreviewQuery, setDraftPreviewQuery] = useState("");
  const activeDocuments = documents.filter((document) => document.status === "active");
  const archivedDocuments = documents.filter((document) => document.status === "archived");
  const visibleDocuments = documents.filter((document) => {
    if (sourceFilter === "all") {
      return true;
    }
    return document.status === sourceFilter;
  });
  const fullSopUnit = extractionUnits.find((unit) => isDocumentLayer(unit));
  const workflowGraphUnit = extractionUnits.find((unit) => unit.unit_type === "workflow_graph" || Boolean(unit.metadata.workflow_graph));
  const workflowGraph = workflowGraphUnit?.metadata.workflow_graph as WorkflowGraphMetadata | undefined;
  const workflowGraphValidationErrors = workflowGraph?.validation_errors ?? workflowGraphUnit?.metadata.graph_validation_errors ?? [];
  const workflowGraphUncertainEdges = workflowGraph?.uncertain_edges ?? workflowGraphUnit?.metadata.uncertain_edges ?? [];
  const workflowEdgeReviewSummary = buildWorkflowEdgeReviewSummary(workflowGraph, workflowGraphUnit);
  const workflowGraphWarningIssueCount =
    (Array.isArray(workflowGraphValidationErrors) ? workflowGraphValidationErrors.length : 0) +
    (Array.isArray(workflowGraphUncertainEdges) ? workflowGraphUncertainEdges.length : 0) +
    Number(workflowGraphUnit?.metadata.uncertain_edges_count ?? 0);
  const workflowGraphWarningsAcknowledged = workflowGraphWarningIssueCount === 0 || workflowGraphUnit?.metadata.graph_validation_acknowledged === true;
  const workflowGraphIssueCount = (workflowGraphWarningsAcknowledged ? 0 : workflowGraphWarningIssueCount) + workflowEdgeReviewSummary.blockingCount;
  const workflowGraphIssuesAcknowledged = workflowGraphIssueCount === 0;
  const atomicUnits = extractionUnits.filter((unit) => !isDocumentLayer(unit) && unit.unit_type !== "workflow_graph" && !unit.metadata.workflow_graph);
  const selectedIsArchived = selectedDocument?.status === "archived";
  const pendingReviewCount = extractionUnits.filter((unit) => unit.review_status === "needs_review").length;
  const pendingAtomicReviewCount = atomicUnits.filter((unit) => unit.review_status === "needs_review").length;
  const highRiskUnitCount = extractionUnits.filter(hasRiskSignal).length;
  const effectiveDateReviewed = extractionUnits.some(hasEffectiveDateSignal);
  const defaultEffectiveFrom = inferredEffectiveFrom(extractionUnits, selectedDocument, selectedVersion);
  const ownerAssigned = Boolean(selectedDocument?.metadata?.owner_team || selectedDocument?.metadata?.ownerTeam);
  const policyRequiresGovernance = ["policy_rule", "policy_table"].includes(String(selectedDocument?.latest_document_type ?? ""));
  const workflowRequiresGraph = selectedDocument?.latest_document_type === "workflow_diagram";
  const selectedExtractionIssue = extractionIssue(selectedDocument);
  const workflowGraphConfidence = Number(workflowGraphUnit?.metadata.graph_confidence ?? workflowGraph?.graph_confidence ?? workflowGraphUnit?.confidence ?? 0);
  const pageOnlySourceRefUnacknowledged = extractionUnits.filter(
    (unit) => unit.metadata.source_ref_quality === "page_only" && unit.metadata.source_ref_acknowledged !== true,
  ).length;
  const requiredWorkflowUnits = requiredUnitTypesFromExtraction(workflowGraphUnit, fullSopUnit);
  const missingWorkflowUnits = requiredWorkflowUnits.filter(
    (required) => !extractionUnits.some((unit) => required.types.includes(unit.unit_type) && unit.review_status !== "needs_review"),
  );
  const workflowRequirementStatuses = requiredWorkflowUnits.map((required) => {
    const matchingUnits = extractionUnits.filter((unit) => required.types.includes(unit.unit_type));
    const reviewedUnits = matchingUnits.filter((unit) => unit.review_status !== "needs_review");
    const status: WorkflowRequirementStatus["status"] = reviewedUnits.length ? "ready" : matchingUnits.length ? "needs_review" : "missing";
    return {
      ...required,
      candidateUnits: candidateUnitsForRequirement(required, atomicUnits),
      matchingUnits,
      reviewedUnits,
      status,
    };
  });
  const validationRuleCount = extractionUnits.filter((unit) => unit.unit_type === "validation_rule").length;
  const reviewStats = extractionUnits.reduce(
    (acc, unit) => {
      acc.total += 1;
      if (unit.review_status === "approved" || unit.review_status === "reviewed") {
        acc.reviewed += 1;
      }
      if (unit.unit_type === "security_note") {
        acc.security += 1;
      }
      return acc;
    },
    { reviewed: 0, security: 0, total: 0 },
  );
  const reviewFilterCounts: Record<ReviewFilter, number> = {
    needs_review: extractionUnits.filter((unit) => unit.review_status === "needs_review").length,
    reviewed: extractionUnits.filter((unit) => unit.review_status === "reviewed").length,
    approved: extractionUnits.filter((unit) => unit.review_status === "approved").length,
    atomic: atomicUnits.length,
    all: extractionUnits.length,
  };
  const readinessChecks = [
    {
      detail: fullSopUnit ? fullSopUnit.title : "Missing document-level layer",
      label: "Full SOP page",
      passed: Boolean(fullSopUnit),
    },
    {
      detail: atomicUnits.length ? `${atomicUnits.length} searchable units` : "No quick-answer units",
      label: "Atomic retrieval units",
      passed: atomicUnits.length > 0,
    },
    {
      detail: workflowGraphUnit
        ? workflowGraphIssuesAcknowledged
          ? `${workflowGraph?.nodes?.length ?? 0} nodes, ${workflowEdgeReviewSummary.reviewed}/${workflowEdgeReviewSummary.total} decision edges reviewed, ${Math.round(workflowGraphConfidence * 100)}% confidence`
          : `${workflowGraphIssueCount} topology or decision edge issue(s) need review`
        : "Workflow graph missing",
      label: "Workflow graph reviewed",
      passed: !workflowRequiresGraph || Boolean(workflowGraphUnit && workflowGraphUnit.review_status !== "needs_review" && workflowGraphConfidence >= 0.7 && (workflowGraph?.edges?.length ?? 0) > 0 && workflowGraphIssuesAcknowledged && workflowEdgeReviewSummary.blockingCount === 0),
    },
    {
      detail: pageOnlySourceRefUnacknowledged
        ? `${pageOnlySourceRefUnacknowledged} page-only source refs still need acknowledgement`
        : "Source refs reviewed or structured",
      label: "Source refs acknowledged",
      passed: !workflowRequiresGraph || pageOnlySourceRefUnacknowledged === 0,
    },
    {
      detail: !requiredWorkflowUnits.length
        ? "No AI-required unit types declared"
        : missingWorkflowUnits.length
          ? `Missing/review needed: ${missingWorkflowUnits.map((unit) => unit.label).join(", ")}`
          : "AI-required workflow units reviewed",
      label: "Required workflow units",
      passed: !requiredWorkflowUnits.length || missingWorkflowUnits.length === 0,
    },
    {
      detail: pendingReviewCount === 0 ? "No unit needs review" : `${pendingReviewCount} unit(s) still need review`,
      label: "Atomic units reviewed",
      passed: pendingReviewCount === 0,
    },
    {
      detail: highRiskUnitCount || validationRuleCount ? `${highRiskUnitCount} risk units, ${validationRuleCount} validation rules` : "No risk/validation metadata detected",
      label: "High-risk warning acknowledged",
      passed: !policyRequiresGovernance || highRiskUnitCount > 0 || validationRuleCount > 0,
    },
    {
      detail: effectiveDateReviewed ? "Effective date signal exists or is marked for review" : "No effective date signal found",
      label: "Effective date reviewed",
      passed: effectiveDateReviewed || !policyRequiresGovernance,
    },
    {
      detail: ownerAssigned ? String(selectedDocument?.metadata?.owner_team ?? selectedDocument?.metadata?.ownerTeam) : "Owner team missing",
      label: "Owner assigned",
      passed: ownerAssigned,
    },
    {
      detail: selectedVersion ? `${selectedVersion.status} v${selectedVersion.version_number}` : "Pick a version to inspect",
      label: "Selected version",
      passed: Boolean(selectedVersion),
    },
  ];
  const canEditSelectedVersion = Boolean(selectedDocument) && !selectedIsArchived && selectedVersion?.status !== "published";
  const readinessPassed = readinessChecks.every((check) => check.passed);
  const publishTasks = buildPublishTasks({
    missingWorkflowUnits,
    pageOnlySourceRefUnacknowledged,
    readinessChecks,
    selectedDocument,
    workflowGraphIssueCount,
    workflowGraphIssuesAcknowledged,
    workflowGraphUnit,
  });
  const sopQualityAudit = buildSopQualityAudit({
    atomicUnits,
    effectiveDateReviewed,
    fullSopUnit,
    highRiskUnitCount,
    missingWorkflowUnits,
    ownerAssigned,
    pageOnlySourceRefUnacknowledged,
    pendingReviewCount,
    policyRequiresGovernance,
    readinessChecks,
    selectedDocument,
    selectedVersion,
    validationRuleCount,
    workflowGraphIssueCount,
    workflowGraphIssuesAcknowledged,
    workflowGraphUnit,
    workflowRequiresGraph,
  });
  const bulkReviewBlocked =
    highRiskUnitCount > 0 ||
    selectedDocument?.latest_document_type === "workflow_diagram" ||
    Number(selectedVersion?.extraction_confidence ?? 1) < 0.85;
  const selectedVersionCanBulkReview = Boolean(selectedVersion) && canEditSelectedVersion && pendingReviewCount > 0 && !bulkReviewBlocked;
  const selectedVersionCanBulkReviewAtomic = Boolean(selectedVersion) && canEditSelectedVersion && pendingAtomicReviewCount > 0 && !bulkReviewBlocked;
  const filteredDocumentLayer = fullSopUnit && unitMatchesReviewFilter(fullSopUnit, reviewFilter, false) ? fullSopUnit : null;
  const filteredAtomicUnits = atomicUnits.filter((unit) => unitMatchesReviewFilter(unit, reviewFilter, true));
  const focusedRequiredUnits = requiredUnitFocus
    ? filteredAtomicUnits.filter((unit) => requiredUnitFocus.types.includes(unit.unit_type))
    : [];
  const filteredUnitsCount = (filteredDocumentLayer ? 1 : 0) + filteredAtomicUnits.length;
  const canBulkApproveVisible = Boolean(selectedVersion) && canEditSelectedVersion && filteredUnitsCount > 0;

  function focusReviewRequirement(requirement: RequiredWorkflowUnit) {
    setRequiredUnitFocus(requirement);
    setReviewFilter("needs_review");
    window.setTimeout(() => {
      reviewSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  }

  function refreshRawTextStats() {
    const text = rawTextRef.current?.value ?? "";
    setRawTextStats({
      bytes: new Blob([text]).size,
      chars: text.length,
      lines: text ? text.split(/\r\n|\r|\n/).length : 0,
    });
  }

  function stageRawText() {
    const text = rawTextRef.current?.value.trim() ?? "";
    const bytes = new Blob([text]).size;
    setRawTextError("");
    if (text.length < 20) {
      refreshRawTextStats();
      setRawTextError("Raw text needs at least 20 characters before staging.");
      return;
    }
    if (bytes > maxBytes) {
      refreshRawTextStats();
      setRawTextError("Raw text is over 15MB. Split it into smaller source documents.");
      return;
    }
    const filename = normalizedRawTextName(rawTextName);
    const file = new File([text], filename, { type: "text/markdown" });
    refreshRawTextStats();
    onFileSelected(file);
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(18rem,22rem)_minmax(0,1fr)]">
      <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>New source</CardTitle>
            <CardDescription>Upload as draft. Review and publish happen after extraction.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            <div className="grid grid-cols-2 gap-2 rounded-lg border bg-muted/15 p-1">
              <Button
                onClick={() => setSourceMode("file")}
                size="sm"
                type="button"
                variant={sourceMode === "file" ? "secondary" : "ghost"}
              >
                <Upload data-icon="inline-start" className="size-4" />
                File
              </Button>
              <Button
                onClick={() => setSourceMode("text")}
                size="sm"
                type="button"
                variant={sourceMode === "text" ? "secondary" : "ghost"}
              >
                <ClipboardList data-icon="inline-start" className="size-4" />
                Raw text
              </Button>
            </div>

            {sourceMode === "file" ? (
              <div className="grid gap-2">
                <label className="text-xs font-medium text-muted-foreground" htmlFor="document-file">Source file</label>
                <input
                  accept=".txt,.md,.markdown,.pdf,.docx,.xlsx,.xlsm,.xls,.png,.jpg,.jpeg,.webp"
                  className="sr-only"
                  id="document-file"
                  onChange={(event) => onFileSelected(event.target.files?.[0] ?? null)}
                  ref={fileInputRef}
                  type="file"
                />
                <Button
                  className="max-w-full min-w-0 justify-start overflow-hidden"
                  onClick={() => fileInputRef.current?.click()}
                  type="button"
                  variant="outline"
                >
                  <Upload data-icon="inline-start" className="size-4 shrink-0" />
                  <span className="min-w-0 flex-1 truncate text-left">{selectedFile ? selectedFile.name : "Choose source file"}</span>
                </Button>
                {selectedFile ? (
                  <div className="min-w-0 rounded-lg border bg-muted/25 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold">{selectedFile.name}</p>
                        <p className="mt-1 text-[11px] text-muted-foreground">{(selectedFile.size / 1024 / 1024).toFixed(2)}MB, max 15MB</p>
                      </div>
                      <Badge variant={uploadReady ? "secondary" : "destructive"}>{uploadReady ? "ready" : "blocked"}</Badge>
                    </div>
                    <div className="mt-3 grid gap-2">
                      <ValidationPill valid={validType} text="Supported type" />
                      <ValidationPill valid={validSize} text="Under 15MB" />
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="grid gap-3 rounded-xl border bg-muted/15 p-3">
                <div className="grid gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="raw-text-filename">Raw source filename</label>
                  <Input
                    id="raw-text-filename"
                    onChange={(event) => setRawTextName(event.target.value)}
                    placeholder="quy-dinh-xac-minh-email.md"
                    value={rawTextName}
                  />
                </div>
                <div className="grid gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="raw-text-source">Raw text</label>
                  <textarea
                    className="min-h-56 resize-y rounded-md border bg-background px-3 py-2 text-sm leading-6 shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                    defaultValue=""
                    id="raw-text-source"
                    onBlur={refreshRawTextStats}
                    placeholder="Paste SOP, policy note, email update, or OCR text here. The text is staged as a markdown file before extraction."
                    ref={rawTextRef}
                    spellCheck={false}
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                    <span>{rawTextStats.lines} lines, {rawTextStats.chars.toLocaleString()} chars, {(rawTextStats.bytes / 1024).toFixed(1)}KB</span>
                    <span>Stats update on blur or stage to avoid typing lag.</span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={stageRawText} size="sm" type="button" variant="secondary">
                    <WandSparkles data-icon="inline-start" className="size-4" />
                    Stage text source
                  </Button>
                  <Button onClick={refreshRawTextStats} size="sm" type="button" variant="outline">
                    Refresh stats
                  </Button>
                  <Badge variant={rawTextStats.bytes > maxBytes || rawTextStats.chars > maxChars ? "destructive" : "outline"}>
                    max 15MB
                  </Badge>
                </div>
                {rawTextError ? (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                    {rawTextError}
                  </div>
                ) : null}
                {selectedFile && selectedFile.type === "text/markdown" ? (
                  <div className="rounded-lg border bg-background p-3 text-xs">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-semibold">{selectedFile.name}</p>
                        <p className="mt-1 text-muted-foreground">Staged raw text source, ready for metadata preview and upload.</p>
                      </div>
                      <Badge variant={uploadReady ? "secondary" : "destructive"}>{uploadReady ? "ready" : "blocked"}</Badge>
                    </div>
                  </div>
                ) : null}
              </div>
            )}

            {busyKey === "metadata-preview" ? (
              <div className="rounded-xl border bg-muted/25 p-3 text-xs">
                <div className="flex items-center gap-2 font-medium">
                  <Loader2 className="size-4 animate-spin" />
                  Auto-filling taxonomy from the selected file
                </div>
                <p className="mt-1 text-muted-foreground">Reading text, tables, document type, and metadata signals before upload.</p>
              </div>
            ) : metadataPreview ? (
              <div className="rounded-xl border bg-muted/25 p-3 text-xs">
                <div className="flex items-center gap-2 font-medium">
                  <WandSparkles className="size-4" />
                  Metadata preview applied
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge variant="outline">{metadataPreview.document_type}</Badge>
                  <Badge variant="outline">{metadataPreview.chunk_count} chunks</Badge>
                  <Badge variant="outline">{Math.round(metadataPreview.extraction_confidence * 100)}% confidence</Badge>
                </div>
                {metadataPreview.warnings.length > 0 ? (
                  <p className="mt-2 text-muted-foreground">{metadataPreview.warnings.slice(0, 2).join(", ")}</p>
                ) : null}
              </div>
            ) : null}

            <Field label="Title" value={upload.title} onChange={(title) => setUpload((current) => ({ ...current, title }))} placeholder="Quy định xác minh tài khoản" />
            <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
              <Field label="Vertical" value={upload.vertical} onChange={(vertical) => setUpload((current) => ({ ...current, vertical }))} />
              <Field label="Audience" value={upload.audience} onChange={(audience) => setUpload((current) => ({ ...current, audience }))} placeholder="customer, driver" />
              <Field label="Category" value={upload.category} onChange={(category) => setUpload((current) => ({ ...current, category }))} />
              <Field label="Owner team" value={upload.ownerTeam} onChange={(ownerTeam) => setUpload((current) => ({ ...current, ownerTeam }))} />
            </div>
            <Field label="Tags" value={upload.tags} onChange={(tags) => setUpload((current) => ({ ...current, tags }))} />
            <Field label="Case reasons" value={upload.caseReasons} onChange={(caseReasons) => setUpload((current) => ({ ...current, caseReasons }))} />

            <label className="flex items-start gap-3 rounded-lg border bg-muted/20 p-3 text-xs leading-5">
              <input
                checked={upload.asyncExtraction}
                className="mt-0.5 size-4 rounded border-input"
                onChange={(event) => setUpload((current) => ({ ...current, asyncExtraction: event.target.checked }))}
                type="checkbox"
              />
              <span>
                <span className="block font-medium text-foreground">Extract in background</span>
                <span className="text-muted-foreground">Recommended for PDFs, diagrams, and large Excel files. Upload returns fast, then the extraction worker fills units for review.</span>
              </span>
            </label>

            {busyKey === "upload" ? (
              <div className="rounded-xl border bg-muted/25 p-3">
                <div className="mb-2 flex items-center justify-between text-xs font-medium">
                  <span>Extraction pipeline</span>
                  <span>running</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div className="h-full w-2/3 animate-pulse rounded-full bg-primary" />
                </div>
                <div className="mt-3 grid grid-cols-5 gap-1 text-center text-[10px] text-muted-foreground">
                  {uploadSteps.map((step) => <span key={step}>{step}</span>)}
                </div>
              </div>
            ) : null}

            <Button className="w-full justify-center" disabled={busyKey === "upload" || busyKey === "metadata-preview" || !uploadReady} onClick={onUpload} type="button">
              {busyKey === "upload" ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Upload data-icon="inline-start" className="size-4" />}
              Upload draft
            </Button>
            <div className="rounded-lg border bg-muted/25 p-3 text-xs leading-5 text-muted-foreground">
              <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
                <ShieldCheck className="size-4" />
                Curation gate
              </div>
              Draft extraction is editable. Lookup and AI answers only use published versions.
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <CardTitle>Source queue</CardTitle>
                <CardDescription>{activeDocuments.length} active, {archivedDocuments.length} archived</CardDescription>
              </div>
              <Button onClick={onRefreshDocuments} size="icon" type="button" variant="ghost">
                <RefreshCw className="size-4" />
              </Button>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-1 rounded-lg border bg-muted/15 p-1">
              {(["active", "archived", "all"] as const).map((filter) => (
                <Button
                  key={filter}
                  onClick={() => setSourceFilter(filter)}
                  size="sm"
                  type="button"
                  variant={sourceFilter === filter ? "secondary" : "ghost"}
                >
                  {filter === "active" ? "Active" : filter === "archived" ? "Archived" : "All"}
                </Button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <ScrollArea className="h-[22rem] pr-3">
              <div className="divide-y">
                {documents.length === 0 ? (
                  <EmptyPanel icon={FileText} title="No documents" text="Upload a source document to create the first draft." compact />
                ) : visibleDocuments.length === 0 ? (
                  <EmptyPanel
                    icon={Archive}
                    title={sourceFilter === "archived" ? "No archived sources" : "No active sources"}
                    text={sourceFilter === "archived" ? "Archived sources will appear here for audit." : "Switch to Archived or All to inspect historical sources."}
                    compact
                  />
                ) : (
                  visibleDocuments.map((document) => (
                    <button
                      className={cn(
                        "grid w-full gap-2 rounded-lg px-2 py-3 text-left transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                        selectedDocument?.document_id === document.document_id && "bg-muted/45",
                        document.status === "archived" && "bg-muted/20 text-muted-foreground hover:bg-muted/30",
                      )}
                      data-testid={`document-row-${document.document_id}`}
                      key={document.document_id}
                      onClick={() => {
                        setSelectedDocument(document);
                        onInspectVersion(document.latest_version_id ?? "");
                        onSelectDocument(document.document_id);
                      }}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="min-w-0 text-sm font-medium leading-5">{document.title}</h3>
                        <div className="flex shrink-0 items-center gap-1.5">
                          {document.status === "archived" ? <Badge variant="outline">Archived</Badge> : null}
                          <Badge variant="outline">v{document.latest_version_number ?? "-"}</Badge>
                        </div>
                      </div>
                      <p className="truncate text-xs text-muted-foreground">{document.source_filename}</p>
                        <div className="flex flex-wrap gap-2">
                          <StatusBadge status={document.latest_review_status ?? "needs_review"} />
                          <Badge variant="outline">{document.latest_document_type ?? "unknown"}</Badge>
                          {extractionIssue(document) ? <Badge variant="destructive">extraction failed</Badge> : null}
                          {document.status === "archived" ? <Badge variant="outline">lookup excluded</Badge> : null}
                        </div>
                    </button>
                  ))
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </aside>

      <section className="min-w-0 space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <CardTitle>{selectedDocument?.title ?? "Select a source document"}</CardTitle>
                <CardDescription className="mt-1 truncate">
                  {selectedDocument?.source_filename ?? "Choose from the source queue to review versions, extraction units, and indexed chunks."}
                </CardDescription>
              </div>
              {selectedDocument ? (
                <div className="flex flex-wrap gap-2">
                  <Badge variant={selectedIsArchived ? "outline" : "secondary"}>
                    {selectedIsArchived ? "archived source" : "active source"}
                  </Badge>
                  <Badge variant="outline">{selectedDocument.latest_document_type ?? "unknown type"}</Badge>
                  <Button
                    disabled={busyKey === "archive-document" || selectedIsArchived}
                    onClick={() => onArchiveDocument(selectedDocument)}
                    size="sm"
                    type="button"
                    variant="outline"
                  >
                    {busyKey === "archive-document" ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Archive data-icon="inline-start" className="size-4" />}
                    {selectedIsArchived ? "Archived" : "Archive"}
                  </Button>
                </div>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            {selectedIsArchived ? (
              <div className="mb-4 rounded-xl border bg-muted/20 p-3">
                <div className="flex items-start gap-3">
                  <Archive className="mt-0.5 size-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">Archived source, audit only</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      This document is hidden from active lookup and AI answers. You can inspect versions, raw extraction, and chunks for traceability.
                    </p>
                  </div>
                </div>
              </div>
            ) : null}
            {selectedExtractionIssue ? (
              <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/10 p-3">
                <div className="flex items-start gap-3">
                  <TriangleAlert className="mt-0.5 size-4 text-destructive" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-destructive">Extraction failed, source evidence saved</p>
                    <p className="mt-1 break-words text-xs leading-5 text-destructive/90">{selectedExtractionIssue.reason}</p>
                    {selectedExtractionIssue.warnings.length ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {selectedExtractionIssue.warnings.slice(0, 4).map((warning) => (
                          <Badge className="max-w-full truncate" key={warning} variant="outline">{warning}</Badge>
                        ))}
                      </div>
                    ) : null}
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      Review can continue from raw extracted text, but publish is blocked until structured AI extraction succeeds.
                    </p>
                  </div>
                </div>
              </div>
            ) : null}
            <div className="grid gap-3 md:grid-cols-4">
              <DocumentFact label="State" value={selectedIsArchived ? "Archived" : selectedDocument ? "Active" : "-"} />
              <DocumentFact label="Version" value={selectedDocument?.latest_version_number ? `v${selectedDocument.latest_version_number}` : "-"} />
              <DocumentFact label="Confidence" value={selectedDocument?.latest_extraction_confidence ? `${Math.round(selectedDocument.latest_extraction_confidence * 100)}%` : "-"} />
              <DocumentFact label="Layers" value={extractionUnits.length ? `1 page + ${atomicUnits.length} units` : "-"} />
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Publish readiness</CardTitle>
                <CardDescription>
                  {selectedIsArchived
                    ? "Archived sources are preserved for audit and cannot be published."
                    : "Operational gate before locking a version and syncing retrieval indexes."}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={readinessPassed ? "secondary" : "outline"}>
                  {selectedIsArchived ? "audit only" : `${readinessChecks.filter((check) => check.passed).length}/${readinessChecks.length} ready`}
                </Badge>
                {selectedVersionCanBulkReviewAtomic && selectedVersion ? (
                  <Button
                    className="h-8 px-3"
                    disabled={busyKey === "bulk-review"}
                    onClick={() => onBulkReviewVersion(selectedVersion.version_id, "atomic")}
                    size="sm"
                    type="button"
                    variant="outline"
                  >
                    {busyKey === "bulk-review" ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <ShieldCheck data-icon="inline-start" className="size-3.5" />}
                    Approve all atomic units
                  </Button>
                ) : null}
                {selectedVersion && canEditSelectedVersion ? (
                  <Button
                    className="h-8 px-3"
                    disabled={busyKey === "bulk-review" || extractionUnits.length === 0}
                    onClick={() => onBulkReviewVersion(selectedVersion.version_id, "all", "approved", true)}
                    size="sm"
                    type="button"
                    variant="outline"
                  >
                    {busyKey === "bulk-review" ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <CheckCircle2 data-icon="inline-start" className="size-3.5" />}
                    Approve all
                  </Button>
                ) : null}
                {selectedVersionCanBulkReview && selectedVersion ? (
                  <Button
                    className="h-8 px-3"
                    disabled={busyKey === "bulk-review"}
                    onClick={() => onBulkReviewVersion(selectedVersion.version_id, "all")}
                    size="sm"
                    type="button"
                    variant="ghost"
                  >
                    Mark all reviewed
                  </Button>
                ) : null}
                {canEditSelectedVersion && pendingReviewCount > 0 && bulkReviewBlocked ? (
                  <Badge variant="outline">bulk review blocked</Badge>
                ) : null}
              </div>
            </div>
          </CardHeader>
          <CardContent className="grid gap-2 pt-4 md:grid-cols-2 xl:grid-cols-5">
            {readinessChecks.map((check) => (
              <ReadinessCheck detail={check.detail} key={check.label} label={check.label} passed={check.passed} />
            ))}
          </CardContent>
        </Card>

        <PublishTaskList tasks={publishTasks} ready={readinessPassed && !selectedIsArchived} />

        <ExtractionPipelineTrace jobs={extractionPipeline} loading={extractionPipelineLoading} />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <SopQualityAuditPanel audit={sopQualityAudit} />
          <DraftRetrievalPreview
            query={draftPreviewQuery}
            selectedDocument={selectedDocument}
            setQuery={setDraftPreviewQuery}
            units={[fullSopUnit, ...atomicUnits].filter(Boolean) as ExtractionUnit[]}
          />
        </div>

        {requiredWorkflowUnits.length ? (
          <WorkflowRequirementsPanel
            busy={busyKey === "create-unit"}
            canEdit={canEditSelectedVersion}
            defaultEffectiveFrom={defaultEffectiveFrom}
            onCreate={(requirement) => {
              if (!selectedVersion) {
                return;
              }
              onCreateExtractionUnit(selectedVersion.version_id, buildWorkflowRequirementStub(requirement, selectedDocument, selectedVersion, defaultEffectiveFrom));
              focusReviewRequirement(requirement);
            }}
            onConvertCandidate={(unit, requirement) => {
              onUpdateExtractionUnit(unit, buildWorkflowRequirementConversion(unit, requirement, defaultEffectiveFrom));
              focusReviewRequirement(requirement);
            }}
            onReviewExisting={focusReviewRequirement}
            requirements={workflowRequirementStatuses}
          />
        ) : null}

        {workflowRequiresGraph ? (
          <WorkflowGraphPanel
            canEdit={canEditSelectedVersion}
            graph={workflowGraph}
            graphUnit={workflowGraphUnit}
            confidence={workflowGraphConfidence}
            onAcknowledge={(unit, reason) => onUpdateExtractionUnit(unit, buildWorkflowGraphAcknowledgement(unit, reason))}
            onReviewEdge={(unit, edge, status, reason) => onUpdateExtractionUnit(unit, buildWorkflowEdgeReviewUpdate(unit, edge, status, reason))}
            saving={savingUnitId === workflowGraphUnit?.unit_id}
          />
        ) : null}

        <Card className="rounded-xl" ref={reviewSectionRef}>
          <CardHeader className="border-b pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Full SOP page</CardTitle>
                <CardDescription>Document-level layer for reading, training, and audit. Atomic units remain below for retrieval.</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">document layer</Badge>
                <Badge variant="outline">{atomicUnits.length} atomic units</Badge>
                {validationRuleCount ? <Badge variant="outline">{validationRuleCount} validation rules</Badge> : null}
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            {!selectedDocument ? (
              <EmptyPanel icon={BookOpen} title="Select a document" text="Choose a source document to preview the composed SOP page." compact />
            ) : extractionUnitsLoading ? (
              <div className="flex items-center gap-2 rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading SOP page
              </div>
            ) : fullSopUnit ? (
              <article className="rounded-xl border bg-muted/20 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{fullSopUnit.unit_type}</Badge>
                  <StatusBadge status={fullSopUnit.review_status} />
                </div>
                <h3 className="mt-3 text-base font-semibold">{fullSopUnit.title}</h3>
                <p className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{fullSopUnit.content}</p>
              </article>
            ) : (
              <EmptyPanel icon={Layers3} title="No full SOP layer" text="This version only has atomic retrieval units. Re-extract to create a document-level page." compact />
            )}
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <Card className="rounded-xl">
            <CardHeader className="border-b pb-4">
              <CardTitle>Versions</CardTitle>
              <CardDescription>Publish locks a curated version and syncs indexes.</CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              {versions.length === 0 ? (
                <EmptyPanel icon={History} title="No versions loaded" text="Select a document to inspect immutable versions." compact />
              ) : (
                <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
                  {versions.map((version) => {
                    const isInspectedVersion = selectedChunkVersionId === version.version_id;
                    const publishBlocked = selectedIsArchived || !isInspectedVersion || !readinessPassed;
                    return (
                    <div className={cn("rounded-lg border p-3", selectedChunkVersionId === version.version_id ? "bg-muted/35" : "bg-card")} key={version.version_id}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="secondary">v{version.version_number}</Badge>
                            <StatusBadge status={version.status} />
                            <Badge variant="outline">{version.review_status ?? "needs_review"}</Badge>
                          </div>
                          <p className="mt-2 text-sm font-medium">{version.change_summary || "No change summary"}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {version.chunk_count} chunks, confidence {Math.round((version.extraction_confidence ?? 0) * 100)}%, {formatDate(version.created_at)}
                          </p>
                        </div>
                        {version.status !== "published" ? (
                          <Button
                            data-testid={`version-${version.version_id}-publish`}
                            disabled={busyKey === "publishing" || publishBlocked}
                            onClick={() => {
                              if (confirmingPublishVersionId !== version.version_id) {
                                setConfirmingPublishVersionId(version.version_id);
                                return;
                              }
                              setConfirmingPublishVersionId("");
                              onPublishVersion(version.version_id);
                            }}
                            size="sm"
                            type="button"
                          >
                            {selectedIsArchived
                              ? "Archived"
                              : !isInspectedVersion
                                ? "Inspect first"
                              : !readinessPassed
                                ? "Not ready"
                              : busyKey === "publishing"
                              ? "Publishing"
                              : confirmingPublishVersionId === version.version_id
                                ? "Confirm publish"
                                : "Publish"}
                          </Button>
                        ) : (
                          <Badge variant="secondary">indexed</Badge>
                        )}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          onClick={() => onInspectVersion(version.version_id)}
                          size="sm"
                          type="button"
                          variant={selectedChunkVersionId === version.version_id ? "secondary" : "outline"}
                        >
                          Inspect version
                        </Button>
                        {version.status === "published" ? (
                          <>
                            <Button asChild size="sm" type="button" variant="outline">
                              <a href={`${workspacePaths.lookup}?q=${encodeURIComponent(selectedDocumentTitle)}`}>
                                <Search data-icon="inline-start" className="size-3.5" />
                                Test lookup
                              </a>
                            </Button>
                            <Button asChild size="sm" type="button" variant="ghost">
                              <a href={`${workspacePaths.chat}?q=${encodeURIComponent(`Dựa trên ${selectedDocumentTitle}, CS cần làm gì?`)}`}>
                                <MessageSquareText data-icon="inline-start" className="size-3.5" />
                                Ask chat
                              </a>
                            </Button>
                          </>
                        ) : null}
                      </div>
                      {version.status === "published" ? (
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          This version is live. Test it from the same Lookup and SOP Chat surfaces agents will use.
                        </p>
                      ) : null}
                      {confirmingPublishVersionId === version.version_id ? (
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          {selectedIsArchived
                            ? "Archived sources cannot be republished from this audit view."
                            : !readinessPassed
                              ? "Publishing is blocked until the readiness checklist passes."
                            : "Confirming will lock this version, archive the previous published version, and sync search indexes."}
                        </p>
                      ) : null}
                    </div>
                  )})}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="rounded-xl">
            <CardHeader className="border-b pb-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>Extraction review</CardTitle>
                  <CardDescription>Default view shows only units that still need review. Use bulk approve for test runs.</CardDescription>
                </div>
                {reviewStats.total ? (
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">{reviewStats.reviewed}/{reviewStats.total} reviewed</Badge>
                    <Badge variant="outline">{reviewStats.security} security notes</Badge>
                    <Badge variant="outline">{atomicUnits.length} retrieval units</Badge>
                  </div>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              {!selectedDocument ? (
                <EmptyPanel icon={GitBranch} title="Select a document" text="Choose a source file to inspect extracted knowledge units." compact />
              ) : extractionUnitsLoading ? (
                <div className="flex items-center gap-2 rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Loading extraction units
                </div>
              ) : extractionUnits.length === 0 ? (
                <EmptyPanel icon={GitBranch} title="No extraction units" text="This version has no extracted units yet." compact />
              ) : (
                <div className="grid gap-4 2xl:grid-cols-[minmax(24rem,0.9fr)_minmax(0,1.6fr)]">
                  <SourceViewer
                    extractionUnits={extractionUnits}
                    loading={versionRawLoading}
                    selectedDocument={selectedDocument}
                    selectedVersion={selectedVersion}
                    versionRaw={versionRaw}
                  />
                  <div className="min-w-0">
                    <div className="sticky top-3 z-10 mb-3 rounded-xl border bg-background/95 p-3 shadow-sm backdrop-blur">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold">Structured units</div>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            Showing {filteredUnitsCount} of {extractionUnits.length}. {requiredUnitFocus ? `Focused on ${requiredUnitFocus.label}.` : selectedVersion?.status === "published" ? "Published versions are locked." : "Draft units are editable."}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline">{selectedIsArchived ? "audit only" : selectedVersion?.status === "published" ? "locked" : "editable draft"}</Badge>
                          <Button
                            disabled={!canBulkApproveVisible || busyKey === "bulk-review"}
                            onClick={() => selectedVersion && onBulkReviewVersion(selectedVersion.version_id, reviewFilter === "atomic" ? "atomic" : "all", "approved", true)}
                            size="sm"
                            type="button"
                            variant="secondary"
                          >
                            {busyKey === "bulk-review" ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <CheckCircle2 data-icon="inline-start" className="size-4" />}
                            Approve visible
                          </Button>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-1 rounded-lg border bg-muted/15 p-1">
                        {REVIEW_FILTERS.map((filter) => (
                          <Button
                            className="h-8 px-3"
                            key={filter.value}
                            onClick={() => setReviewFilter(filter.value)}
                            size="sm"
                            type="button"
                            variant={reviewFilter === filter.value ? "secondary" : "ghost"}
                          >
                            {filter.label}
                            <span className="ml-1 rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                              {reviewFilterCounts[filter.value]}
                            </span>
                          </Button>
                        ))}
                      </div>
                      {requiredUnitFocus ? (
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-secondary/35 px-3 py-2">
                          <p className="text-xs leading-5 text-muted-foreground">
                            Focused requirement: <span className="font-semibold text-foreground">{requiredUnitFocus.label}</span>. Edit the matching unit below, then mark reviewed or approve.
                          </p>
                          <Button onClick={() => setRequiredUnitFocus(null)} size="sm" type="button" variant="ghost">
                            Clear focus
                          </Button>
                        </div>
                      ) : null}
                    </div>
                    <ScrollArea className="h-[52rem] pr-3">
                      <div className="space-y-3">
                        {filteredUnitsCount === 0 ? (
                          <EmptyPanel
                            icon={CheckCircle2}
                            title={reviewFilter === "needs_review" ? "No units need review" : "No units in this filter"}
                            text={reviewFilter === "needs_review" ? "Switch to All or Approved to audit completed units." : "Change the review filter to inspect another group."}
                            compact
                          />
                        ) : null}
                        {filteredDocumentLayer ? (
                          <section className="space-y-2">
                            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                              <BookOpen className="size-4" />
                              Document layer
                            </div>
                            <ExtractionReviewEditor
                              defaultEffectiveFrom={defaultEffectiveFrom}
                              disabled={!canEditSelectedVersion}
                              onSave={onUpdateExtractionUnit}
                              saving={savingUnitId === filteredDocumentLayer.unit_id}
                              unit={filteredDocumentLayer}
                            />
                          </section>
                        ) : null}
                        {filteredAtomicUnits.length ? (
                          <section className="space-y-2">
                          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                            <Layers3 className="size-4" />
                            Atomic retrieval units
                          </div>
                          {focusedRequiredUnits.length ? (
                            <div className="rounded-lg border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                              Showing matching unit(s) first for <span className="font-semibold text-foreground">{requiredUnitFocus?.label}</span>.
                            </div>
                          ) : null}
                          {sortUnitsForRequirementFocus(filteredAtomicUnits, requiredUnitFocus).map((unit) => (
                            <ExtractionReviewEditor
                              defaultEffectiveFrom={defaultEffectiveFrom}
                              disabled={!canEditSelectedVersion}
                              key={unit.unit_id}
                              onSave={onUpdateExtractionUnit}
                              saving={savingUnitId === unit.unit_id}
                              unit={unit}
                            />
                          ))}
                        </section>
                        ) : null}
                      </div>
                    </ScrollArea>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Indexed chunks</CardTitle>
            <CardDescription>Raw retrieval units for the selected version, useful for debugging citations.</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            {!selectedDocument ? (
              <EmptyPanel icon={Database} title="Select a document" text="Choose an indexed document to view extracted chunks." compact />
            ) : chunksLoading ? (
              <div className="flex items-center gap-2 rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading chunks
              </div>
            ) : chunks.length === 0 ? (
              <EmptyPanel
                icon={Database}
                title="No chunks available"
                text={selectedIsArchived ? "Archived sources are excluded from active indexes. Inspect raw extraction for historical evidence." : "Draft versions may not have active chunks selected."}
                compact
              />
            ) : (
              <ScrollArea className="h-[22rem] pr-3">
                <div className="divide-y">
                  {chunks.map((chunk) => (
                    <article className="py-4" key={chunk.chunk_id}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="secondary">chunk {chunk.chunk_index}</Badge>
                          <Badge variant="outline">{chunk.section}</Badge>
                          <Badge variant="outline">{String(chunk.metadata.retrieval_scope ?? "unit")}</Badge>
                          <Badge variant="outline">{chunk.token_count} tokens</Badge>
                        </div>
                        <span className="font-mono text-[10px] text-muted-foreground">{chunk.chunk_id.slice(0, 8)}</span>
                      </div>
                      {chunk.heading ? <h4 className="mt-3 text-sm font-semibold">{chunk.heading}</h4> : null}
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{chunk.content}</p>
                    </article>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

const REVIEW_FILTERS: Array<{ label: string; value: ReviewFilter }> = [
  { label: "Needs review", value: "needs_review" },
  { label: "Reviewed", value: "reviewed" },
  { label: "Approved", value: "approved" },
  { label: "Atomic", value: "atomic" },
  { label: "All", value: "all" },
];

function unitMatchesReviewFilter(unit: ExtractionUnit, filter: ReviewFilter, isAtomic: boolean) {
  if (filter === "all") {
    return true;
  }
  if (filter === "atomic") {
    return isAtomic;
  }
  return unit.review_status === filter;
}

function sortUnitsForRequirementFocus(units: ExtractionUnit[], requirement: RequiredWorkflowUnit | null) {
  if (!requirement) {
    return units;
  }
  return [...units].sort((left, right) => {
    const leftMatch = requirement.types.includes(left.unit_type) ? 0 : 1;
    const rightMatch = requirement.types.includes(right.unit_type) ? 0 : 1;
    return leftMatch - rightMatch || left.unit_index - right.unit_index;
  });
}

function inferredEffectiveFrom(units: ExtractionUnit[], selectedDocument: DocumentSummary | null, selectedVersion?: VersionSummary) {
  for (const unit of units) {
    const value = unit.metadata.effective_from ?? unit.metadata.effectiveFrom;
    if (value) {
      return String(value);
    }
  }
  const documentValue = selectedDocument?.metadata?.effective_from ?? selectedDocument?.metadata?.effectiveFrom;
  if (documentValue) {
    return String(documentValue);
  }
  if (selectedVersion?.created_at) {
    return selectedVersion.created_at.slice(0, 10);
  }
  return new Date().toISOString().slice(0, 10);
}

function extractionIssue(document: DocumentSummary | null) {
  if (!document) {
    return null;
  }
  const status = String(document.metadata?.extraction_status ?? "");
  const error = String(document.metadata?.extraction_error ?? "");
  const warnings = Array.isArray(document.metadata?.extraction_warnings)
    ? document.metadata.extraction_warnings.map(String).filter(Boolean)
    : [];
  if (!status.startsWith("failed") && !error && !warnings.some((warning) => warning.includes("failed") || warning.includes("openrouter"))) {
    return null;
  }
  return {
    reason: error || warnings[0] || "Extraction failed before structured units were created.",
    status,
    warnings,
  };
}

function ValidationPill({ text, valid }: { text: string; valid: boolean }) {
  return (
    <div className={cn("rounded-lg border px-2 py-1 text-[11px]", valid ? "bg-secondary text-secondary-foreground" : "border-destructive/30 bg-destructive/10 text-destructive")}>
      {valid ? "OK" : "Block"}: {text}
    </div>
  );
}

function WorkflowRequirementsPanel({
  busy,
  canEdit,
  defaultEffectiveFrom,
  onConvertCandidate,
  onCreate,
  onReviewExisting,
  requirements,
}: {
  busy: boolean;
  canEdit: boolean;
  defaultEffectiveFrom: string;
  onConvertCandidate: (unit: ExtractionUnit, requirement: RequiredWorkflowUnit) => void;
  onCreate: (requirement: RequiredWorkflowUnit) => void;
  onReviewExisting: (requirement: RequiredWorkflowUnit) => void;
  requirements: WorkflowRequirementStatus[];
}) {
  const missingCount = requirements.filter((requirement) => requirement.status !== "ready").length;
  return (
    <Card className="rounded-xl">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Required workflow units</CardTitle>
            <CardDescription>
              Review these workflow-specific units before publish. Missing items can be created as review stubs, then filled from source evidence.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={missingCount ? "destructive" : "secondary"}>
              {missingCount ? `${missingCount} need action` : "ready"}
            </Badge>
            <Badge variant="outline">effective {defaultEffectiveFrom}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 pt-4">
        {requirements.map((requirement) => {
          const candidate = requirement.candidateUnits[0];
          const needsReview = requirement.status === "needs_review";
          const missing = requirement.status === "missing";
          const existingUnit = requirement.matchingUnits[0];
          return (
            <article className="rounded-xl border bg-muted/10 p-3" key={requirement.key}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={requirement.status === "ready" ? "secondary" : requirement.status === "needs_review" ? "outline" : "destructive"}>
                      {requirement.status === "ready" ? "reviewed" : requirement.status === "needs_review" ? "needs review" : "missing"}
                    </Badge>
                    <Badge variant="outline">{requirement.key}</Badge>
                  </div>
                  <h3 className="mt-2 text-sm font-semibold">{requirement.label}</h3>
                  <p className="mt-1 max-w-[72ch] text-xs leading-5 text-muted-foreground">
                    {workflowRequirementGuidance(requirement.key)}
                  </p>
                  {candidate && missing ? (
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                      Candidate source: <span className="font-medium text-foreground">{candidate.title}</span>
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {needsReview ? (
                    <Button onClick={() => onReviewExisting(requirement)} size="sm" type="button" variant="outline">
                      Open in review list
                    </Button>
                  ) : null}
                  {missing && candidate ? (
                    <Button
                      disabled={!canEdit}
                      onClick={() => onConvertCandidate(candidate, requirement)}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      <WandSparkles data-icon="inline-start" className="size-4" />
                      Convert candidate
                    </Button>
                  ) : null}
                  {missing ? (
                    <Button disabled={!canEdit || busy} onClick={() => onCreate(requirement)} size="sm" type="button" variant="secondary">
                      {busy ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Plus data-icon="inline-start" className="size-4" />}
                      Add blank unit
                    </Button>
                  ) : null}
                </div>
              </div>
              {existingUnit ? (
                <p className="mt-3 text-[11px] text-muted-foreground">
                  Existing unit: <span className="font-medium text-foreground">{existingUnit.title}</span>
                </p>
              ) : missing ? (
                <p className="mt-3 text-[11px] text-muted-foreground">
                  Use Convert candidate when suggested source looks right, or Add blank unit if CS Ops needs to write it manually from the source viewer.
                </p>
              ) : null}
            </article>
          );
        })}
      </CardContent>
    </Card>
  );
}

function SourceViewer({
  extractionUnits,
  loading,
  selectedDocument,
  selectedVersion,
  versionRaw,
}: {
  extractionUnits: ExtractionUnit[];
  loading: boolean;
  selectedDocument: DocumentSummary;
  selectedVersion?: VersionSummary;
  versionRaw: VersionRawText | null;
}) {
  const [failedPreviewUrl, setFailedPreviewUrl] = useState("");
  const isPdfSource = selectedDocument.source_filename.toLowerCase().endsWith(".pdf") || selectedDocument.latest_document_type === "workflow_diagram";
  const previewUrl =
    isPdfSource && selectedVersion
      ? `${API_BASE_URL}/api/v1/ai/versions/${selectedVersion.version_id}/source/pages/1`
      : "";
  const references = extractionUnits
    .map(sourceReference)
    .filter(Boolean)
    .slice(0, 6);
  return (
    <aside className="rounded-xl border bg-muted/15">
      <div className="border-b p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">source evidence</Badge>
          {selectedDocument.status === "archived" ? <Badge variant="outline">archived</Badge> : null}
          <Badge variant="outline">v{selectedVersion?.version_number ?? "-"}</Badge>
          <Badge variant="outline">{selectedDocument.latest_document_type ?? "unknown"}</Badge>
        </div>
        <h3 className="mt-3 line-clamp-2 text-sm font-semibold">{selectedDocument.source_filename}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {selectedDocument.status === "archived"
            ? "Historical source evidence is preserved for audit. It is excluded from active lookup."
            : "Compare raw extraction on the left with curated SOP units on the right before publish."}
        </p>
      </div>
      <div className="space-y-3 p-3">
        {previewUrl && failedPreviewUrl !== previewUrl ? (
          <div className="overflow-hidden rounded-lg border bg-background">
            <div className="border-b px-3 py-2 text-xs font-medium text-muted-foreground">Rendered source page 1</div>
            <img
              alt={`Rendered source preview for ${selectedDocument.source_filename}`}
              className="max-h-[34rem] w-full object-contain"
              onError={() => setFailedPreviewUrl(previewUrl)}
              src={previewUrl}
            />
          </div>
        ) : previewUrl ? (
          <div className="rounded-lg border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
            Source page image is not available for this version. Raw extraction is shown below.
          </div>
        ) : null}
        {references.length ? (
          <div className="flex flex-wrap gap-2">
            {references.map((reference) => (
              <Badge key={reference} variant="outline">{reference}</Badge>
            ))}
          </div>
        ) : null}
        {loading ? (
          <div className="flex items-center gap-2 rounded-lg border bg-background/60 p-3 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading raw extraction
          </div>
        ) : versionRaw?.raw_text ? (
          <ScrollArea className="h-[40rem] rounded-lg border bg-background p-3">
            <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-5 text-muted-foreground">{versionRaw.raw_text}</pre>
          </ScrollArea>
        ) : (
          <EmptyPanel icon={FileText} title="No raw source loaded" text="Raw extraction is unavailable for this version." compact />
        )}
      </div>
    </aside>
  );
}

function WorkflowGraphPanel({
  canEdit,
  confidence,
  graph,
  graphUnit,
  onAcknowledge,
  onReviewEdge,
  saving,
}: {
  canEdit: boolean;
  confidence: number;
  graph?: WorkflowGraphMetadata;
  graphUnit?: ExtractionUnit;
  onAcknowledge: (unit: ExtractionUnit, reason: string) => void;
  onReviewEdge: (unit: ExtractionUnit, edge: WorkflowEdgeMetadata, status: "acknowledged" | "confirmed" | "rejected", reason: string) => void;
  saving: boolean;
}) {
  const [acknowledgementReason, setAcknowledgementReason] = useState("");
  const validationErrors = graph?.validation_errors ?? graphUnit?.metadata.graph_validation_errors ?? [];
  const uncertainEdges = graph?.uncertain_edges ?? graphUnit?.metadata.uncertain_edges ?? [];
  const annotations = graph?.annotations ?? graphUnit?.metadata.annotations ?? [];
  const uncertainEdgeCount =
    (Array.isArray(uncertainEdges) ? uncertainEdges.length : 0) +
    Number(graphUnit?.metadata.uncertain_edges_count ?? 0);
  const issueCount = (Array.isArray(validationErrors) ? validationErrors.length : 0) + uncertainEdgeCount;
  const acknowledged = issueCount === 0 || graphUnit?.metadata.graph_validation_acknowledged === true;
  const edgeReviewSummary = buildWorkflowEdgeReviewSummary(graph, graphUnit);
  return (
    <Card className="rounded-xl">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Workflow graph</CardTitle>
            <CardDescription>Visual graph for branch review. Edit the extracted units below, use this panel only to inspect flow correctness.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={graphUnit?.review_status === "needs_review" ? "destructive" : "secondary"}>
              {graphUnit?.review_status ?? "missing"}
            </Badge>
            <Badge variant="outline">{Math.round(confidence * 100)}% confidence</Badge>
            <Badge variant="outline">{graph?.nodes?.length ?? 0} nodes</Badge>
            <Badge variant="outline">{graph?.edges?.length ?? 0} edges</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        {graphUnit && graph ? (
          <div className="space-y-4">
            <div className="rounded-xl border bg-muted/15 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Network className="size-4" />
                {graph.title ?? graphUnit.title}
              </div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {String(graph.review_reason ?? graphUnit.metadata.review_reason ?? "Review graph branches and arrow direction before publish.")}
              </p>
            </div>
            {issueCount ? (
              <div className={cn("rounded-xl border p-4", acknowledged ? "bg-secondary/30" : "border-destructive/30 bg-destructive/5")}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className={cn("text-sm font-semibold", acknowledged ? "text-foreground" : "text-destructive")}>Topology validation blockers</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {acknowledged
                        ? "Human reviewer acknowledged these topology warnings. Backend publish gate will accept this graph if other checks pass."
                        : "Backend publish is blocked until these graph warnings are acknowledged after source review."}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={acknowledged ? "secondary" : "destructive"}>{issueCount} issues</Badge>
                    {acknowledged ? <Badge variant="outline">acknowledged</Badge> : null}
                    {graphUnit && !acknowledged ? (
                      <div className="flex flex-col gap-2 sm:min-w-80">
                        <textarea
                          className="min-h-16 rounded-md border bg-background px-3 py-2 text-xs leading-5 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                          onChange={(event) => setAcknowledgementReason(event.target.value)}
                          placeholder="Required: why this graph warning is acceptable after checking the source."
                          value={acknowledgementReason}
                        />
                        <Button
                          disabled={!canEdit || saving || acknowledgementReason.trim().length < 12}
                          onClick={() => onAcknowledge(graphUnit, acknowledgementReason.trim())}
                          size="sm"
                          type="button"
                          variant="secondary"
                        >
                          {saving ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <ShieldCheck data-icon="inline-start" className="size-4" />}
                          Acknowledge with reason
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </div>
                {Array.isArray(validationErrors) && validationErrors.length ? (
                  <div className="mt-3 grid gap-2">
                    {validationErrors.slice(0, 8).map((error, index) => (
                    <p className="rounded-lg border bg-background px-3 py-2 text-xs leading-5 text-muted-foreground" key={`${error}-${index}`}>
                      {String(error)}
                    </p>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            <div className="grid gap-4 2xl:grid-cols-[minmax(22rem,0.85fr)_minmax(0,1.35fr)]">
              <div className="rounded-xl border bg-background p-3">
                <WorkflowMermaid graph={graph} />
              </div>
              <ScrollArea className="h-[30rem] rounded-xl border">
                <WorkflowBranchTable canEdit={canEdit} graph={graph} graphUnit={graphUnit} onReviewEdge={onReviewEdge} saving={saving} />
              </ScrollArea>
            </div>
            <div className="rounded-xl border bg-muted/15 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold">Decision branch review</p>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={edgeReviewSummary.blockingCount ? "destructive" : "secondary"}>
                    {edgeReviewSummary.reviewed}/{edgeReviewSummary.total} reviewed
                  </Badge>
                  {edgeReviewSummary.rejected ? <Badge variant="destructive">{edgeReviewSummary.rejected} rejected</Badge> : null}
                  {edgeReviewSummary.missingReason ? <Badge variant="outline">{edgeReviewSummary.missingReason} missing reason</Badge> : null}
                </div>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Publish requires each decision branch to be confirmed, or acknowledged with a reason if the source is ambiguous.
              </p>
            </div>
            <div className="grid gap-4 2xl:grid-cols-2">
              <WorkflowAnnotationsPanel annotations={Array.isArray(annotations) ? annotations : []} />
              <WorkflowUncertainEdgesPanel edges={Array.isArray(uncertainEdges) ? uncertainEdges : []} graph={graph} />
            </div>
          </div>
        ) : (
          <EmptyPanel icon={Network} title="No workflow graph" text="Re-extract this workflow diagram. Publish is blocked until graph nodes and edges exist." compact />
        )}
      </CardContent>
    </Card>
  );
}

function WorkflowAnnotationsPanel({ annotations }: { annotations: NonNullable<WorkflowGraphMetadata["annotations"]> }) {
  return (
    <div className="rounded-xl border bg-background">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <p className="text-xs font-semibold text-muted-foreground">Annotations, notes, scripts</p>
        <Badge variant="outline">{annotations.length}</Badge>
      </div>
      {annotations.length ? (
        <ScrollArea className="h-64">
          <div className="divide-y">
            {annotations.slice(0, 40).map((annotation, index) => (
              <div className="p-3" key={annotation.id ?? `${annotation.type}-${index}`}>
                <div className="flex flex-wrap items-center gap-1">
                  <Badge variant={annotation.risk_level === "high" ? "destructive" : "outline"}>{annotation.type ?? "annotation"}</Badge>
                  {annotation.attached_to ? <Badge variant="secondary">attached: {annotation.attached_to}</Badge> : null}
                </div>
                <p className="mt-2 text-sm font-medium leading-5">{annotation.title || "Lưu ý workflow"}</p>
                <p className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">{annotation.content}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      ) : (
        <p className="p-3 text-xs leading-5 text-muted-foreground">No annotations extracted. For diagrams, notes/scripts should be separated from main workflow steps.</p>
      )}
    </div>
  );
}

function WorkflowUncertainEdgesPanel({
  edges,
  graph,
}: {
  edges: NonNullable<WorkflowGraphMetadata["uncertain_edges"]>;
  graph: WorkflowGraphMetadata;
}) {
  const resolver = useMemo(() => buildWorkflowNodeResolver(graph), [graph]);
  return (
    <div className="rounded-xl border bg-background">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <p className="text-xs font-semibold text-muted-foreground">Uncertain edges needing review</p>
        <Badge variant={edges.length ? "destructive" : "outline"}>{edges.length}</Badge>
      </div>
      {edges.length ? (
        <ScrollArea className="h-64">
          <div className="divide-y">
            {edges.slice(0, 40).map((edge, index) => (
              <div className="grid gap-2 p-3 text-sm" key={`${edge.from_node}-${edge.to_node}-${index}`}>
                <div className="grid grid-cols-[minmax(0,1fr)_5rem_minmax(0,1fr)] items-start gap-2">
                  <NodeSummary node={resolver.resolve(edge.from_node)} fallback={edge.from_node} />
                  <Badge className="justify-center" variant="outline">{edge.condition || "unclear"}</Badge>
                  <NodeSummary node={resolver.resolve(edge.to_node)} fallback={edge.to_node} />
                </div>
                <p className="text-xs leading-5 text-muted-foreground">{edge.reason}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      ) : (
        <p className="p-3 text-xs leading-5 text-muted-foreground">No uncertain edges. Decision branches still require graph review before publishing workflow diagrams.</p>
      )}
    </div>
  );
}

function WorkflowBranchTable({
  canEdit,
  graph,
  graphUnit,
  onReviewEdge,
  saving,
}: {
  canEdit: boolean;
  graph: WorkflowGraphMetadata;
  graphUnit?: ExtractionUnit;
  onReviewEdge: (unit: ExtractionUnit, edge: WorkflowEdgeMetadata, status: "acknowledged" | "confirmed" | "rejected", reason: string) => void;
  saving: boolean;
}) {
  const resolver = useMemo(() => buildWorkflowNodeResolver(graph), [graph]);
  const [edgeReasons, setEdgeReasons] = useState<Record<string, string>>({});
  const branches = (graph.edges ?? []).slice(0, 100).map((edge, index) => {
    const edgeKey = workflowEdgeKey(edge);
    const review = workflowEdgeReview(graphUnit, edge);
    return {
      condition: edge.condition || "Next",
      edge,
      edgeKey,
      from: resolver.resolve(edge.from_node),
      index,
      isDecisionEdge: isDecisionWorkflowEdge(edge, graph),
      rawFrom: edge.from_node,
      rawTo: edge.to_node,
      review,
      to: resolver.resolve(edge.to_node),
    };
  });

  return (
    <div className="divide-y">
      <div className="sticky top-0 z-10 grid grid-cols-[2.5rem_minmax(0,1fr)_7rem_minmax(0,1fr)_12rem] gap-3 border-b bg-card px-3 py-2 text-xs font-semibold text-muted-foreground">
        <span>#</span>
        <span>From</span>
        <span>Condition</span>
        <span>Next step</span>
        <span>Review</span>
      </div>
      {branches.length ? branches.map((branch) => (
        <div className="grid grid-cols-[2.5rem_minmax(0,1fr)_7rem_minmax(0,1fr)_12rem] gap-3 px-3 py-3 text-sm" key={`${branch.rawFrom}-${branch.rawTo}-${branch.index}`}>
          <span className="text-xs text-muted-foreground">{branch.index + 1}</span>
          <NodeSummary node={branch.from} fallback={branch.rawFrom} />
          <div>
            <Badge variant={branch.condition.toLowerCase() === "yes" ? "secondary" : branch.condition.toLowerCase() === "no" ? "outline" : "outline"}>
              {branch.condition}
            </Badge>
          </div>
          <NodeSummary node={branch.to} fallback={branch.rawTo} />
          <div className="space-y-2">
            {branch.isDecisionEdge ? (
              <>
                <Badge variant={branch.review.status === "confirmed" ? "secondary" : branch.review.status === "rejected" ? "destructive" : branch.review.status === "acknowledged" ? "outline" : "destructive"}>
                  {branch.review.status || "needs_review"}
                </Badge>
                {branch.review.reason ? (
                  <p className="line-clamp-2 text-[11px] leading-4 text-muted-foreground">{branch.review.reason}</p>
                ) : null}
                {graphUnit && canEdit ? (
                  <div className="grid gap-1.5">
                    <textarea
                      className="min-h-14 rounded-md border bg-background px-2 py-1.5 text-[11px] leading-4 outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
                      onChange={(event) => setEdgeReasons((current) => ({ ...current, [branch.edgeKey]: event.target.value }))}
                      placeholder="Reason for acknowledge/reject"
                      value={edgeReasons[branch.edgeKey] ?? ""}
                    />
                    <div className="flex flex-wrap gap-1">
                      <Button
                        className="h-7 px-2 text-[11px]"
                        disabled={saving}
                        onClick={() => onReviewEdge(graphUnit, branch.edge, "confirmed", edgeReasons[branch.edgeKey] ?? "")}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        Confirm
                      </Button>
                      <Button
                        className="h-7 px-2 text-[11px]"
                        disabled={saving || (edgeReasons[branch.edgeKey] ?? "").trim().length < 8}
                        onClick={() => onReviewEdge(graphUnit, branch.edge, "acknowledged", (edgeReasons[branch.edgeKey] ?? "").trim())}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        Ack
                      </Button>
                      <Button
                        className="h-7 px-2 text-[11px]"
                        disabled={saving || (edgeReasons[branch.edgeKey] ?? "").trim().length < 8}
                        onClick={() => onReviewEdge(graphUnit, branch.edge, "rejected", (edgeReasons[branch.edgeKey] ?? "").trim())}
                        size="sm"
                        type="button"
                        variant="ghost"
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <Badge variant="outline">not decision</Badge>
            )}
          </div>
        </div>
      )) : (
        <div className="p-4 text-sm text-muted-foreground">No graph branches were extracted.</div>
      )}
    </div>
  );
}

function NodeSummary({ fallback, node }: { fallback?: string; node?: WorkflowNodeMetadata }) {
  return (
    <div className="min-w-0">
      <p className="line-clamp-2 font-medium leading-5">{node?.title || node?.question || fallback || "Unknown step"}</p>
      <div className="mt-1 flex flex-wrap gap-1">
        {node?.type ? <Badge variant="outline">{node.type}</Badge> : null}
        {node?.phase ? <Badge variant="outline">{node.phase}</Badge> : null}
        {node?.actor ? <Badge variant="outline">{node.actor}</Badge> : null}
      </div>
    </div>
  );
}

function WorkflowMermaid({ graph }: { graph: WorkflowGraphMetadata }) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const [svgSize, setSvgSize] = useState<{ height: number; width: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const svgRef = useRef<HTMLDivElement>(null);
  const chart = useMemo(() => workflowGraphToMermaid(graph), [graph]);
  const renderId = useMemo(() => `workflow-graph-${Math.random().toString(36).slice(2)}`, [chart]);

  useEffect(() => {
    let cancelled = false;
    async function renderChart() {
      setError("");
      setSvg("");
      if (!chart) {
        setError("No graph syntax available.");
        return;
      }
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          flowchart: {
            curve: "basis",
            htmlLabels: true,
            nodeSpacing: 42,
            rankSpacing: 54,
          },
          startOnLoad: false,
          securityLevel: "strict",
          theme: "neutral",
        });
        const result = await mermaid.render(renderId, chart);
        if (!cancelled) {
          setSvg(result.svg);
        }
      } catch (renderError) {
        if (!cancelled) {
          setError(renderError instanceof Error ? renderError.message : "Mermaid render failed.");
        }
      }
    }
    void renderChart();
    return () => {
      cancelled = true;
    };
  }, [chart, renderId]);

  useEffect(() => {
    if (!svg) {
      setSvgSize(null);
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const element = svgRef.current?.querySelector("svg");
      if (!(element instanceof SVGSVGElement)) {
        return;
      }
      const viewBox = element.viewBox.baseVal;
      const rect = element.getBoundingClientRect();
      const width = viewBox.width || rect.width;
      const height = viewBox.height || rect.height;
      if (width && height) {
        setSvgSize({ height, width });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [svg]);

  return (
    <div className="rounded-lg border bg-background p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-muted-foreground">Mermaid workflow preview</p>
        <div className="flex flex-wrap items-center gap-2">
          {svg ? (
            <div className="flex items-center overflow-hidden rounded-lg border bg-card">
              <Button
                className="h-7 rounded-none border-0 px-2 text-xs"
                disabled={zoom <= 0.6}
                onClick={() => setZoom((value) => Math.max(0.6, Number((value - 0.15).toFixed(2))))}
                size="sm"
                type="button"
                variant="ghost"
              >
                −
              </Button>
              <span className="min-w-12 border-x px-2 text-center text-xs font-medium tabular-nums text-muted-foreground">
                {Math.round(zoom * 100)}%
              </span>
              <Button
                className="h-7 rounded-none border-0 px-2 text-xs"
                disabled={zoom >= 2}
                onClick={() => setZoom((value) => Math.min(2, Number((value + 0.15).toFixed(2))))}
                size="sm"
                type="button"
                variant="ghost"
              >
                +
              </Button>
              <Button
                className="h-7 rounded-none border-0 border-l px-2 text-xs"
                disabled={zoom === 1}
                onClick={() => setZoom(1)}
                size="sm"
                type="button"
                variant="ghost"
              >
                Reset
              </Button>
            </div>
          ) : null}
          <Badge variant="outline">{graph.edges?.length ?? 0} edges</Badge>
        </div>
      </div>
      {svg ? (
        <div className="max-h-[42rem] overflow-auto rounded-md border bg-muted/20 p-3">
          <div
            className="relative"
            style={{
              height: svgSize ? svgSize.height * zoom : undefined,
              minHeight: svgSize ? undefined : "20rem",
              width: svgSize ? svgSize.width * zoom : undefined,
            }}
          >
            <div
              className="origin-top-left [&_svg]:max-w-none"
              dangerouslySetInnerHTML={{ __html: svg }}
              ref={svgRef}
              style={{ transform: `scale(${zoom})` }}
            />
          </div>
        </div>
      ) : error ? (
        <div className="rounded-md border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
          Mermaid could not render this graph. Use the readable branch table next to this panel to review the extraction.
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          Rendering graph
        </div>
      )}
    </div>
  );
}

function workflowGraphToMermaid(graph: WorkflowGraphMetadata) {
  const edges = graph.edges ?? [];
  if (!edges.length) {
    return "";
  }
  const resolver = buildWorkflowNodeResolver(graph);
  const endpointIds = new Map<string, string>();
  const lines = ["flowchart LR"];

  edges.slice(0, 120).forEach((edge) => {
    const from = mermaidEndpointId(edge.from_node, endpointIds);
    const to = mermaidEndpointId(edge.to_node, endpointIds);
    if (!from || !to) {
      return;
    }
    ensureMermaidNode(lines, from, resolver.label(edge.from_node));
    ensureMermaidNode(lines, to, resolver.label(edge.to_node));
    const condition = String(edge.condition || "").trim();
    lines.push(condition ? `  ${from} -->|"${escapeMermaidLabel(condition)}"| ${to}` : `  ${from} --> ${to}`);
  });

  return lines.join("\n");
}

function ensureMermaidNode(lines: string[], id: string, label: string) {
  const declaration = `  ${id}["${escapeMermaidLabel(label)}"]`;
  if (!lines.includes(declaration)) {
    lines.push(declaration);
  }
}

function mermaidEndpointId(value: string | undefined, endpointIds: Map<string, string>) {
  const key = String(value || "").trim();
  if (!key) {
    return "";
  }
  const existing = endpointIds.get(key);
  if (existing) {
    return existing;
  }
  const id = `n${endpointIds.size}`;
  endpointIds.set(key, id);
  return id;
}

function escapeMermaidLabel(value: string) {
  const clean = value.replace(/"/g, "'").replace(/\|/g, "/").replace(/\s+/g, " ").trim();
  return wrapMermaidLabel(clean, 34).slice(0, 220);
}

function wrapMermaidLabel(value: string, maxLineLength: number) {
  const words = value.split(" ");
  const lines: string[] = [];
  let current = "";
  words.forEach((word) => {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxLineLength && current) {
      lines.push(current);
      current = word;
      return;
    }
    current = candidate;
  });
  if (current) {
    lines.push(current);
  }
  return lines.slice(0, 4).join("<br/>");
}

function buildWorkflowNodeResolver(graph: WorkflowGraphMetadata) {
  const nodes = graph.nodes ?? [];
  const exact = new Map<string, WorkflowNodeMetadata>();
  const normalized = new Map<string, WorkflowNodeMetadata>();
  const buckets = {
    decision: [] as WorkflowNodeMetadata[],
    end: [] as WorkflowNodeMetadata[],
    note: [] as WorkflowNodeMetadata[],
    orderHistory: [] as WorkflowNodeMetadata[],
    script: [] as WorkflowNodeMetadata[],
    start: [] as WorkflowNodeMetadata[],
    step: [] as WorkflowNodeMetadata[],
  };

  nodes.forEach((node, index) => {
    [node.id, node.title, node.question].filter(Boolean).forEach((value) => {
      exact.set(String(value), node);
      normalized.set(normalizeWorkflowKey(String(value)), node);
    });
    classifyWorkflowNode(node, index, nodes.length).forEach((kind) => {
      buckets[kind].push(node);
    });
  });

  function resolve(value?: string) {
    const raw = String(value || "").trim();
    if (!raw) {
      return undefined;
    }
    const direct = exact.get(raw) ?? normalized.get(normalizeWorkflowKey(raw));
    if (direct) {
      return direct;
    }
    const code = parseWorkflowCode(raw);
    if (!code) {
      return undefined;
    }
    const bucket = buckets[code.kind];
    if (!bucket.length) {
      return undefined;
    }
    if (code.kind === "note" && /general/i.test(raw)) {
      return bucket[bucket.length - 1];
    }
    const index = Math.max(0, Math.min(bucket.length - 1, code.ordinal - 1));
    return bucket[index];
  }

  function label(value?: string) {
    const node = resolve(value);
    const main = node?.title || node?.question || readableWorkflowEndpoint(value);
    const meta = [node?.actor, node?.phase].filter(Boolean).join(" / ");
    return meta ? `${main} (${meta})` : main;
  }

  return { label, resolve };
}

function buildWorkflowEdgeReviewSummary(graph?: WorkflowGraphMetadata, graphUnit?: ExtractionUnit) {
  const edges = graph?.edges ?? [];
  let total = 0;
  let reviewed = 0;
  let rejected = 0;
  let missingReason = 0;
  edges.forEach((edge) => {
    if (!isDecisionWorkflowEdge(edge, graph)) {
      return;
    }
    total += 1;
    const review = workflowEdgeReview(graphUnit, edge);
    if (review.status === "rejected") {
      rejected += 1;
      return;
    }
    if (review.status === "confirmed") {
      reviewed += 1;
      return;
    }
    if (review.status === "acknowledged") {
      if (review.reason) {
        reviewed += 1;
      } else {
        missingReason += 1;
      }
    }
  });
  return {
    blockingCount: Math.max(0, total - reviewed),
    missingReason,
    rejected,
    reviewed,
    total,
  };
}

function workflowEdgeReview(graphUnit: ExtractionUnit | undefined, edge: WorkflowEdgeMetadata) {
  const reviews = graphUnit?.metadata.workflow_edge_reviews;
  const review = reviews && typeof reviews === "object" && !Array.isArray(reviews)
    ? (reviews as Record<string, { reason?: string; status?: string }>)[workflowEdgeKey(edge)]
    : undefined;
  return {
    reason: String(review?.reason ?? edge.review_reason ?? "").trim(),
    status: String(review?.status ?? edge.review_status ?? "").trim(),
  };
}

function workflowEdgeKey(edge: WorkflowEdgeMetadata) {
  return `${String(edge.from_node ?? "").trim()}|${String(edge.condition ?? "").trim().toLowerCase()}|${String(edge.to_node ?? "").trim()}`;
}

function isDecisionWorkflowEdge(edge: WorkflowEdgeMetadata, graph?: WorkflowGraphMetadata) {
  const condition = normalizeWorkflowKey(String(edge.condition ?? ""));
  if (["yes", "no", "co", "khong", "dung", "sai"].includes(condition) || condition.includes("no response") || condition.includes("khong phan hoi")) {
    return true;
  }
  const fromNodeId = String(edge.from_node ?? "").trim();
  const node = graph?.nodes?.find((item) => item.id === fromNodeId);
  if (node && isDecisionWorkflowNode(node)) {
    return true;
  }
  return normalizeWorkflowKey(fromNodeId).includes("decision");
}

function isDecisionWorkflowNode(node: WorkflowNodeMetadata) {
  const haystack = normalizeWorkflowKey(`${node.id ?? ""} ${node.type ?? ""} ${node.title ?? ""} ${node.question ?? ""}`);
  return haystack.includes("decision") || haystack.includes("quyet dinh") || Boolean(node.question) || haystack.includes("?");
}

function classifyWorkflowNode(node: WorkflowNodeMetadata, index: number, nodeCount: number) {
  const raw = normalizeWorkflowKey(`${node.id || ""} ${node.type || ""} ${node.title || ""} ${node.question || ""}`);
  const kinds: WorkflowNodeKind[] = [];
  if (raw.includes("start") || raw.includes("bat dau") || index === 0) {
    kinds.push("start");
  }
  if (raw.includes("end") || raw.includes("ket thuc") || index === nodeCount - 1) {
    kinds.push("end");
  }
  if (raw.includes("decision") || raw.includes("quyet dinh") || Boolean(node.question) || raw.includes("?")) {
    kinds.push("decision");
  }
  if (raw.includes("script") || raw.includes("macro")) {
    kinds.push("script");
  }
  if (raw.includes("note") || raw.includes("luu y")) {
    kinds.push("note");
  }
  if (raw.includes("order history")) {
    kinds.push("orderHistory");
  }
  if (!kinds.some((kind) => ["decision", "script", "note", "orderHistory", "start", "end"].includes(kind))) {
    kinds.push("step");
  }
  return kinds;
}

function parseWorkflowCode(value: string) {
  const normalized = value.replace(/^x[_-]?/i, "").replace(/[_-]+/g, " ");
  if (/^start$/i.test(normalized)) {
    return { kind: "start" as const, ordinal: 1 };
  }
  if (/^end$/i.test(normalized)) {
    return { kind: "end" as const, ordinal: 1 };
  }
  if (/order history/i.test(normalized)) {
    return { kind: "orderHistory" as const, ordinal: 1 };
  }
  const match = normalized.match(/^(step|decision|script|note)\s*([0-9]+)?/i);
  if (!match) {
    return null;
  }
  const kindByCode = {
    decision: "decision",
    note: "note",
    script: "script",
    step: "step",
  } as const;
  return {
    kind: kindByCode[match[1].toLowerCase() as keyof typeof kindByCode],
    ordinal: Number(match[2] || 1),
  };
}

function readableWorkflowEndpoint(value?: string) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "Unknown step";
  }
  return raw
    .replace(/^x[_-]?/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\b([a-z])/g, (match) => match.toUpperCase());
}

function normalizeWorkflowKey(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9?]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isDocumentLayer(unit: ExtractionUnit) {
  return unit.unit_type === "full_sop" || unit.metadata.retrieval_scope === "document";
}

function hasRiskSignal(unit: ExtractionUnit) {
  const haystack = `${unit.unit_type} ${unit.title} ${JSON.stringify(unit.metadata)}`.toLowerCase();
  return haystack.includes("risk") || haystack.includes("security") || haystack.includes("compliance") || haystack.includes("high");
}

function hasEffectiveDateSignal(unit: ExtractionUnit) {
  const haystack = `${unit.title} ${unit.content} ${JSON.stringify(unit.metadata)}`.toLowerCase();
  return haystack.includes("effective") || haystack.includes("hiệu lực") || haystack.includes("hieu luc") || haystack.includes("needs_review");
}

function sourceReference(unit: ExtractionUnit) {
  if (unit.source_sheet) {
    return unit.source_row ? `${unit.source_sheet} row ${unit.source_row}` : unit.source_sheet;
  }
  if (unit.source_page) {
    return `page ${unit.source_page}`;
  }
  return "";
}

function requiredUnitTypesFromExtraction(...units: Array<ExtractionUnit | undefined>) {
  const values = new Set<string>();
  units.forEach((unit) => {
    if (!unit) {
      return;
    }
    collectRequiredUnitTypes(unit.metadata.required_unit_types, values);
    collectRequiredUnitTypes(unit.metadata.publish_required_unit_types, values);
    const documentMetadata = unit.metadata.document_metadata;
    if (documentMetadata && typeof documentMetadata === "object" && !Array.isArray(documentMetadata)) {
      const metadata = documentMetadata as Record<string, unknown>;
      collectRequiredUnitTypes(metadata.required_unit_types, values);
      collectRequiredUnitTypes(metadata.publish_required_unit_types, values);
    }
    const readiness = unit.metadata.publish_readiness;
    if (readiness && typeof readiness === "object" && !Array.isArray(readiness)) {
      const readinessRecord = readiness as Record<string, unknown>;
      collectRequiredUnitTypes(readinessRecord.required_unit_types ?? readinessRecord.required_units, values);
    }
  });
  return [...values].map((unitType) => ({
    key: unitType,
    label: readableUnitType(unitType),
    types: unitType === "decision_rule" ? ["decision_rule", "decision_point"] : [unitType],
  }));
}

function candidateUnitsForRequirement(required: RequiredWorkflowUnit, units: ExtractionUnit[]) {
  const tokens = requirementTokens(required);
  return units
    .filter((unit) => !required.types.includes(unit.unit_type))
    .map((unit) => {
      const haystack = normalizeWorkflowKey(`${unit.unit_type} ${unit.title} ${unit.content} ${JSON.stringify(unit.metadata)}`);
      const tokenScore = tokens.reduce((score, token) => score + (haystack.includes(token) ? 1 : 0), 0);
      const candidateBoost = unit.unit_type.startsWith("candidate_") || unit.review_status === "needs_review" ? 1 : 0;
      return { score: tokenScore + candidateBoost, unit };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score || left.unit.unit_index - right.unit.unit_index)
    .slice(0, 3)
    .map((item) => item.unit);
}

function requirementTokens(required: RequiredWorkflowUnit) {
  const base = `${required.key} ${required.label}`;
  return normalizeWorkflowKey(base)
    .split(" ")
    .filter((token) => token.length >= 4);
}

function buildWorkflowRequirementConversion(
  unit: ExtractionUnit,
  requirement: RequiredWorkflowUnit,
  defaultEffectiveFrom: string,
): ExtractionUnitUpdate {
  return {
    title: unit.title.trim() || requirement.label,
    content: unit.content.trim(),
    unit_type: requirement.key,
    confidence: Math.max(0.55, Number(unit.confidence) || 0.55),
    review_status: "needs_review",
    actor: "cs-ops-ui",
    metadata: {
      ...unit.metadata,
      converted_from_unit_type: unit.unit_type,
      effective_from: String(unit.metadata.effective_from ?? defaultEffectiveFrom),
      required_workflow_unit: true,
      required_workflow_unit_key: requirement.key,
      review_status: "needs_review",
      unit_type: requirement.key,
    },
  };
}

function buildWorkflowRequirementStub(
  requirement: RequiredWorkflowUnit,
  selectedDocument: DocumentSummary | null,
  selectedVersion: VersionSummary,
  defaultEffectiveFrom: string,
): ExtractionUnitCreate {
  const isWorkflow = selectedDocument?.latest_document_type === "workflow_diagram";
  return {
    title: requirement.label,
    content: `TODO: Curate ${requirement.label} from the source evidence before approval. Do not publish this placeholder.`,
    unit_type: requirement.key,
    confidence: 0.5,
    review_status: "needs_review",
    actor: "cs-ops-ui",
    metadata: {
      created_from_readiness_panel: true,
      document_type: selectedDocument?.latest_document_type ?? selectedVersion.document_type ?? "workflow_diagram",
      effective_from: defaultEffectiveFrom,
      manual_curation_status: "created_stub",
      required_workflow_unit: true,
      required_workflow_unit_key: requirement.key,
      review_status: "needs_review",
      source_evidence_only: true,
      source_page: isWorkflow ? 1 : undefined,
      page_number: isWorkflow ? 1 : undefined,
      source_ref_acknowledged: false,
      source_ref_quality: isWorkflow ? "page_only" : "none",
      unit_type: requirement.key,
    },
  };
}

function buildWorkflowGraphAcknowledgement(unit: ExtractionUnit, reason: string): ExtractionUnitUpdate {
  const reviewStatus = unit.review_status === "approved" ? "approved" : "reviewed";
  return {
    title: unit.title,
    content: unit.content,
    unit_type: unit.unit_type,
    confidence: unit.confidence,
    review_status: reviewStatus,
    actor: "cs-lead-ui",
    metadata: {
      ...unit.metadata,
      graph_validation_acknowledged: true,
      graph_validation_acknowledged_at: new Date().toISOString(),
      graph_validation_acknowledged_by: "cs-lead-ui",
      graph_validation_acknowledged_reason: reason,
      review_status: reviewStatus,
      source_ref_acknowledged: unit.metadata.source_ref_quality === "page_only" ? true : unit.metadata.source_ref_acknowledged,
      unit_type: unit.unit_type,
    },
  };
}

function buildWorkflowEdgeReviewUpdate(
  unit: ExtractionUnit,
  edge: WorkflowEdgeMetadata,
  status: "acknowledged" | "confirmed" | "rejected",
  reason: string,
): ExtractionUnitUpdate {
  const now = new Date().toISOString();
  const reviews = {
    ...(typeof unit.metadata.workflow_edge_reviews === "object" && !Array.isArray(unit.metadata.workflow_edge_reviews)
      ? unit.metadata.workflow_edge_reviews as Record<string, unknown>
      : {}),
  };
  reviews[workflowEdgeKey(edge)] = {
    condition: edge.condition ?? "",
    from_node: edge.from_node ?? "",
    reason,
    reviewed_at: now,
    reviewed_by: "cs-lead-ui",
    status,
    to_node: edge.to_node ?? "",
  };
  return {
    title: unit.title,
    content: unit.content,
    unit_type: unit.unit_type,
    confidence: unit.confidence,
    review_status: unit.review_status === "approved" ? "approved" : "reviewed",
    actor: "cs-lead-ui",
    metadata: {
      ...unit.metadata,
      review_status: unit.review_status === "approved" ? "approved" : "reviewed",
      unit_type: unit.unit_type,
      workflow_edge_reviews: reviews,
      workflow_edge_reviews_updated_at: now,
      workflow_edge_reviews_updated_by: "cs-lead-ui",
    },
  };
}

function workflowRequirementGuidance(unitType: string) {
  const guidance: Record<string, string> = {
    workflow_overview: "Short document-level workflow summary for quick orientation. It should not replace the full SOP page.",
    verification_dependency: "Dependency or prerequisite evidence, for example which source rule, account verification rule, or related policy must be checked first.",
    decision_point: "A decision question with clear branch outcomes. For workflow diagrams, Yes/No paths should be human-confirmed.",
    decision_rule: "A decision question with clear branch outcomes. For workflow diagrams, Yes/No paths should be human-confirmed.",
    related_document: "Related SOP, policy, source file, or dependency that an agent or lead must open for the complete context.",
  };
  return guidance[unitType] ?? "Required by extraction metadata for this workflow. Curate it from source evidence, then mark reviewed or approved.";
}

function collectRequiredUnitTypes(value: unknown, output: Set<string>) {
  if (!Array.isArray(value)) {
    return;
  }
  value.forEach((item) => {
    const unitType = String(item || "").trim();
    if (unitType) {
      output.add(unitType);
    }
  });
}

function readableUnitType(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizedRawTextName(value: string) {
  const trimmed = value.trim() || "raw-sop-draft.md";
  const safeName = trimmed
    .replace(/[\\/]+/g, "-")
    .replace(/\s+/g, "-")
    .replace(/[^a-zA-Z0-9._-]+/g, "")
    .replace(/^-+|-+$/g, "");
  if (!safeName) {
    return "raw-sop-draft.md";
  }
  return /\.(txt|md|markdown)$/i.test(safeName) ? safeName : `${safeName}.md`;
}
