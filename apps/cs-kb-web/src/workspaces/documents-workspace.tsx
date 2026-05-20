import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import {
  IconArchive as Archive,
  IconBook as BookOpen,
  IconCircleCheck as CheckCircle2,
  IconHelpCircle as CircleHelp,
  IconClipboardList as ClipboardList,
  IconDatabase as Database,
  IconFileText as FileText,
  IconGitBranch as GitBranch,
  IconHistory as History,
  IconLayersIntersect as Layers3,
  IconLoader2 as Loader2,
  IconMessage as MessageSquareText,
  IconNetwork as Network,
  IconPlus as Plus,
  IconRefresh as RefreshCw,
  IconSearch as Search,
  IconShieldCheck as ShieldCheck,
  IconAlertTriangle as TriangleAlert,
  IconUpload as Upload,
  IconWand as WandSparkles
} from "@tabler/icons-react";

import { DraftRetrievalPreview, ExtractionPipelineTrace, PublishTaskList, SopQualityAuditPanel, buildPublishTasks, buildSopQualityAudit } from "@/components/documents-review-insights";
import { DocumentFact, ReadinessCheck } from "@/components/operations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyPanel, Field, MetaLine, StatusBadge, TagSummary } from "@/components/common";
import { DatePicker } from "@/components/date-picker";
import { ExtractionReviewEditor } from "@/components/extraction-review-editor";
import { API_BASE_URL } from "@/config";
import { workspacePaths } from "@/constants";
import { nextReviewDueIso, withReviewFrequencyDates } from "@/lib/date";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentChunk, DocumentMetadataPreview, DocumentSummary, ExtractionJobSummary, ExtractionPipelineInspection, ExtractionUnit, ExtractionUnitCreate, ExtractionUnitUpdate, KBCollectionSummary, PublishReadiness, UploadState, VersionRawText, VersionSummary } from "@/types";

type WorkflowGraphMetadata = {
  workflow_id?: string;
  title?: string;
  start_node_id?: string;
  graph_confidence?: number;
  fidelity_score?: number;
  graph_fidelity_score?: number;
  selected_flow?: string;
  repair_applied?: boolean;
  decision_edges_review_required?: number;
  missing_terminal_edges?: string[];
  orphan_annotations?: string[];
  unresolved_relations?: Array<{ target_title?: string; relation_type?: string; evidence_text?: string }>;
  visible_step_codes?: string[];
  covered_step_codes?: string[];
  missing_step_codes?: string[];
  detector_conflicts?: string[];
  topology_source?: string;
  requires_human_review?: boolean;
  review_reason?: string;
  nodes?: Array<{ id?: string; type?: string; semantic_node_type?: string; step_code?: string; shape_kind?: string; terminal_state?: string; actor?: string; phase?: string; title?: string; content?: string; question?: string }>;
  edges?: Array<{ from_node?: string; to_node?: string; condition?: string; confidence?: number; reason?: string; review_reason?: string; review_status?: string; topology_status?: string }>;
  annotations?: Array<{ id?: string; type?: string; attached_to?: string; attached_to_node_ids?: string[]; title?: string; content?: string; risk_level?: string }>;
  uncertain_edges?: Array<{ from_node?: string; to_node?: string; condition?: string; reason?: string; confidence?: number; review_status?: string; topology_status?: string }>;
  validation_errors?: string[];
};
type WorkflowEdgeMetadata = NonNullable<WorkflowGraphMetadata["edges"]>[number];
type WorkflowNodeMetadata = NonNullable<WorkflowGraphMetadata["nodes"]>[number];
type WorkflowNodeKind = "decision" | "end" | "note" | "orderHistory" | "script" | "start" | "step";
type DocumentStep =
  | "assign"
  | "backendGate"
  | "chunks"
  | "evidence"
  | "kbIndex"
  | "pipeline"
  | "publish"
  | "quality"
  | "readiness"
  | "sop"
  | "units"
  | "view"
  | "workflowGraph"
  | "workflowRequirements";
type ReviewFilter = "needs_review" | "reviewed" | "approved" | "rejected" | "source_refs" | "atomic" | "all";
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
type SourceEvidenceViewPayload = {
  coverage_report?: Record<string, unknown>;
  formatter?: string;
  markdown?: string;
  markdown_truncated?: boolean;
  model?: string;
  raw_text_chars?: number;
  sections?: Array<Record<string, unknown>>;
  title?: string;
  warnings?: string[];
};
type KBIndexPlanPayload = {
  collections?: Array<Record<string, unknown>>;
  issue_router_units?: Array<Record<string, unknown>>;
  sop_references?: Array<Record<string, unknown>>;
  tool_links?: Array<Record<string, unknown>>;
  action_templates?: Array<Record<string, unknown>>;
  unresolved_targets?: Array<Record<string, unknown>>;
  summary?: Record<string, number | string>;
};

export function DocumentsWorkspace({
  busyKey,
  chunks,
  chunksLoading,
  collections,
  deletingUnitId,
  documents,
  extractionUnits,
  extractionUnitsLoading,
  extractionPipeline,
  extractionPipelineInspection,
  extractionPipelineLoading,
  onArchiveDocument,
  onApplyCollection,
  onBulkReviewVersion,
  onCreateExtractionUnit,
  onDeleteExtractionUnit,
  onInspectVersion,
  onFileSelected,
  onPublishVersion,
  onRefreshDocuments,
  onRetryIndexing,
  onSelectDocument,
  onUpdateExtractionUnit,
  onUpload,
  metadataPreview,
  publishReadiness,
  publishReadinessLoading,
  selectedDocument,
  selectedChunkVersionId,
  savingUnitId,
  setSelectedDocument,
  setUpload,
  surface = "review",
  upload,
  versionRaw,
  versionRawLoading,
  versions,
}: {
  busyKey: string;
  chunks: DocumentChunk[];
  chunksLoading: boolean;
  collections: KBCollectionSummary[];
  deletingUnitId: string;
  documents: DocumentSummary[];
  extractionUnits: ExtractionUnit[];
  extractionUnitsLoading: boolean;
  extractionPipeline: ExtractionJobSummary[];
  extractionPipelineInspection: ExtractionPipelineInspection | null;
  extractionPipelineLoading: boolean;
  onArchiveDocument: (document: DocumentSummary) => void;
  onApplyCollection: (units: ExtractionUnit[], collection: KBCollectionSummary | null) => void;
  onBulkReviewVersion: (versionId: string, scope?: "all" | "atomic", reviewStatus?: "reviewed" | "approved", force?: boolean) => void;
  onCreateExtractionUnit: (versionId: string, unit: ExtractionUnitCreate) => void;
  onDeleteExtractionUnit: (unit: ExtractionUnit) => void;
  onInspectVersion: (versionId: string) => void;
  onFileSelected: (file: File | null) => void;
  onPublishVersion: (versionId: string, force?: boolean) => void;
  onRefreshDocuments: () => void;
  onRetryIndexing: (versionId: string) => void;
  onSelectDocument: (documentId: string) => void;
  onUpload: () => void;
  metadataPreview: DocumentMetadataPreview | null;
  publishReadiness: PublishReadiness | null;
  publishReadinessLoading: boolean;
  selectedDocument: DocumentSummary | null;
  selectedChunkVersionId: string;
  setSelectedDocument: (document: DocumentSummary) => void;
  setUpload: Dispatch<SetStateAction<UploadState>>;
  surface?: "queue" | "review" | "upload";
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
  const selectedDocumentGovernance = selectedDocument ? documentGovernanceDefaults(selectedDocument) : undefined;
  const selectedDocumentTitle = selectedDocument?.title || upload.title || "published SOP";
  const [sourceMode, setSourceMode] = useState<"file" | "text">("file");
  const [confirmingPublishVersionId, setConfirmingPublishVersionId] = useState("");
  const [confirmingForcePublishVersionId, setConfirmingForcePublishVersionId] = useState("");
  const [rawTextError, setRawTextError] = useState("");
  const [rawTextName, setRawTextName] = useState("raw-sop-draft.md");
  const [rawTextStats, setRawTextStats] = useState({ bytes: 0, chars: 0, lines: 0 });
  const [sourceFilter, setSourceFilter] = useState<"active" | "archived" | "all">("active");
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("needs_review");
  const [documentStep, setDocumentStep] = useState<DocumentStep>("view");
  const [requiredUnitFocus, setRequiredUnitFocus] = useState<RequiredWorkflowUnit | null>(null);
  const activeDocuments = documents.filter((document) => document.status === "active");
  const archivedDocuments = documents.filter((document) => document.status === "archived");
  const visibleDocuments = documents.filter((document) => {
    if (sourceFilter === "all") {
      return true;
    }
    return document.status === sourceFilter;
  });
  const activeExtractionUnits = extractionUnits.filter((unit) => !isRejectedExtractionUnit(unit));
  const documentLayerUnits = extractionUnits.filter(isDocumentLayer);
  const activeDocumentLayerUnits = activeExtractionUnits.filter(isDocumentLayer);
  const fullSopUnit = activeDocumentLayerUnits.find((unit) => unit.unit_type === "full_sop") ?? activeDocumentLayerUnits[0];
  const sourceEvidenceUnits = extractionUnits.filter(isSourceEvidenceUnit);
  const workflowGraphUnit = activeExtractionUnits.find(isWorkflowGraphUnit);
  const workflowGraphUnits = extractionUnits.filter((unit) => !isDocumentLayer(unit) && !isSourceEvidenceUnit(unit) && isWorkflowGraphUnit(unit));
  const workflowGraph = workflowGraphUnit?.metadata.workflow_graph as WorkflowGraphMetadata | undefined;
  const sourceEvidenceView = useMemo(() => sourceEvidenceViewPayload(extractionPipeline), [extractionPipeline]);
  const workflowGraphValidationErrors = workflowGraph?.validation_errors ?? workflowGraphUnit?.metadata.graph_validation_errors ?? [];
  const workflowGraphUncertainEdges = workflowGraph?.uncertain_edges ?? workflowGraphUnit?.metadata.uncertain_edges ?? [];
  const workflowEdgeReviewSummary = buildWorkflowEdgeReviewSummary(workflowGraph, workflowGraphUnit);
  const atomicUnits = extractionUnits.filter((unit) => !isDocumentLayer(unit) && !isSourceEvidenceUnit(unit) && !isWorkflowGraphUnit(unit));
  const activeAtomicUnits = activeExtractionUnits.filter((unit) => !isDocumentLayer(unit) && !isSourceEvidenceUnit(unit) && !isWorkflowGraphUnit(unit));
  const suggestedUploadCollection = collections.find((collection) => collection.slug === upload.suggestedCollectionSlug);
  const selectedIsArchived = selectedDocument?.status === "archived";
  const pendingReviewCount = extractionUnits.filter((unit) => unit.review_status === "needs_review").length;
  const pendingAtomicReviewCount = atomicUnits.filter((unit) => unit.review_status === "needs_review").length;
  const highRiskUnitCount = activeExtractionUnits.filter(hasRiskSignal).length;
  const effectiveDateReviewed = activeExtractionUnits.some(hasEffectiveDateSignal);
  const defaultEffectiveFrom = inferredEffectiveFrom(activeExtractionUnits, selectedDocument, selectedVersion);
  const ownerAssigned = Boolean(selectedDocument?.metadata?.owner_team || selectedDocument?.metadata?.ownerTeam);
  const policyRequiresGovernance = ["policy_rule", "policy_table"].includes(String(selectedDocument?.latest_document_type ?? ""));
  const workflowRequiresGraph = selectedDocument?.latest_document_type === "workflow_diagram";
  const isKbIndexWorkbook = selectedDocument?.latest_document_type === "kb_index_workbook";
  const kbIndexPlan = useMemo(() => kbIndexPlanPayload(extractionPipeline), [extractionPipeline]);
  const selectedExtractionIssue = extractionIssue(selectedDocument);
  const workflowGraphConfidence = Number(workflowGraphUnit?.metadata.graph_confidence ?? workflowGraph?.graph_confidence ?? workflowGraphUnit?.confidence ?? 0);
  const workflowGraphLowConfidence = workflowRequiresGraph && Boolean(workflowGraphUnit) && workflowGraphConfidence > 0 && workflowGraphConfidence < 0.7;
  const workflowGraphWarningIssueCount =
    (Array.isArray(workflowGraphValidationErrors) ? workflowGraphValidationErrors.length : 0) +
    Math.max(Array.isArray(workflowGraphUncertainEdges) ? workflowGraphUncertainEdges.length : 0, Number(workflowGraphUnit?.metadata.uncertain_edges_count ?? 0)) +
    (workflowGraphLowConfidence ? 1 : 0);
  const workflowGraphAcknowledgementReason = String(workflowGraphUnit?.metadata.graph_validation_acknowledged_reason ?? "").trim();
  const workflowGraphWarningsAcknowledged =
    workflowGraphWarningIssueCount === 0 ||
    (workflowGraphUnit?.metadata.graph_validation_acknowledged === true && workflowGraphAcknowledgementReason.length > 0);
  const workflowGraphIssueCount = (workflowGraphWarningsAcknowledged ? 0 : workflowGraphWarningIssueCount) + workflowEdgeReviewSummary.blockingCount;
  const workflowGraphIssuesAcknowledged = workflowGraphIssueCount === 0;
  const pageOnlySourceRefUnacknowledged = activeExtractionUnits.filter(
    (unit) => unit.metadata.source_ref_quality === "page_only" && unit.metadata.source_ref_acknowledged !== true,
  ).length;
  const requiredWorkflowUnits = requiredUnitTypesFromExtraction(workflowGraphUnit, fullSopUnit);
  const missingWorkflowUnits = requiredWorkflowUnits.filter(
    (required) => !activeExtractionUnits.some((unit) => required.types.includes(unit.unit_type) && isReviewedExtractionUnit(unit)),
  );
  const showKbIndexTab = isKbIndexWorkbook;
  const workflowRequirementStatuses = requiredWorkflowUnits.map((required) => {
    const matchingUnits = activeExtractionUnits.filter((unit) => required.types.includes(unit.unit_type));
    const reviewedUnits = matchingUnits.filter(isReviewedExtractionUnit);
    const status: WorkflowRequirementStatus["status"] = reviewedUnits.length ? "ready" : matchingUnits.length ? "needs_review" : "missing";
    return {
      ...required,
      candidateUnits: candidateUnitsForRequirement(required, activeAtomicUnits),
      matchingUnits,
      reviewedUnits,
      status,
    };
  });
  const validationRuleCount = activeExtractionUnits.filter((unit) => unit.unit_type === "validation_rule").length;
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
    rejected: extractionUnits.filter((unit) => unit.review_status === "rejected").length,
    source_refs: pageOnlySourceRefUnacknowledged,
    atomic: atomicUnits.length,
    all: extractionUnits.length,
  };
  const readinessChecks = [
    {
      detail: fullSopUnit ? fullSopUnit.title : "Missing document-level layer",
      label: "Document overview",
      passed: Boolean(fullSopUnit),
    },
    {
      detail: activeAtomicUnits.length ? `${activeAtomicUnits.length} searchable units` : "No quick-answer units",
      label: "Atomic retrieval units",
      passed: activeAtomicUnits.length > 0,
    },
    {
      detail: workflowGraphUnit
        ? workflowGraphIssuesAcknowledged
          ? `${workflowGraph?.nodes?.length ?? 0} nodes, ${workflowEdgeReviewSummary.reviewed}/${workflowEdgeReviewSummary.total} decision edges reviewed, ${Math.round(workflowGraphConfidence * 100)}% confidence${workflowGraphLowConfidence ? " accepted by reviewer" : ""}`
          : `${workflowGraphIssueCount} topology or decision edge issue(s) need review`
        : "Workflow graph missing",
      label: "Workflow graph reviewed",
      passed: !workflowRequiresGraph || Boolean(workflowGraphUnit && isReviewedExtractionUnit(workflowGraphUnit) && (workflowGraph?.edges?.length ?? 0) > 0 && workflowGraphIssuesAcknowledged && workflowEdgeReviewSummary.blockingCount === 0),
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
    atomicUnits: activeAtomicUnits,
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
  const filteredDocumentLayerUnits = documentLayerUnits.filter((unit) => unitMatchesReviewFilter(unit, reviewFilter, false));
  const filteredWorkflowGraphUnits = workflowGraphUnits.filter((unit) => unitMatchesReviewFilter(unit, reviewFilter, false));
  const filteredAtomicUnits = atomicUnits.filter((unit) => unitMatchesReviewFilter(unit, reviewFilter, true));
  const focusedRequiredUnits = requiredUnitFocus
    ? filteredAtomicUnits.filter((unit) => requiredUnitFocus.types.includes(unit.unit_type))
    : [];
  const filteredUnitsCount = filteredDocumentLayerUnits.length + filteredWorkflowGraphUnits.length + filteredAtomicUnits.length;
  const reviewEmptyState = reviewFilterEmptyState(reviewFilter);
  const canBulkApproveVisible = Boolean(selectedVersion) && canEditSelectedVersion && filteredUnitsCount > 0 && !bulkReviewBlocked;
  const bulkApproveScope: "all" | "atomic" = reviewFilter === "atomic" ? "atomic" : "all";
  const bulkApproveLabel = bulkApproveScope === "atomic" ? "Approve all atomic units" : "Approve all units";

  useEffect(() => {
    const allowedSteps = new Set<DocumentStep>(["view", "assign", "evidence", "units", "sop", "backendGate", "readiness", "quality", "publish", "pipeline", "chunks"]);
    if (requiredWorkflowUnits.length) {
      allowedSteps.add("workflowRequirements");
    }
    if (workflowRequiresGraph || workflowGraphUnits.length > 0) {
      allowedSteps.add("workflowGraph");
    }
    if (showKbIndexTab) {
      allowedSteps.add("kbIndex");
    }
    if (!allowedSteps.has(documentStep)) {
      setDocumentStep("view");
    }
  }, [documentStep, requiredWorkflowUnits.length, showKbIndexTab, workflowGraphUnits.length, workflowRequiresGraph]);

  function focusReviewRequirement(requirement: RequiredWorkflowUnit) {
    setRequiredUnitFocus(requirement);
    setReviewFilter("needs_review");
    setDocumentStep("units");
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

  const isReviewSurface = surface === "review";

  return (
    <div
      className={cn(
        "grid gap-4",
        isReviewSurface ? "mx-auto max-w-7xl" : surface === "upload" ? "mx-auto max-w-2xl" : "mx-auto max-w-5xl",
      )}
    >
      {!isReviewSurface ? (
      <aside className="space-y-4">
        {surface !== "queue" ? (
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div>
              <CardTitle>New source</CardTitle>
              <CardDescription>Step 1 of 3: upload as draft. Review and publish happen after extraction.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 pt-4">
            <StepRail
              current="upload"
              steps={[
                { key: "upload", label: "Upload" },
                { key: "queue", label: "Queue" },
                { key: "review", label: "Review" },
              ]}
            />
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
            <details className="order-20 rounded-lg border bg-muted/10 p-3">
              <summary className="cursor-pointer text-sm font-medium">Optional metadata</summary>
              <div className="mt-3 space-y-4">
                <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
                  <Field label="Vertical" value={upload.vertical} onChange={(vertical) => setUpload((current) => ({ ...current, vertical }))} />
                  <Field label="Audience" value={upload.audience} onChange={(audience) => setUpload((current) => ({ ...current, audience }))} placeholder="customer, driver" />
                  <Field label="Category" value={upload.category} onChange={(category) => setUpload((current) => ({ ...current, category }))} />
                  <Field label="Owner team" value={upload.ownerTeam} onChange={(ownerTeam) => setUpload((current) => ({ ...current, ownerTeam }))} />
                </div>
                <div className="rounded-lg border bg-background p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-semibold text-foreground">Primary collection</div>
                      <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                        AI can suggest, but only approved/manual selection is used by Lookup and Chat.
                      </p>
                    </div>
                    <Badge variant={upload.collectionAssignmentStatus === "approved" ? "secondary" : "outline"}>
                      {upload.collectionAssignmentStatus === "approved" ? "approved" : upload.collectionAssignmentStatus === "suggested" ? "AI suggested" : "optional"}
                    </Badge>
                  </div>
                  <Select
                    onValueChange={(value) => {
                      if (value === "none") {
                        setUpload((current) => ({
                          ...current,
                          collectionSlug: "",
                          collectionName: "",
                          collectionType: "",
                          collectionAssignmentStatus: "unassigned",
                          collectionSource: "manual",
                          collectionConfidence: 0,
                        }));
                        return;
                      }
                      const collection = collections.find((item) => item.slug === value);
                      setUpload((current) => ({
                        ...current,
                        collectionSlug: collection?.slug ?? value,
                        collectionName: collection?.name ?? value,
                        collectionType: collection?.collection_type ?? "domain",
                        collectionAssignmentStatus: "approved",
                        collectionSource: "manual",
                        collectionConfidence: 1,
                      }));
                    }}
                    value={upload.collectionSlug || "none"}
                  >
                    <SelectTrigger className="h-9 rounded-full bg-background">
                      <SelectValue placeholder="No collection" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No collection yet</SelectItem>
                      {collections.map((collection) => (
                        <SelectItem key={collection.id} value={collection.slug}>
                          {collection.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {upload.suggestedCollectionSlug ? (
                    <div className="mt-2 rounded-lg border bg-background px-3 py-2 text-xs leading-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-muted-foreground">
                          AI suggested: <span className="font-semibold text-foreground">{suggestedUploadCollection?.name ?? upload.suggestedCollectionName ?? upload.suggestedCollectionSlug}</span>
                          {upload.suggestedCollectionConfidence ? ` · ${Math.round(upload.suggestedCollectionConfidence * 100)}%` : ""}
                        </span>
                        <Button
                          className="h-7 rounded-full px-2"
                          onClick={() => {
                            const collection = suggestedUploadCollection;
                            setUpload((current) => ({
                              ...current,
                              collectionSlug: collection?.slug ?? current.suggestedCollectionSlug,
                              collectionName: collection?.name ?? current.suggestedCollectionName,
                              collectionType: collection?.collection_type ?? current.suggestedCollectionType,
                              collectionAssignmentStatus: "approved",
                              collectionSource: "ai_suggestion_approved",
                              collectionConfidence: current.suggestedCollectionConfidence || 0.7,
                            }));
                          }}
                          size="sm"
                          type="button"
                          variant="secondary"
                        >
                          Approve suggestion
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="rounded-lg border bg-background p-3">
                  <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-foreground">
                    <ShieldCheck className="size-4" />
                    Owner review SLA
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
                    <GovernanceSelect
                      label="Risk level"
                      onChange={(riskLevel) => setUpload((current) => ({ ...current, riskLevel }))}
                      options={["low", "medium", "high", "critical"]}
                      placeholder="Unset risk"
                      value={upload.riskLevel}
                    />
                    <GovernanceSelect
                      label="Review frequency"
                      onChange={(reviewFrequency) => setUpload((current) => withReviewFrequencyDates(current, reviewFrequency))}
                      options={["quarterly", "semiannual", "annual"]}
                      placeholder="Unset frequency"
                      value={upload.reviewFrequency}
                    />
                    <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                      Last reviewed
                      <DatePicker
                        label="Last reviewed"
                        onChange={(lastReviewedAt) => setUpload((current) => ({
                          ...current,
                          lastReviewedAt,
                          nextReviewDue: current.reviewFrequency ? nextReviewDueIso(lastReviewedAt, current.reviewFrequency) : current.nextReviewDue,
                        }))}
                        placeholder="Pick last review date"
                        value={upload.lastReviewedAt}
                      />
                    </label>
                    <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
                      Next review due
                      <DatePicker
                        label="Next review due"
                        onChange={(nextReviewDue) => setUpload((current) => ({ ...current, nextReviewDue }))}
                        placeholder="Pick next due date"
                        value={upload.nextReviewDue}
                      />
                    </label>
                  </div>
                </div>
                <Field label="Tags" value={upload.tags} onChange={(tags) => setUpload((current) => ({ ...current, tags }))} />
                <Field label="Case reasons" value={upload.caseReasons} onChange={(caseReasons) => setUpload((current) => ({ ...current, caseReasons }))} />
              </div>
            </details>
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

            <p className="text-xs leading-5 text-muted-foreground">
              Draft extraction stays out of Lookup and AI answers until a reviewer publishes the version.
            </p>
            <Button className="w-full justify-center" disabled={busyKey === "upload" || busyKey === "metadata-preview" || !uploadReady} onClick={onUpload} type="button">
              {busyKey === "upload" ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Upload data-icon="inline-start" className="size-4" />}
              Upload draft
            </Button>
            <Button asChild className="w-full justify-center" type="button" variant="outline">
              <a href={workspacePaths.documentQueue}>Go to source queue</a>
            </Button>
          </CardContent>
        </Card>
        ) : null}

        {surface !== "upload" ? (
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <CardTitle>Source queue</CardTitle>
                <CardDescription>Step 2 of 3: choose a source to review. {activeDocuments.length} active, {archivedDocuments.length} archived.</CardDescription>
              </div>
              <div className="flex items-center gap-1">
                <Button asChild size="sm" type="button" variant="outline">
                  <a href={workspacePaths.documentUpload}>Upload</a>
                </Button>
                <Button onClick={onRefreshDocuments} size="icon" type="button" variant="ghost">
                  <RefreshCw className="size-4" />
                </Button>
              </div>
            </div>
            <StepRail
              current="queue"
              steps={[
                { key: "upload", label: "Upload" },
                { key: "queue", label: "Queue" },
                { key: "review", label: "Review" },
              ]}
            />
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
                        if (surface === "queue") {
                          const params = new URLSearchParams();
                          params.set("document", document.document_id);
                          if (document.latest_version_id) {
                            params.set("version", document.latest_version_id);
                          }
                          window.location.href = `${workspacePaths.documents}?${params.toString()}`;
                        }
                      }}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="min-w-0 text-sm font-medium leading-5">{document.title}</h3>
                        {document.status === "archived" ? <Badge className="shrink-0" variant="outline">Archived</Badge> : null}
                      </div>
                      <p className="truncate text-xs text-muted-foreground">{document.source_filename}</p>
                      <div className="flex flex-wrap gap-2">
                        <StatusBadge status={document.latest_review_status ?? "needs_review"} />
                        {extractionIssue(document) ? <Badge variant="destructive">extraction failed</Badge> : null}
                        {document.status === "archived" ? <Badge variant="outline">lookup excluded</Badge> : null}
                      </div>
                      <MetaLine
                        items={[
                          `v${document.latest_version_number ?? "-"}`,
                          document.latest_document_type ?? "unknown",
                        ]}
                      />
                    </button>
                  ))
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
        ) : null}
      </aside>
      ) : null}

      {isReviewSurface ? (
      <section className="min-w-0 space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <CardTitle>{selectedDocument?.title ?? "Select a source document"}</CardTitle>
                <CardDescription className="mt-1 truncate">
                  {selectedDocument?.source_filename ?? "Choose from the source queue to review versions, extraction units, and indexed chunks."}
                </CardDescription>
                {selectedDocument ? (
                  <MetaLine
                    className="mt-1"
                    items={[
                      `v${selectedDocument.latest_version_number ?? "-"}`,
                      selectedDocument.latest_document_type ?? "unknown type",
                    ]}
                  />
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm" type="button" variant="outline">
                  <a href={workspacePaths.documentQueue}>Source queue</a>
                </Button>
                {selectedDocument ? (
                  <>
                    <Badge variant={selectedIsArchived ? "outline" : "secondary"}>
                      {selectedIsArchived ? "archived source" : "active source"}
                    </Badge>
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
                  </>
                ) : (
                  <Button asChild size="sm" type="button" variant="secondary">
                    <a href={workspacePaths.documentUpload}>Upload source</a>
                  </Button>
                )}
              </div>
            </div>
            <StepRail
              current="review"
              steps={[
                { key: "upload", label: "Upload" },
                { key: "queue", label: "Queue" },
                { key: "review", label: "Review" },
              ]}
            />
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
                    <p className="text-sm font-semibold text-destructive">{selectedExtractionIssue.title}</p>
                    <p className="mt-1 break-words text-xs leading-5 text-destructive/90">{selectedExtractionIssue.reason}</p>
                    {selectedExtractionIssue.warnings.length ? (
                      <TagSummary className="mt-2" items={selectedExtractionIssue.warnings} maxItems={3} />
                    ) : null}
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">{selectedExtractionIssue.guidance}</p>
                  </div>
                </div>
              </div>
            ) : null}
            <div className="grid gap-3 md:grid-cols-4">
              <DocumentFact label="State" value={selectedIsArchived ? "Archived" : selectedDocument ? "Active" : "-"} />
              <DocumentFact label="Version" value={selectedDocument?.latest_version_number ? `v${selectedDocument.latest_version_number}` : "-"} />
              <DocumentFact label="Confidence" value={selectedDocument?.latest_extraction_confidence ? `${Math.round(selectedDocument.latest_extraction_confidence * 100)}%` : "-"} />
              <DocumentFact label="Layers" value={extractionUnits.length ? `1 overview + ${atomicUnits.length} units + ${sourceEvidenceUnits.length} source sections` : "-"} />
            </div>
          </CardContent>
        </Card>

        <Tabs className="space-y-4" onValueChange={(value) => setDocumentStep(value as DocumentStep)} value={documentStep}>
          <div className="sticky top-4 z-20 rounded-xl border bg-background/95 p-2 shadow-sm backdrop-blur">
            <TabsList className="flex h-auto w-full flex-wrap gap-1 bg-muted/30 p-1">
              <TabsTrigger className="min-w-20 flex-1" value="view">Source</TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1" value="assign">Assign</TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1" value="evidence">Evidence</TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1 gap-2" value="units">
                Units
                {pendingReviewCount ? (
                  <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {pendingReviewCount}
                  </span>
                ) : null}
              </TabsTrigger>
              {requiredWorkflowUnits.length ? (
                <TabsTrigger className="min-w-28 flex-1 gap-2" value="workflowRequirements">
                  Requirements
                  {workflowGraphIssueCount || missingWorkflowUnits.length ? (
                    <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {workflowGraphIssueCount + missingWorkflowUnits.length}
                    </span>
                  ) : null}
                </TabsTrigger>
              ) : null}
              {workflowRequiresGraph || workflowGraphUnits.length ? (
                <TabsTrigger className="min-w-20 flex-1 gap-2" value="workflowGraph">
                  Graph
                  {workflowGraphIssueCount ? (
                    <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {workflowGraphIssueCount}
                    </span>
                  ) : null}
                </TabsTrigger>
              ) : null}
              {showKbIndexTab ? (
                <TabsTrigger className="min-w-20 flex-1 gap-2" value="kbIndex">
                  Index
                  {kbIndexPlan?.summary?.unresolved_target_count ? (
                    <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {String(kbIndexPlan.summary.unresolved_target_count)}
                    </span>
                  ) : null}
                </TabsTrigger>
              ) : null}
              <TabsTrigger className="min-w-20 flex-1" value="sop">SOP</TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1 gap-2" value="backendGate">
                API
                <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {publishReadinessLoading ? "..." : publishReadiness ? publishReadiness.ready ? "ok" : publishReadiness.failure_count : "-"}
                </span>
              </TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1 gap-2" value="readiness">
                Ready
                <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {readinessChecks.filter((check) => check.passed).length}/{readinessChecks.length}
                </span>
              </TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1" value="quality">Quality</TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1" value="publish">Publish</TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1" value="pipeline">Jobs</TabsTrigger>
              <TabsTrigger className="min-w-20 flex-1" value="chunks">Chunks</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent className="mt-0 space-y-4" value="view">
            <SourceDocumentView
              loading={versionRawLoading || extractionPipelineLoading}
              selectedDocument={selectedDocument}
              selectedVersion={selectedVersion}
              sourceEvidenceView={sourceEvidenceView}
              versionRaw={versionRaw}
            />
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="assign">
            <Card className="rounded-xl">
              <CardHeader className="border-b pb-4">
                <CardTitle>Collection assignment</CardTitle>
                <CardDescription>Approve the retrieval collection before reviewing individual units.</CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                {selectedDocument && extractionUnits.length ? (
                <CollectionAssignmentPanel
                  canEdit={canEditSelectedVersion}
                  collections={collections}
                  document={selectedDocument}
                  onApply={(collection) => onApplyCollection(extractionUnits, collection)}
                  units={extractionUnits}
                />
                ) : !selectedDocument ? (
                  <EmptyPanel icon={GitBranch} title="Select a document" text="Choose a source file before assigning collections." compact />
                ) : extractionUnitsLoading ? (
                  <div className="flex items-center gap-2 rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Loading extraction units
                  </div>
                ) : (
                  <EmptyPanel icon={GitBranch} title="No units to assign" text="This version has no extracted units yet." compact />
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="evidence">
            {!selectedDocument ? (
              <Card className="rounded-xl">
                <CardContent className="pt-4">
                  <EmptyPanel icon={FileText} title="Select a document" text="Choose a source file to inspect source evidence." compact />
                </CardContent>
              </Card>
            ) : (
              <SourceViewer
                extractionUnits={extractionUnits}
                loading={versionRawLoading}
                selectedDocument={selectedDocument}
                selectedVersion={selectedVersion}
                sourceEvidenceView={sourceEvidenceView}
                versionRaw={versionRaw}
              />
            )}
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="units">
          <Card className="rounded-xl" ref={reviewSectionRef}>
            <CardHeader className="border-b pb-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>Structured units</CardTitle>
                  <CardDescription>Edit, reject, approve, or acknowledge source references before publish.</CardDescription>
                </div>
                {reviewStats.total ? (
                  <MetaLine
                    items={[
                      `${reviewStats.reviewed}/${reviewStats.total} reviewed`,
                      `${reviewStats.security} security notes`,
                      `${atomicUnits.length} retrieval units`,
                    ]}
                  />
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
                            onClick={() => selectedVersion && onBulkReviewVersion(selectedVersion.version_id, bulkApproveScope, "approved")}
                            size="sm"
                            title={bulkReviewBlocked ? "Bulk approve is disabled for workflow, high-risk, or low-confidence drafts. Review units explicitly." : "Approve all units in this API scope after source review."}
                            type="button"
                            variant="secondary"
                          >
                            {busyKey === "bulk-review" ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <CheckCircle2 data-icon="inline-start" className="size-4" />}
                            {bulkApproveLabel}
                          </Button>
                          {bulkReviewBlocked ? <Badge variant="outline">manual review required</Badge> : null}
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
                            title={reviewEmptyState.title}
                            text={reviewEmptyState.text}
                            compact
                          />
                        ) : null}
                        {filteredDocumentLayerUnits.length ? (
                          <section className="space-y-2">
                            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                              <BookOpen className="size-4" />
                              Document layer
                            </div>
                            {filteredDocumentLayerUnits.map((unit) => (
                              <ExtractionReviewEditor
                                defaultEffectiveFrom={defaultEffectiveFrom}
                                documentGovernance={selectedDocumentGovernance}
                                disabled={!canEditSelectedVersion}
                                deleting={deletingUnitId === unit.unit_id}
                                key={unit.unit_id}
                                onDelete={onDeleteExtractionUnit}
                                onSave={onUpdateExtractionUnit}
                                saving={savingUnitId === unit.unit_id}
                                unit={unit}
                              />
                            ))}
                          </section>
                        ) : null}
                        {filteredWorkflowGraphUnits.length ? (
                          <section className="space-y-2">
                            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                              <Network className="size-4" />
                              Workflow graph unit
                            </div>
                            {filteredWorkflowGraphUnits.map((unit) => (
                              <ExtractionReviewEditor
                                defaultEffectiveFrom={defaultEffectiveFrom}
                                documentGovernance={selectedDocumentGovernance}
                                disabled={!canEditSelectedVersion}
                                deleting={deletingUnitId === unit.unit_id}
                                key={unit.unit_id}
                                onDelete={onDeleteExtractionUnit}
                                onSave={onUpdateExtractionUnit}
                                saving={savingUnitId === unit.unit_id}
                                unit={unit}
                              />
                            ))}
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
                              documentGovernance={selectedDocumentGovernance}
                              disabled={!canEditSelectedVersion}
                              deleting={deletingUnitId === unit.unit_id}
                              key={unit.unit_id}
                              onDelete={onDeleteExtractionUnit}
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
              )}
            </CardContent>
          </Card>
          </TabsContent>

          {showKbIndexTab ? (
            <TabsContent className="mt-0 space-y-4" value="kbIndex">
              <KBIndexReviewPanel
                canEdit={canEditSelectedVersion}
                deletingUnitId={deletingUnitId}
                defaultEffectiveFrom={defaultEffectiveFrom}
                kbIndexPlan={kbIndexPlan}
                onDeleteExtractionUnit={onDeleteExtractionUnit}
                onUpdateExtractionUnit={onUpdateExtractionUnit}
                savingUnitId={savingUnitId}
                units={extractionUnits}
              />
            </TabsContent>
          ) : null}

          {requiredWorkflowUnits.length ? (
            <TabsContent className="mt-0 space-y-4" value="workflowRequirements">
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
            </TabsContent>
          ) : null}

          {workflowRequiresGraph || workflowGraphUnits.length ? (
            <TabsContent className="mt-0 space-y-4" value="workflowGraph">
              {workflowGraphUnit || workflowRequiresGraph ? (
                <WorkflowGraphPanel
                  canEdit={canEditSelectedVersion}
                  graph={workflowGraph}
                  graphUnit={workflowGraphUnit}
                  confidence={workflowGraphConfidence}
                  onAcknowledge={(unit, reason) => onUpdateExtractionUnit(unit, buildWorkflowGraphAcknowledgement(unit, reason))}
                  onReviewOpenEdges={(unit, edges, status, reason) => onUpdateExtractionUnit(unit, buildWorkflowBulkEdgeReviewUpdate(unit, edges, status, reason))}
                  onReviewEdge={(unit, edge, status, reason) => onUpdateExtractionUnit(unit, buildWorkflowEdgeReviewUpdate(unit, edge, status, reason))}
                  saving={savingUnitId === workflowGraphUnit?.unit_id}
                />
              ) : (
                <Card className="rounded-xl">
                  <CardContent className="pt-4">
                    <EmptyPanel icon={Network} title="No workflow graph" text="This version has no workflow graph unit to review." compact />
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          ) : null}

          <TabsContent className="mt-0 space-y-4" value="sop">
            <Card className="rounded-xl">
              <CardHeader className="border-b pb-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle>Document overview</CardTitle>
                    <CardDescription>Short document-level summary for routing and parent context. Full source text remains in Source evidence.</CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">overview layer</Badge>
                    <Badge variant="outline">{atomicUnits.length} atomic units</Badge>
                    {sourceEvidenceUnits.length ? <Badge variant="outline">{sourceEvidenceUnits.length} source sections</Badge> : null}
                    {validationRuleCount ? <Badge variant="outline">{validationRuleCount} validation rules</Badge> : null}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                {!selectedDocument ? (
                  <EmptyPanel icon={BookOpen} title="Select a document" text="Choose a source document to preview the overview layer." compact />
                ) : extractionUnitsLoading ? (
                  <div className="flex items-center gap-2 rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Loading document overview
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
                  <EmptyPanel icon={Layers3} title="No document overview" text="This version only has atomic retrieval units. Re-extract to create a document-level overview." compact />
                )}
              </CardContent>
            </Card>

            <DraftRetrievalPreview
              selectedDocument={selectedDocument}
              units={[fullSopUnit, ...atomicUnits].filter(Boolean) as ExtractionUnit[]}
            />
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="backendGate">
            {workflowRequiresGraph && workflowGraphIssueCount > 0 ? (
              <Card className="rounded-xl border-destructive/35 bg-destructive/5">
                <CardHeader className="border-b border-destructive/20 pb-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-destructive">Workflow graph blocks publish</CardTitle>
                      <CardDescription>
                        This is resolved in the Graph tab. API gate only shows the blocker summary.
                      </CardDescription>
                    </div>
                    <Button onClick={() => setDocumentStep("workflowGraph")} size="sm" type="button" variant="secondary">
                      <Network data-icon="inline-start" className="size-4" />
                      Open Graph review
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-3 pt-4 md:grid-cols-2">
                  <div className="rounded-lg border bg-background p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">Topology warnings</p>
                      <Badge variant={workflowGraphWarningsAcknowledged ? "secondary" : "destructive"}>
                        {workflowGraphWarningsAcknowledged ? "acknowledged" : `${workflowGraphWarningIssueCount} open`}
                      </Badge>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      {workflowGraphWarningsAcknowledged
                        ? "Topology warnings have an acknowledgement reason."
                        : "Open the Graph tab, compare against source, then fill Acknowledge with reason."}
                    </p>
                  </div>
                  <div className="rounded-lg border bg-background p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">Decision branch review</p>
                      <Badge variant={workflowEdgeReviewSummary.blockingCount ? "destructive" : "secondary"}>
                        {workflowEdgeReviewSummary.blockingCount ? `${workflowEdgeReviewSummary.blockingCount} open` : "done"}
                      </Badge>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      {workflowEdgeReviewSummary.blockingCount
                        ? "Open the Graph tab and confirm each decision branch, or acknowledge ambiguous branches with a reason."
                        : "All required decision branches are confirmed or acknowledged."}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : null}

            <Card className="rounded-xl">
              <CardHeader className="border-b pb-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle>Backend publish gate</CardTitle>
                    <CardDescription>Exact dry-run result from the publish API, kept separate from frontend heuristics.</CardDescription>
                  </div>
                  <Badge variant={publishReadiness?.ready ? "secondary" : "destructive"}>
                    {publishReadinessLoading ? "checking" : publishReadiness?.ready ? "api ready" : `${publishReadiness?.failure_count ?? 0} API blocker(s)`}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                {publishReadinessLoading ? (
                  <div className="flex items-center gap-2 rounded-lg border bg-muted/20 p-3 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Checking backend publish readiness
                  </div>
                ) : !publishReadiness ? (
                  <EmptyPanel icon={ShieldCheck} title="No backend gate result" text="Select a draft version to run the publish dry-run." compact />
                ) : publishReadiness.ready ? (
                  <div className="rounded-lg border bg-secondary/30 p-3 text-sm">
                    Backend publish validation has no open blockers for this version.
                  </div>
                ) : (
                  <div className="grid gap-2 md:grid-cols-2">
                    {publishReadiness.failures.slice(0, 12).map((failure) => (
                      <div className="rounded-lg border bg-muted/10 p-3" key={failure}>
                        <div className="flex items-center gap-2">
                          <TriangleAlert className="size-4 text-destructive" />
                          <p className="text-sm font-semibold">{readablePublishFailure(failure)}</p>
                        </div>
                        <p className="mt-1 font-mono text-[11px] text-muted-foreground">{failure}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="readiness">
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
                    {selectedVersionCanBulkReview && selectedVersion ? (
                      <Button
                        className="h-8 px-3"
                        disabled={busyKey === "bulk-review" || extractionUnits.length === 0}
                        onClick={() => onBulkReviewVersion(selectedVersion.version_id, "all", "approved")}
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

            <PublishTaskList tasks={publishTasks} ready={readinessPassed && !selectedIsArchived && !publishReadinessLoading && publishReadiness?.ready !== false} />
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="quality">
            <SopQualityAuditPanel audit={sopQualityAudit} />
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="publish">
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
                    const versionArchived = version.status === "archived";
                    const publishState = version.publish_state ?? (version.status === "published" ? "published_ready" : version.status);
                    const indexingFailed = publishState === "published_indexing_failed";
                    const indexingPending = publishState === "publishing" || publishState === "published_indexing_pending";
                    const publishedReady = publishState === "published_ready";
                    const backendPublishChecking = isInspectedVersion && publishReadinessLoading;
                    const backendPublishBlocked = isInspectedVersion && publishReadiness?.ready === false;
                    const publishBlocked = selectedIsArchived || versionArchived || !isInspectedVersion || !readinessPassed || backendPublishChecking || backendPublishBlocked;
                    let publishBlockReason = "";
                    if (selectedIsArchived) {
                      publishBlockReason = "Archived sources cannot be republished from this audit view.";
                    } else if (versionArchived) {
                      publishBlockReason = "Archived versions cannot be republished from this audit view.";
                    } else if (!isInspectedVersion) {
                      publishBlockReason = "Inspect this version before publishing it.";
                    } else if (backendPublishChecking) {
                      publishBlockReason = "Backend publish gate is still checking this version.";
                    } else if (backendPublishBlocked) {
                      publishBlockReason = `Backend publish gate still has ${publishReadiness?.failure_count ?? 0} blocker(s).`;
                    } else if (!readinessPassed) {
                      publishBlockReason = "Publishing is blocked until the Checklist passes.";
                    }
                    return (
                    <div className={cn("rounded-lg border p-3", selectedChunkVersionId === version.version_id ? "bg-muted/35" : "bg-card")} key={version.version_id}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <StatusBadge status={version.status} />
                            <Badge variant={indexingFailed ? "destructive" : publishedReady ? "secondary" : "outline"}>{publishState}</Badge>
                          </div>
                          <p className="mt-2 text-sm font-medium">{version.change_summary || "No change summary"}</p>
                          <MetaLine
                            className="mt-1"
                            items={[
                              `v${version.version_number}`,
                              version.review_status ?? "needs_review",
                              `${version.chunk_count} chunks`,
                              `${Math.round((version.extraction_confidence ?? 0) * 100)}% confidence`,
                              formatDate(version.created_at),
                            ]}
                          />
                        </div>
                        {version.status !== "published" ? (
                          <div className="flex shrink-0 flex-col items-end gap-2">
                            <Button
                              data-testid={`version-${version.version_id}-publish`}
                              disabled={busyKey === "publishing" || publishBlocked}
                              onClick={() => {
                                if (confirmingPublishVersionId !== version.version_id) {
                                  setConfirmingForcePublishVersionId("");
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
                                : versionArchived
                                  ? "Archived"
                                : !isInspectedVersion
                                  ? "Inspect first"
                                : !readinessPassed || backendPublishChecking || backendPublishBlocked
                                  ? "Not ready"
                                : busyKey === "publishing"
                                ? "Publishing"
                                : confirmingPublishVersionId === version.version_id
                                  ? "Confirm publish"
                                  : "Publish"}
                            </Button>
                            <Button
                              className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
                              data-testid={`version-${version.version_id}-force-publish`}
                              disabled={busyKey === "publishing" || selectedIsArchived || versionArchived || !isInspectedVersion}
                              onClick={() => {
                                if (confirmingForcePublishVersionId !== version.version_id) {
                                  setConfirmingPublishVersionId("");
                                  setConfirmingForcePublishVersionId(version.version_id);
                                  return;
                                }
                                setConfirmingForcePublishVersionId("");
                                onPublishVersion(version.version_id, true);
                              }}
                              size="sm"
                              type="button"
                              variant="outline"
                            >
                              <TriangleAlert data-icon="inline-start" className="size-3.5" />
                              {busyKey === "publishing"
                                ? "Publishing"
                                : selectedIsArchived || versionArchived
                                  ? "Archived"
                                : !isInspectedVersion
                                  ? "Inspect first"
                                  : confirmingForcePublishVersionId === version.version_id
                                    ? "Confirm force"
                                    : "Force publish"}
                            </Button>
                          </div>
                        ) : indexingFailed ? (
                          <Button
                            data-testid={`version-${version.version_id}-retry-indexing`}
                            disabled={busyKey === "indexing"}
                            onClick={() => onRetryIndexing(version.version_id)}
                            size="sm"
                            type="button"
                            variant="outline"
                          >
                            Retry indexing
                          </Button>
                        ) : indexingPending ? (
                          <Badge variant="outline">indexing</Badge>
                        ) : (
                          <Badge variant="secondary">published_ready</Badge>
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
                        {version.status === "published" && publishedReady ? (
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
                      {version.status === "published" && publishedReady ? (
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          This version is live. Test it from the same Lookup and SOP Chat surfaces agents will use.
                        </p>
                      ) : version.status === "published" && indexingFailed ? (
                        <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
                          <p className="text-xs leading-5 text-destructive">
                            Indexing failed, so Lookup and SOP Chat will not use this version yet. Retry after checking Meilisearch and AI chunk availability.
                          </p>
                          {version.indexing_error ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{version.indexing_error}</p> : null}
                        </div>
                      ) : version.status === "published" && indexingPending ? (
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          This version is published in DB but still waiting for search/vector visibility confirmation.
                        </p>
                      ) : publishBlocked ? (
                        <div className="mt-3 rounded-lg border bg-muted/15 p-3">
                          <p className="text-xs leading-5 text-muted-foreground">{publishBlockReason}</p>
                          {isInspectedVersion && (!readinessPassed || backendPublishBlocked) ? (
                            <Button className="mt-2 h-8 px-3" onClick={() => setDocumentStep("readiness")} size="sm" type="button" variant="secondary">
                              <ShieldCheck data-icon="inline-start" className="size-3.5" />
                              Open Checklist
                            </Button>
                          ) : null}
                        </div>
                      ) : null}
                      {confirmingPublishVersionId === version.version_id ? (
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          Confirming will lock this version, archive the previous published version, and sync search indexes.
                        </p>
                      ) : null}
                      {confirmingForcePublishVersionId === version.version_id ? (
                        <p className="mt-2 text-xs leading-5 text-destructive">
                          MVP force publish bypasses readiness blockers, locks this version, archives the previous published version, and syncs search indexes.
                        </p>
                      ) : null}
                    </div>
                  )})}
                </div>
              )}
            </CardContent>
          </Card>
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="pipeline">
            <ExtractionPipelineTrace inspection={extractionPipelineInspection} jobs={extractionPipeline} loading={extractionPipelineLoading} />
          </TabsContent>

          <TabsContent className="mt-0 space-y-4" value="chunks">
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
                        <MetaLine
                          items={[
                            `chunk ${chunk.chunk_index}`,
                            chunk.section,
                            String(chunk.metadata.retrieval_scope ?? "unit"),
                            `${chunk.token_count} tokens`,
                          ]}
                        />
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
          </TabsContent>
        </Tabs>
      </section>
      ) : null}
    </div>
  );
}

const REVIEW_FILTERS: Array<{ label: string; value: ReviewFilter }> = [
  { label: "Needs review", value: "needs_review" },
  { label: "Reviewed", value: "reviewed" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Source refs", value: "source_refs" },
  { label: "Atomic", value: "atomic" },
  { label: "All", value: "all" },
];

function isReviewedExtractionUnit(unit: ExtractionUnit) {
  return unit.review_status === "reviewed" || unit.review_status === "approved";
}

function isRejectedExtractionUnit(unit: ExtractionUnit) {
  return unit.review_status === "rejected";
}

function unitMatchesReviewFilter(unit: ExtractionUnit, filter: ReviewFilter, isAtomic: boolean) {
  if (filter === "all") {
    return true;
  }
  if (filter === "atomic") {
    return isAtomic;
  }
  if (filter === "source_refs") {
    return !isRejectedExtractionUnit(unit) && unit.metadata.source_ref_quality === "page_only" && unit.metadata.source_ref_acknowledged !== true;
  }
  return unit.review_status === filter;
}

function reviewFilterEmptyState(filter: ReviewFilter) {
  if (filter === "needs_review") {
    return {
      text: "Switch to All or Approved to audit completed units.",
      title: "No units need review",
    };
  }
  if (filter === "source_refs") {
    return {
      text: "Every page-only source reference is acknowledged.",
      title: "No source refs need acknowledgement",
    };
  }
  if (filter === "rejected") {
    return {
      text: "Rejected units will appear here after CS Ops excludes them from publish.",
      title: "No rejected units",
    };
  }
  return {
    text: "Change the review filter to inspect another group.",
    title: "No units in this filter",
  };
}

function CollectionAssignmentPanel({
  canEdit,
  collections,
  document,
  onApply,
  units,
}: {
  canEdit: boolean;
  collections: KBCollectionSummary[];
  document: DocumentSummary;
  onApply: (collection: KBCollectionSummary | null) => void;
  units: ExtractionUnit[];
}) {
  const currentSlug = mostCommonString([
    ...units.map((unit) => metadataString(unit.metadata.collection_slug)),
    metadataString(document.metadata?.collection_slug),
  ]);
  const suggestedSlug = metadataString(document.metadata?.suggested_collection_slug) || mostCommonString(units.map((unit) => metadataString(unit.metadata.suggested_collection_slug)));
  const [draftSlug, setDraftSlug] = useState(currentSlug || "none");
  const currentCollection = collections.find((collection) => collection.slug === currentSlug);
  const suggestedCollection = collections.find((collection) => collection.slug === suggestedSlug);
  const draftCollection = collections.find((collection) => collection.slug === draftSlug);

  useEffect(() => {
    setDraftSlug(currentSlug || "none");
  }, [currentSlug]);

  return (
    <div className="mb-4 rounded-xl border bg-muted/15 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">Collection assignment</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Collections guide Lookup, Chat retrieval boosts, onboarding, and browse pages. AI suggestions need manual approval before publish.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={currentSlug ? "secondary" : "outline"}>{currentSlug ? "approved collection" : "unassigned"}</Badge>
          {suggestedSlug && suggestedSlug !== currentSlug ? <Badge variant="outline">AI suggested</Badge> : null}
        </div>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
        <Select disabled={!canEdit} onValueChange={setDraftSlug} value={draftSlug}>
          <SelectTrigger className="h-9 rounded-full bg-background">
            <SelectValue placeholder="No collection" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">No collection</SelectItem>
            {collections.map((collection) => (
              <SelectItem key={collection.id} value={collection.slug}>
                {collection.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          disabled={!canEdit || draftSlug === (currentSlug || "none")}
          onClick={() => onApply(draftCollection ?? null)}
          size="sm"
          type="button"
          variant="secondary"
        >
          Apply to all units
        </Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>Current: {currentCollection?.name ?? (currentSlug || "None")}</span>
        {suggestedCollection && suggestedCollection.slug !== currentSlug ? (
          <>
            <span>·</span>
            <button
              className="font-medium text-foreground underline-offset-4 hover:underline disabled:text-muted-foreground"
              disabled={!canEdit}
              onClick={() => setDraftSlug(suggestedCollection.slug)}
              type="button"
            >
              Use AI suggestion: {suggestedCollection.name}
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}

function metadataString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function mostCommonString(values: string[]) {
  const counts = new Map<string, number>();
  for (const value of values) {
    if (!value) {
      continue;
    }
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? "";
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
  const metadata = document.metadata ?? {};
  const status = String(metadata.extraction_status ?? "");
  const error = String(metadata.extraction_error ?? "");
  const aiError = String(metadata.ai_error ?? "");
  const publishBlocked = metadata.publish_blocked === true || String(metadata.publish_blocked ?? "") === "true";
  const publishBlockedReason = String(metadata.publish_blocked_reason ?? "");
  const warnings = Array.isArray(metadata.extraction_warnings)
    ? metadata.extraction_warnings.map(String).filter(Boolean)
    : [];

  if (status.startsWith("failed") || error) {
    return {
      guidance: "Review can continue from raw extracted text, but publish is blocked until structured extraction succeeds.",
      reason: error || aiError || warnings.find(isHardExtractionWarning) || "Extraction failed before structured units were created.",
      status,
      title: "Extraction failed, source evidence saved",
      warnings: warnings.filter(isDisplayableExtractionWarning),
    };
  }

  if (status === "degraded" || isStructuringPublishBlock(publishBlocked, publishBlockedReason)) {
    return {
      guidance: "Review the extracted units, then approve or force-approve after manual curation to make this SOP publish-ready.",
      reason: aiError || publishBlockedReason || warnings.find(isHardExtractionWarning) || "Structured extraction needs manual curation.",
      status,
      title: "Extraction needs manual curation",
      warnings: warnings.filter(isDisplayableExtractionWarning),
    };
  }

  if (warnings.some(isHardExtractionWarning)) {
    return {
      guidance: "Check the extraction pipeline details before publishing this SOP.",
      reason: warnings.find(isHardExtractionWarning) ?? "Extraction warning requires review.",
      status,
      title: "Extraction warning requires review",
      warnings: warnings.filter(isDisplayableExtractionWarning),
    };
  }

  return null;
}

function isStructuringPublishBlock(publishBlocked: boolean, reason: string) {
  if (!publishBlocked) {
    return false;
  }
  return [
    "structured_ai_extraction_failed",
    "ai_structuring_failed_requires_manual_curation",
    "manual_review_required",
  ].some((signal) => reason.includes(signal));
}

function isHardExtractionWarning(warning: string) {
  const normalized = warning.toLowerCase();
  return (
    (normalized.startsWith("ai_") && normalized.includes("failed")) ||
    normalized.includes("structuring_failed") ||
    normalized.includes("extraction_failed")
  );
}

function isDisplayableExtractionWarning(warning: string) {
  if (isHardExtractionWarning(warning)) {
    return true;
  }
  return ![
    "openrouter_rule_table_extraction_used",
    "openrouter_refine_used",
    "openrouter_source_evidence_formatter_used",
    "source_evidence_formatter_not_object",
    "effective_from_missing_needs_review",
  ].some((signal) => warning.includes(signal));
}

function ValidationPill({ text, valid }: { text: string; valid: boolean }) {
  return (
    <div className={cn("rounded-lg border px-2 py-1 text-[11px]", valid ? "bg-secondary text-secondary-foreground" : "border-destructive/30 bg-destructive/10 text-destructive")}>
      {valid ? "OK" : "Block"}: {text}
    </div>
  );
}

function StepRail({
  current,
  steps,
}: {
  current: string;
  steps: Array<{ key: string; label: string }>;
}) {
  const currentIndex = Math.max(0, steps.findIndex((step) => step.key === current));
  return (
    <ol className="grid gap-2 rounded-lg border bg-muted/15 p-2 sm:grid-cols-3">
      {steps.map((step, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "next";
        return (
          <li className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-center gap-2" key={step.key}>
            <span
              className={cn(
                "flex size-6 items-center justify-center rounded-full border text-[11px] font-semibold tabular-nums",
                state === "current" && "border-primary bg-primary text-primary-foreground",
                state === "done" && "bg-secondary text-secondary-foreground",
                state === "next" && "bg-background text-muted-foreground",
              )}
            >
              {index + 1}
            </span>
            <span className={cn("truncate text-xs font-medium", state === "next" ? "text-muted-foreground" : "text-foreground")}>
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
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

function SourceDocumentView({
  loading,
  selectedDocument,
  selectedVersion,
  sourceEvidenceView,
  versionRaw,
}: {
  loading: boolean;
  selectedDocument: DocumentSummary | null;
  selectedVersion?: VersionSummary;
  sourceEvidenceView: SourceEvidenceViewPayload | null;
  versionRaw: VersionRawText | null;
}) {
  const [mode, setMode] = useState<"formatted" | "raw">("formatted");
  const rawText = versionRaw?.raw_text ?? "";
  const formattedMarkdown = sourceEvidenceView?.markdown?.trim() || formatRawEvidenceMarkdown(rawText);
  const warnings = sourceEvidenceView?.warnings ?? [];
  return (
    <Card className="rounded-xl">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">source view</Badge>
            </div>
            <CardTitle className="mt-3">{sourceEvidenceView?.title || selectedDocument?.source_filename || "Source document"}</CardTitle>
            <CardDescription>
              Read the source as a clean SOP view. Switch to raw when auditing extraction fidelity.
            </CardDescription>
            <MetaLine
              className="mt-1"
              items={[
                sourceEvidenceView?.formatter ? "AI formatted" : "local format",
                `v${selectedVersion?.version_number ?? "-"}`,
              ]}
            />
          </div>
          <div className="flex rounded-lg border bg-muted/20 p-1">
            <Button className="h-8 px-3" onClick={() => setMode("formatted")} size="sm" type="button" variant={mode === "formatted" ? "secondary" : "ghost"}>
              Formatted
            </Button>
            <Button className="h-8 px-3" onClick={() => setMode("raw")} size="sm" type="button" variant={mode === "raw" ? "secondary" : "ghost"}>
              Raw
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        {!selectedDocument ? (
          <EmptyPanel icon={BookOpen} title="Select a document" text="Choose a source file to read it as an SOP." compact />
        ) : loading ? (
          <div className="flex items-center gap-2 rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading source view
          </div>
        ) : rawText ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
            <div className="min-w-0 rounded-xl border bg-background">
              {mode === "formatted" ? (
                <MarkdownEvidence markdown={formattedMarkdown} />
              ) : (
                <ScrollArea className="h-[48rem] p-4">
                  <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-muted-foreground">{rawText}</pre>
                </ScrollArea>
              )}
            </div>
            <aside className="space-y-3">
              <div className="rounded-xl border bg-muted/15 p-3">
                <div className="text-xs font-semibold">Source health</div>
                <div className="mt-3 grid gap-2 text-xs text-muted-foreground">
                  <div className="flex justify-between gap-2"><span>Raw chars</span><span>{rawText.length.toLocaleString()}</span></div>
                  <div className="flex justify-between gap-2"><span>Formatted chars</span><span>{formattedMarkdown.length.toLocaleString()}</span></div>
                  <div className="flex justify-between gap-2"><span>Sections</span><span>{sourceEvidenceView?.sections?.length ?? countMarkdownHeadings(formattedMarkdown)}</span></div>
                  <div className="flex justify-between gap-2"><span>Model</span><span className="text-right">{sourceEvidenceView?.model || "n/a"}</span></div>
                </div>
              </div>
              {warnings.length ? (
                <div className="rounded-xl border bg-muted/15 p-3">
                  <div className="text-xs font-semibold">Formatter warnings</div>
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground">
                    {warnings.slice(0, 8).map((warning) => <li key={warning}>{warning}</li>)}
                  </ul>
                </div>
              ) : null}
              {sourceEvidenceView?.markdown_truncated ? (
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-5 text-amber-800">
                  Formatted view was truncated. Use Raw mode for full evidence.
                </div>
              ) : null}
            </aside>
          </div>
        ) : (
          <EmptyPanel icon={FileText} title="No source view loaded" text="Raw extraction is unavailable for this version." compact />
        )}
      </CardContent>
    </Card>
  );
}

function KBIndexReviewPanel({
  canEdit,
  deletingUnitId,
  defaultEffectiveFrom,
  kbIndexPlan,
  onDeleteExtractionUnit,
  onUpdateExtractionUnit,
  savingUnitId,
  units,
}: {
  canEdit: boolean;
  deletingUnitId: string;
  defaultEffectiveFrom: string;
  kbIndexPlan: KBIndexPlanPayload | null;
  onDeleteExtractionUnit: (unit: ExtractionUnit) => void;
  onUpdateExtractionUnit: (unit: ExtractionUnit, update: ExtractionUnitUpdate) => void;
  savingUnitId: string;
  units: ExtractionUnit[];
}) {
  const kbUnits = units.filter((unit) => unit.metadata?.kb_index === true || String(unit.metadata?.document_type ?? "") === "kb_index_workbook");
  const buckets = [
    { key: "collections", label: "Collections", units: kbUnits.filter((unit) => String(unit.metadata?.kb_index_candidate_type ?? "") === "collections") },
    { key: "issue_router_units", label: "Issue Router Units", units: kbUnits.filter((unit) => ["issue_router_unit", "vip_overlay_rule", "product_update_note"].includes(unit.unit_type)) },
    { key: "sop_references", label: "SOP References", units: kbUnits.filter((unit) => unit.unit_type === "sop_reference") },
    { key: "tool_links", label: "Tool Links", units: kbUnits.filter((unit) => unit.unit_type === "tool_link") },
    { key: "action_templates", label: "Action Templates", units: kbUnits.filter((unit) => unit.unit_type === "quick_action_rule") },
  ];
  const unresolvedTargets = kbIndexPlan?.unresolved_targets ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="border-b">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Workbook index review</CardTitle>
              <CardDescription>
                Review imported collections, issue routers, SOP references, tools, actions, and unresolved targets before publish materializes them.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">{kbUnits.length} candidates</Badge>
              <Badge variant="outline">{unresolvedTargets.length} unresolved targets</Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 pt-4 md:grid-cols-3 xl:grid-cols-6">
          <DocumentFact label="Collections" value={String(kbIndexPlan?.summary?.collection_count ?? buckets[0].units.length)} />
          <DocumentFact label="Routers" value={String(kbIndexPlan?.summary?.issue_router_unit_count ?? buckets[1].units.length)} />
          <DocumentFact label="SOP refs" value={String(kbIndexPlan?.summary?.sop_reference_count ?? buckets[2].units.length)} />
          <DocumentFact label="Tools" value={String(kbIndexPlan?.summary?.tool_link_count ?? buckets[3].units.length)} />
          <DocumentFact label="Actions" value={String(kbIndexPlan?.summary?.action_template_count ?? buckets[4].units.length)} />
          <DocumentFact label="Unresolved" value={String(kbIndexPlan?.summary?.unresolved_target_count ?? unresolvedTargets.length)} />
        </CardContent>
      </Card>

      {unresolvedTargets.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Unresolved Relations</CardTitle>
            <CardDescription>These source rows mention a target SOP but no approved target is linked yet.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 md:grid-cols-2">
            {unresolvedTargets.slice(0, 12).map((target, index) => (
              <div className="rounded-md border p-3 text-sm" key={`${String(target.target_title ?? "target")}-${index}`}>
                <div className="font-medium">{String(target.target_title ?? "Unknown target")}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {String(target.relation_type ?? "references")} · {String(target.source_sheet ?? "")} row {String(target.source_row ?? "")}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {buckets.map((bucket) => (
        <Card key={bucket.key}>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-3 text-base">
              {bucket.label}
              <Badge variant="outline">{bucket.units.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {bucket.units.length === 0 ? (
              <p className="text-sm text-muted-foreground">No candidates in this group.</p>
            ) : (
              bucket.units.map((unit) => (
                <ExtractionReviewEditor
                  defaultEffectiveFrom={defaultEffectiveFrom}
                  disabled={!canEdit}
                  deleting={deletingUnitId === unit.unit_id}
                  key={unit.unit_id}
                  onDelete={onDeleteExtractionUnit}
                  onSave={onUpdateExtractionUnit}
                  saving={savingUnitId === unit.unit_id}
                  unit={unit}
                />
              ))
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function SourceViewer({
  extractionUnits,
  loading,
  selectedDocument,
  selectedVersion,
  sourceEvidenceView,
  versionRaw,
}: {
  extractionUnits: ExtractionUnit[];
  loading: boolean;
  selectedDocument: DocumentSummary;
  selectedVersion?: VersionSummary;
  sourceEvidenceView: SourceEvidenceViewPayload | null;
  versionRaw: VersionRawText | null;
}) {
  const [failedPreviewUrl, setFailedPreviewUrl] = useState("");
  const [mode, setMode] = useState<"formatted" | "raw">("formatted");
  const isPdfSource = selectedDocument.source_filename.toLowerCase().endsWith(".pdf") || selectedDocument.latest_document_type === "workflow_diagram";
  const previewUrl =
    isPdfSource && selectedVersion
      ? `${API_BASE_URL}/api/v1/ai/versions/${selectedVersion.version_id}/source/pages/1`
      : "";
  const formattedMarkdown = sourceEvidenceView?.markdown?.trim() || formatRawEvidenceMarkdown(versionRaw?.raw_text ?? "");
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
        </div>
        <h3 className="mt-3 line-clamp-2 text-sm font-semibold">{selectedDocument.source_filename}</h3>
        <MetaLine
          className="mt-1"
          items={[
            `v${selectedVersion?.version_number ?? "-"}`,
            selectedDocument.latest_document_type ?? "unknown",
          ]}
        />
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
        <TagSummary items={references} maxItems={4} />
        <div className="flex rounded-lg border bg-background p-1">
          <Button className="h-7 flex-1 px-2 text-xs" onClick={() => setMode("formatted")} size="sm" type="button" variant={mode === "formatted" ? "secondary" : "ghost"}>
            Formatted
          </Button>
          <Button className="h-7 flex-1 px-2 text-xs" onClick={() => setMode("raw")} size="sm" type="button" variant={mode === "raw" ? "secondary" : "ghost"}>
            Raw
          </Button>
        </div>
        {loading ? (
          <div className="flex items-center gap-2 rounded-lg border bg-background/60 p-3 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading raw extraction
          </div>
        ) : versionRaw?.raw_text ? (
          <ScrollArea className="h-[40rem] rounded-lg border bg-background p-3">
            {mode === "formatted" ? (
              <MarkdownEvidence compact markdown={formattedMarkdown} />
            ) : (
              <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-5 text-muted-foreground">{versionRaw.raw_text}</pre>
            )}
          </ScrollArea>
        ) : (
          <EmptyPanel icon={FileText} title="No raw source loaded" text="Raw extraction is unavailable for this version." compact />
        )}
      </div>
    </aside>
  );
}

function MarkdownEvidence({ compact = false, markdown }: { compact?: boolean; markdown: string }) {
  const blocks = markdownTableAwareBlocks(markdown);
  return (
    <div className={compact ? "space-y-2 text-xs leading-5" : "space-y-3 p-5 text-sm leading-6"}>
      {blocks.map((block, index) => {
        if (block.type === "table") {
          return (
            <pre className="overflow-auto rounded-lg border bg-muted/15 p-3 font-mono text-[11px] leading-5 text-muted-foreground" key={`table-${index}`}>
              {block.lines.join("\n")}
            </pre>
          );
        }
        return <MarkdownLine compact={compact} key={`line-${index}`} line={block.lines[0] ?? ""} />;
      })}
    </div>
  );
}

function MarkdownLine({ compact, line }: { compact: boolean; line: string }) {
  const trimmed = line.trim();
  if (!trimmed) {
    return <div className={compact ? "h-1" : "h-2"} />;
  }
  const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
  if (heading) {
    const level = heading[1].length;
    const label = heading[2];
    const className = level === 1
      ? "border-b pb-2 text-lg font-semibold tracking-tight"
      : level === 2
        ? "pt-2 text-base font-semibold"
        : "text-sm font-semibold";
    return <div className={compact ? "text-sm font-semibold" : className}>{inlineMarkdown(label)}</div>;
  }
  if (trimmed.startsWith(">")) {
    return <div className="rounded-lg border bg-muted/20 px-3 py-2 text-muted-foreground">{inlineMarkdown(trimmed.replace(/^>\s?/, ""))}</div>;
  }
  const bullet = line.match(/^(\s*)[-*+]\s+(.+)$/);
  if (bullet) {
    const indent = Math.min(Math.floor((bullet[1]?.length ?? 0) / 2), 4);
    return (
      <div className="flex gap-2 text-muted-foreground" style={{ paddingLeft: `${indent * 0.85}rem` }}>
        <span className="mt-[0.65em] size-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
        <span>{inlineMarkdown(bullet[2])}</span>
      </div>
    );
  }
  const numbered = line.match(/^(\s*)(\d+(?:\.\d+)*\.?)\s+(.+)$/);
  if (numbered) {
    const indent = Math.min(Math.floor((numbered[1]?.length ?? 0) / 2), 4);
    return (
      <div className="flex gap-2 text-muted-foreground" style={{ paddingLeft: `${indent * 0.85}rem` }}>
        <span className="shrink-0 font-medium text-foreground">{numbered[2]}</span>
        <span>{inlineMarkdown(numbered[3])}</span>
      </div>
    );
  }
  return <p className="text-muted-foreground">{inlineMarkdown(trimmed)}</p>;
}

function markdownTableAwareBlocks(markdown: string) {
  const blocks: Array<{ lines: string[]; type: "line" | "table" }> = [];
  let tableLines: string[] = [];
  for (const line of markdown.split(/\r?\n/)) {
    if (line.trim().startsWith("|")) {
      tableLines.push(line);
      continue;
    }
    if (tableLines.length) {
      blocks.push({ lines: tableLines, type: "table" });
      tableLines = [];
    }
    blocks.push({ lines: [line], type: "line" });
  }
  if (tableLines.length) {
    blocks.push({ lines: tableLines, type: "table" });
  }
  return blocks;
}

function inlineMarkdown(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong className="font-semibold text-foreground" key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function formatRawEvidenceMarkdown(rawText: string) {
  if (!rawText.trim()) {
    return "";
  }
  return rawText
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+-\s+/g, "\n- ")
    .replace(/[ \t]+\+\s+/g, "\n  - ")
    .replace(/[ \t]+([@#%~]\s*[^:\n]{1,80}:)/g, "\n    - **$1**")
    .replace(/[ \t]+((?:TH|B)\d+(?:\.\d+)*\.?\s*:?)/g, "\n- **$1**")
    .replace(/[ \t]+((?:Yes|No|Có|Không|Cung cấp được|Không được|Trùng khớp|Không trùng khớp):)/gi, "\n  - **$1**")
    .replace(/[ \t]+(\d+(?:\.\d+){1,4}\.?\s+)/g, "\n  - $1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function countMarkdownHeadings(markdown: string) {
  return markdown.split(/\r?\n/).filter((line) => /^#{1,4}\s+/.test(line)).length;
}

function sourceEvidenceViewPayload(jobs: ExtractionJobSummary[]): SourceEvidenceViewPayload | null {
  const output = jobs.flatMap((job) => job.outputs ?? []).find((artifact) => artifact.artifact_type === "source_evidence_view");
  const payload = output?.payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }
  return payload as SourceEvidenceViewPayload;
}

function kbIndexPlanPayload(jobs: ExtractionJobSummary[]): KBIndexPlanPayload | null {
  const output = jobs.flatMap((job) => job.outputs ?? []).find((artifact) => artifact.artifact_type === "kb_index_plan");
  const payload = output?.payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }
  return payload as KBIndexPlanPayload;
}

function HelpTooltip({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          aria-label="Explain this workflow review item"
          className="inline-flex size-4 shrink-0 cursor-help items-center justify-center rounded-full text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
          type="button"
        >
          <CircleHelp className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-72 items-start text-left leading-5" side="top">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

function WorkflowGraphPanel({
  canEdit,
  confidence,
  graph,
  graphUnit,
  onAcknowledge,
  onReviewOpenEdges,
  onReviewEdge,
  saving,
}: {
  canEdit: boolean;
  confidence: number;
  graph?: WorkflowGraphMetadata;
  graphUnit?: ExtractionUnit;
  onAcknowledge: (unit: ExtractionUnit, reason: string) => void;
  onReviewOpenEdges: (unit: ExtractionUnit, edges: WorkflowEdgeMetadata[], status: "acknowledged", reason: string) => void;
  onReviewEdge: (unit: ExtractionUnit, edge: WorkflowEdgeMetadata, status: "acknowledged" | "confirmed" | "rejected", reason: string) => void;
  saving: boolean;
}) {
  const [acknowledgementReason, setAcknowledgementReason] = useState("");
  const validationErrors = graph?.validation_errors ?? graphUnit?.metadata.graph_validation_errors ?? [];
  const uncertainEdges = graph?.uncertain_edges ?? graphUnit?.metadata.uncertain_edges ?? [];
  const annotations = graph?.annotations ?? graphUnit?.metadata.annotations ?? [];
  const missingStepCodes = Array.isArray(graph?.missing_step_codes) ? graph.missing_step_codes : [];
  const detectorConflicts = Array.isArray(graph?.detector_conflicts) ? graph.detector_conflicts : [];
  const missingTerminalEdges = Array.isArray(graph?.missing_terminal_edges) ? graph.missing_terminal_edges : [];
  const orphanAnnotations = Array.isArray(graph?.orphan_annotations) ? graph.orphan_annotations : [];
  const unresolvedRelations = Array.isArray(graph?.unresolved_relations) ? graph.unresolved_relations : [];
  const decisionEdgesReviewRequired = Number(graph?.decision_edges_review_required ?? graphUnit?.metadata.decision_edges_review_required ?? 0);
  const repairApplied = Boolean(graph?.repair_applied ?? graphUnit?.metadata.repair_applied);
  const selectedFlow = String(graph?.selected_flow ?? graphUnit?.metadata.selected_flow ?? "");
  const fidelityScore = Number(graph?.graph_fidelity_score ?? graph?.fidelity_score ?? graph?.graph_confidence ?? confidence ?? 0);
  const lowConfidenceTopologyIssue = confidence > 0 && confidence < 0.7;
  const uncertainEdgeCount =
    Math.max(Array.isArray(uncertainEdges) ? uncertainEdges.length : 0, Number(graphUnit?.metadata.uncertain_edges_count ?? 0));
  const issueCount = (Array.isArray(validationErrors) ? validationErrors.length : 0) + uncertainEdgeCount + (lowConfidenceTopologyIssue ? 1 : 0);
  const savedAcknowledgementReason = String(graphUnit?.metadata.graph_validation_acknowledged_reason ?? "").trim();
  const acknowledged = issueCount === 0 || (graphUnit?.metadata.graph_validation_acknowledged === true && savedAcknowledgementReason.length > 0);
  const acknowledgementInputValid = acknowledgementReason.trim().length >= 8;
  const acknowledgementDisabledReason = !canEdit
    ? "Inspect an editable draft version first."
    : saving
      ? "Saving acknowledgement..."
      : !acknowledgementInputValid
        ? "Enter at least 8 characters explaining why this warning is acceptable."
        : "";
  const edgeReviewSummary = buildWorkflowEdgeReviewSummary(graph, graphUnit);
  const blockingDecisionEdges = workflowDecisionEdgesNeedingReview(graph, graphUnit);
  const canUseSavedReasonForBranches = savedAcknowledgementReason.length >= 8;
  const bulkAcknowledgeDisabledReason = !canEdit
    ? "Inspect an editable draft version first."
    : saving
      ? "Saving branch reviews..."
      : !canUseSavedReasonForBranches
        ? "Acknowledge topology warnings with a reason first."
        : !blockingDecisionEdges.length
          ? "All decision branches are already reviewed."
          : "";
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
                <HelpTooltip text="Workflow graph là lớp review topology: nodes, edges, annotations, và các nhánh cần kiểm tra với source diagram trước publish." />
              </div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {String(graph.review_reason ?? graphUnit.metadata.review_reason ?? "Review graph branches and arrow direction before publish.")}
              </p>
              {graph.topology_source === "workflow_v3_canvas_transcription" || missingStepCodes.length || detectorConflicts.length ? (
                <div className="mt-3 grid gap-2 text-xs md:grid-cols-3">
                  <div className="rounded-lg border bg-background p-2">
                    <span className="text-muted-foreground">V3 fidelity</span>
                    <p className="mt-1 font-semibold">{Math.round(fidelityScore * 100)}%</p>
                  </div>
                  <div className="rounded-lg border bg-background p-2">
                    <span className="text-muted-foreground">Missing visible steps</span>
                    <p className={cn("mt-1 font-semibold", missingStepCodes.length && "text-destructive")}>{missingStepCodes.length ? missingStepCodes.join(", ") : "none"}</p>
                  </div>
                  <div className="rounded-lg border bg-background p-2">
                    <span className="text-muted-foreground">Detector conflicts</span>
                    <p className={cn("mt-1 font-semibold", detectorConflicts.length && "text-destructive")}>{detectorConflicts.length || "none"}</p>
                  </div>
                </div>
              ) : null}
              <div className="mt-3 grid gap-2 text-xs md:grid-cols-3">
                <div className="rounded-lg border bg-background p-2">
                  <span className="text-muted-foreground">Selected flow</span>
                  <p className="mt-1 font-semibold">{selectedFlow || "unknown"}</p>
                </div>
                <div className="rounded-lg border bg-background p-2">
                  <span className="text-muted-foreground">Repair stage</span>
                  <p className={cn("mt-1 font-semibold", repairApplied && "text-amber-500")}>{repairApplied ? "applied" : "not needed"}</p>
                </div>
                <div className="rounded-lg border bg-background p-2">
                  <span className="text-muted-foreground">Decision edges to review</span>
                  <p className={cn("mt-1 font-semibold", decisionEdgesReviewRequired && "text-amber-500")}>{decisionEdgesReviewRequired || "none"}</p>
                </div>
                <div className="rounded-lg border bg-background p-2">
                  <span className="text-muted-foreground">Missing terminal edges</span>
                  <p className={cn("mt-1 font-semibold", missingTerminalEdges.length && "text-destructive")}>{missingTerminalEdges.length ? missingTerminalEdges.join(", ") : "none"}</p>
                </div>
                <div className="rounded-lg border bg-background p-2">
                  <span className="text-muted-foreground">Orphan annotations</span>
                  <p className={cn("mt-1 font-semibold", orphanAnnotations.length && "text-destructive")}>{orphanAnnotations.length || "none"}</p>
                </div>
                <div className="rounded-lg border bg-background p-2">
                  <span className="text-muted-foreground">Unresolved relations</span>
                  <p className={cn("mt-1 font-semibold", unresolvedRelations.length && "text-amber-500")}>{unresolvedRelations.length || "none"}</p>
                </div>
              </div>
            </div>
            {!acknowledged || edgeReviewSummary.blockingCount ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-destructive">How to clear “Workflow graph reviewed”</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Publish stays blocked until the graph warnings and decision branches below are explicitly reviewed.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {!acknowledged ? <Badge variant="destructive">{issueCount} topology warning(s)</Badge> : <Badge variant="secondary">topology acknowledged</Badge>}
                    {edgeReviewSummary.blockingCount ? <Badge variant="destructive">{edgeReviewSummary.blockingCount} branch review(s)</Badge> : <Badge variant="secondary">branches reviewed</Badge>}
                  </div>
                </div>
                <div className="mt-3 grid gap-2 text-xs leading-5 text-muted-foreground md:grid-cols-2">
                  <div className="rounded-lg border bg-background p-3">
                    <span className="inline-flex items-center gap-1 font-semibold text-foreground">
                      1. Topology warnings
                      <HelpTooltip text="Acknowledge phần này khi reviewer đã xem diagram và chấp nhận các warning tổng thể của graph, ví dụ confidence thấp, uncertain edges, hoặc validation warnings. Đây chưa phải review từng nhánh Yes/No." />
                    </span>
                    <p className="mt-1">
                      {!acknowledged
                        ? "Compare the diagram/source, enter a reason, then click Acknowledge with reason."
                        : "Done. The acknowledgement reason is saved on the graph unit."}
                    </p>
                  </div>
                  <div className="rounded-lg border bg-background p-3">
                    <span className="inline-flex items-center gap-1 font-semibold text-foreground">
                      2. Decision branches
                      <HelpTooltip text="Review từng cạnh đi ra từ decision node. Confirm nếu nhánh rõ ràng đúng theo diagram. Ack nếu nhánh còn mơ hồ nhưng chấp nhận được sau khi xem source. Reject nếu nhánh sai và cần sửa graph." />
                    </span>
                    <p className="mt-1">
                      {edgeReviewSummary.blockingCount
                        ? "Confirm clear Yes/No edges, or acknowledge ambiguous edges using the saved topology reason."
                        : "Done. Required decision edges are confirmed or acknowledged."}
                    </p>
                    {graphUnit && edgeReviewSummary.blockingCount ? (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <Button
                          className="h-8"
                          disabled={Boolean(bulkAcknowledgeDisabledReason)}
                          onClick={() => onReviewOpenEdges(graphUnit, blockingDecisionEdges, "acknowledged", savedAcknowledgementReason)}
                          size="sm"
                          title="Acknowledge tất cả decision branches còn open bằng reason đã lưu ở topology. Chỉ dùng sau khi đã spot-check source diagram."
                          type="button"
                          variant="secondary"
                        >
                          {saving ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <ShieldCheck data-icon="inline-start" className="size-3.5" />}
                          Ack remaining branches
                        </Button>
                        {bulkAcknowledgeDisabledReason ? (
                          <p className="text-[11px] leading-4">{bulkAcknowledgeDisabledReason}</p>
                        ) : (
                          <p className="text-[11px] leading-4">Uses saved reason: {savedAcknowledgementReason}</p>
                        )}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}
            {issueCount ? (
              <div className={cn("rounded-xl border p-4", acknowledged ? "bg-secondary/30" : "border-destructive/30 bg-destructive/5")}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className={cn("inline-flex items-center gap-1 text-sm font-semibold", acknowledged ? "text-foreground" : "text-destructive")}>
                      Topology validation blockers
                      <HelpTooltip text="Các blocker này đến từ validator của workflow graph: topology còn mơ hồ, thiếu review nhánh quyết định, hoặc confidence thấp. Reviewer phải kiểm tra source diagram rồi acknowledge với lý do rõ ràng." />
                    </p>
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
                          title="Reason này lưu ở graph-level acknowledgement. Sau đó có thể dùng lại để acknowledge các branch còn mơ hồ."
                          value={acknowledgementReason}
                        />
                        <Button
                          disabled={Boolean(acknowledgementDisabledReason)}
                          onClick={() => onAcknowledge(graphUnit, acknowledgementReason.trim())}
                          size="sm"
                          title="Lưu xác nhận rằng topology warning đã được reviewer kiểm tra và chấp nhận."
                          type="button"
                          variant="secondary"
                        >
                          {saving ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <ShieldCheck data-icon="inline-start" className="size-4" />}
                          Acknowledge with reason
                        </Button>
                        {acknowledgementDisabledReason ? (
                          <p className="text-[11px] leading-4 text-muted-foreground">{acknowledgementDisabledReason}</p>
                        ) : null}
                      </div>
                    ) : null}
                    {acknowledged && savedAcknowledgementReason ? (
                      <p className="basis-full text-xs leading-5 text-muted-foreground">
                        Reason: {savedAcknowledgementReason}
                      </p>
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
                {lowConfidenceTopologyIssue ? (
                  <p className="mt-3 rounded-lg border bg-background px-3 py-2 text-xs leading-5 text-muted-foreground">
                    Graph confidence is {Math.round(confidence * 100)}%, below the 70% auto-pass threshold. A human reviewer can clear this by checking the source diagram and acknowledging the topology warning with a reason.
                  </p>
                ) : null}
              </div>
            ) : null}
            <div className="grid gap-4 2xl:grid-cols-[minmax(22rem,0.85fr)_minmax(0,1.35fr)]">
              <div className="rounded-xl border bg-background p-3">
                <WorkflowMermaid graph={graph} />
              </div>
              <ScrollArea className="h-[30rem] rounded-xl border">
                <WorkflowBranchTable
                  canEdit={canEdit}
                  defaultAcknowledgementReason={savedAcknowledgementReason}
                  graph={graph}
                  graphUnit={graphUnit}
                  onReviewEdge={onReviewEdge}
                  saving={saving}
                />
              </ScrollArea>
            </div>
            <div className="rounded-xl border bg-muted/15 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="inline-flex items-center gap-1 text-sm font-semibold">
                  Decision branch review
                  <HelpTooltip text="Bảng này là publish gate riêng cho workflow diagram. Mỗi nhánh Yes/No từ decision node phải được Confirm hoặc Ack trước khi graph được xem là reviewed." />
                </p>
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
              <WorkflowUncertainEdgesPanel
                canEdit={canEdit}
                edges={Array.isArray(uncertainEdges) ? uncertainEdges : []}
                graph={graph}
                graphUnit={graphUnit}
                onAcknowledge={onAcknowledge}
                saving={saving}
                topologyAcknowledged={acknowledged}
              />
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
  canEdit,
  edges,
  graph,
  graphUnit,
  onAcknowledge,
  saving,
  topologyAcknowledged,
}: {
  canEdit: boolean;
  edges: NonNullable<WorkflowGraphMetadata["uncertain_edges"]>;
  graph: WorkflowGraphMetadata;
  graphUnit?: ExtractionUnit;
  onAcknowledge: (unit: ExtractionUnit, reason: string) => void;
  saving: boolean;
  topologyAcknowledged: boolean;
}) {
  const resolver = useMemo(() => buildWorkflowNodeResolver(graph), [graph]);
  const [acknowledgementReason, setAcknowledgementReason] = useState("");
  const savedReason = String(graphUnit?.metadata.graph_validation_acknowledged_reason ?? "").trim();
  const acknowledgementDisabledReason = !graphUnit
    ? "Graph unit is missing."
    : !canEdit
      ? "Inspect an editable draft version first."
      : saving
        ? "Saving acknowledgement..."
        : acknowledgementReason.trim().length < 8
          ? "Enter at least 8 characters after checking the source diagram."
          : "";
  return (
    <div className="rounded-xl border bg-background">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b px-3 py-2">
        <div>
          <p className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground">
            Uncertain edges needing review
            <HelpTooltip text="Đây là topology-level warning từ visual detector. Confirm/Ack branch trong bảng decision không xoá warning này; reviewer cần acknowledge uncertain topology sau khi đối chiếu source diagram." />
          </p>
          {topologyAcknowledged && savedReason ? (
            <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted-foreground">Acknowledged: {savedReason}</p>
          ) : edges.length ? (
            <p className="mt-1 text-[11px] leading-4 text-muted-foreground">Check these arrows against the source diagram, then acknowledge the topology warning here.</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Badge variant={edges.length && !topologyAcknowledged ? "destructive" : "outline"}>{edges.length}</Badge>
          {edges.length && topologyAcknowledged ? <Badge variant="secondary">acknowledged</Badge> : null}
        </div>
      </div>
      {edges.length ? (
        <div>
          {!topologyAcknowledged ? (
            <div className="grid gap-2 border-b bg-muted/10 p-3">
              <textarea
                className="min-h-16 rounded-md border bg-background px-3 py-2 text-xs leading-5 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                disabled={!graphUnit || !canEdit || saving}
                onChange={(event) => setAcknowledgementReason(event.target.value)}
                placeholder="Why are these uncertain edges acceptable after source review?"
                value={acknowledgementReason}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  className="h-8"
                  disabled={Boolean(acknowledgementDisabledReason)}
                  onClick={() => graphUnit ? onAcknowledge(graphUnit, acknowledgementReason.trim()) : undefined}
                  size="sm"
                  type="button"
                  variant="secondary"
                >
                  {saving ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <ShieldCheck data-icon="inline-start" className="size-3.5" />}
                  Acknowledge uncertain edges
                </Button>
                {acknowledgementDisabledReason ? (
                  <p className="text-[11px] leading-4 text-muted-foreground">{acknowledgementDisabledReason}</p>
                ) : null}
              </div>
            </div>
          ) : null}
          <ScrollArea className="h-64">
            <div className="divide-y">
              {edges.slice(0, 40).map((edge, index) => (
                <div className="grid gap-2 p-3 text-sm" key={`${edge.from_node}-${edge.to_node}-${index}`}>
                  <div className="grid grid-cols-[minmax(0,1fr)_5rem_minmax(0,1fr)] items-start gap-2">
                    <NodeSummary node={resolver.resolve(edge.from_node)} fallback={edge.from_node} />
                    <Badge className="justify-center" variant="outline">{edge.condition || "unclear"}</Badge>
                    <NodeSummary node={resolver.resolve(edge.to_node)} fallback={edge.to_node} />
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {typeof edge.confidence === "number" ? <Badge variant="outline">{Math.round(edge.confidence * 100)}% confidence</Badge> : null}
                    {topologyAcknowledged ? <Badge variant="secondary">covered by acknowledgement</Badge> : <Badge variant="destructive">needs topology ack</Badge>}
                  </div>
                  <p className="text-xs leading-5 text-muted-foreground">{edge.reason || "Detector could not fully confirm this edge direction or condition."}</p>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>
      ) : (
        <p className="p-3 text-xs leading-5 text-muted-foreground">No uncertain edges. Decision branches still require graph review before publishing workflow diagrams.</p>
      )}
    </div>
  );
}

function WorkflowBranchTable({
  canEdit,
  defaultAcknowledgementReason,
  graph,
  graphUnit,
  onReviewEdge,
  saving,
}: {
  canEdit: boolean;
  defaultAcknowledgementReason: string;
  graph: WorkflowGraphMetadata;
  graphUnit?: ExtractionUnit;
  onReviewEdge: (unit: ExtractionUnit, edge: WorkflowEdgeMetadata, status: "acknowledged" | "confirmed" | "rejected", reason: string) => void;
  saving: boolean;
}) {
  const resolver = useMemo(() => buildWorkflowNodeResolver(graph), [graph]);
  const [edgeReasons, setEdgeReasons] = useState<Record<string, string>>({});
  const displayEdges = workflowGraphDisplayEdges(graph);
  const branches = displayEdges.slice(0, 100).map((edge, index) => {
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
      reviewed: isWorkflowEdgeReviewed(review),
      to: resolver.resolve(edge.to_node),
      topologyStatus: edge.topology_status,
    };
  });

  return (
    <div className="divide-y">
      <div className="sticky top-0 z-10 grid grid-cols-[2.5rem_minmax(0,1fr)_7rem_minmax(0,1fr)_12rem] gap-3 border-b bg-card px-3 py-2 text-xs font-semibold text-muted-foreground">
        <span>#</span>
        <span>From</span>
        <span>Condition</span>
        <span>Next step</span>
        <span className="inline-flex items-center gap-1">
          Review
          <HelpTooltip text="Chỉ decision edges cần action. Non-decision edges hiển thị để tham khảo luồng, không cần Confirm/Ack." />
        </span>
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
                <Badge variant={branch.topologyStatus === "uncertain" ? "outline" : branch.review.status === "confirmed" ? "secondary" : branch.review.status === "rejected" ? "destructive" : branch.review.status === "acknowledged" ? "outline" : "destructive"}>
                  {branch.topologyStatus === "uncertain" ? "uncertain topology" : branch.review.status || "needs_review"}
                </Badge>
                {branch.topologyStatus === "uncertain" ? (
                  <p className="text-[11px] leading-4 text-muted-foreground">Review this in the uncertain edges panel, then acknowledge topology warnings.</p>
                ) : null}
                {branch.review.reason ? (
                  <p className="line-clamp-2 text-[11px] leading-4 text-muted-foreground">{branch.review.reason}</p>
                ) : null}
                {graphUnit && canEdit && !branch.reviewed && branch.topologyStatus !== "uncertain" ? (
                  <div className="grid gap-1.5">
                    <textarea
                      className="min-h-14 rounded-md border bg-background px-2 py-1.5 text-[11px] leading-4 outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
                      onChange={(event) => setEdgeReasons((current) => ({ ...current, [branch.edgeKey]: event.target.value }))}
                      placeholder={defaultAcknowledgementReason ? "Optional: blank uses saved topology reason" : "Reason for acknowledge/reject"}
                      title="Chỉ cần nhập khi muốn dùng reason riêng cho branch này. Nếu để trống khi Ack, hệ thống dùng saved topology reason."
                      value={edgeReasons[branch.edgeKey] ?? ""}
                    />
                    {defaultAcknowledgementReason ? (
                      <p className="text-[11px] leading-4 text-muted-foreground">Blank Ack uses: {defaultAcknowledgementReason}</p>
                    ) : null}
                    <div className="flex flex-wrap gap-1">
                      <Button
                        className="h-7 px-2 text-[11px]"
                        disabled={saving}
                        onClick={() => onReviewEdge(graphUnit, branch.edge, "confirmed", edgeReasons[branch.edgeKey] ?? "")}
                        size="sm"
                        title="Confirm: nhánh này rõ ràng đúng theo source diagram, không cần reason."
                        type="button"
                        variant="outline"
                      >
                        Confirm
                      </Button>
                      <Button
                        className="h-7 px-2 text-[11px]"
                        disabled={saving || workflowBranchEffectiveReason(edgeReasons[branch.edgeKey], defaultAcknowledgementReason).length < 8}
                        onClick={() => onReviewEdge(graphUnit, branch.edge, "acknowledged", workflowBranchEffectiveReason(edgeReasons[branch.edgeKey], defaultAcknowledgementReason))}
                        size="sm"
                        title="Ack: nhánh này còn mơ hồ nhưng reviewer chấp nhận sau khi xem source. Cần reason, hoặc dùng saved topology reason."
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
                        title="Reject: nhánh sai, cần reason để người sau biết graph phải sửa ở đâu."
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
              <Badge variant="outline">{branch.topologyStatus === "uncertain" ? "uncertain" : "not decision"}</Badge>
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
  const primary = node?.type === "decision"
    ? node?.question || node?.title || fallback || "Unknown step"
    : node?.title || node?.question || fallback || "Unknown step";
  const detailCandidates = [node?.content, node?.question, node?.title].filter(Boolean).map((value) => String(value));
  const detail = detailCandidates.find((value) => normalizeWorkflowKey(value) !== normalizeWorkflowKey(primary));
  return (
    <div className="min-w-0">
      <p className="line-clamp-2 font-medium leading-5">{primary}</p>
      {detail ? <p className="mt-1 line-clamp-4 text-xs leading-5 text-muted-foreground">{detail}</p> : null}
      <div className="mt-1 flex flex-wrap gap-1">
        {node?.semantic_node_type && node.semantic_node_type !== node.type ? <Badge variant="secondary">{node.semantic_node_type}</Badge> : null}
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
  const edges = workflowGraphDisplayEdges(graph);
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

function workflowGraphDisplayEdges(graph: WorkflowGraphMetadata): WorkflowEdgeMetadata[] {
  const confirmed = (graph.edges ?? []).map((edge) => ({ ...edge, topology_status: edge.topology_status ?? "confirmed" }));
  const uncertain = (graph.uncertain_edges ?? []).map((edge) => ({
    ...edge,
    review_reason: edge.reason,
    review_status: edge.review_status ?? "needs_review",
    topology_status: "uncertain",
  }));
  const seen = new Set<string>();
  return [...confirmed, ...uncertain].filter((edge) => {
    const key = workflowEdgeKey(edge);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return Boolean(edge.from_node && edge.to_node);
  });
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
    [node.id, node.title, node.question, node.content].filter(Boolean).forEach((value) => {
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
    const main = node?.question || node?.title || node?.content || readableWorkflowEndpoint(value);
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
    if (isWorkflowEdgeReviewed(review)) {
      reviewed += 1;
      return;
    }
    if (review.status === "acknowledged" && !review.reason) {
      missingReason += 1;
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

function workflowDecisionEdgesNeedingReview(graph?: WorkflowGraphMetadata, graphUnit?: ExtractionUnit) {
  return (graph?.edges ?? []).filter((edge) => isDecisionWorkflowEdge(edge, graph) && !isWorkflowEdgeReviewed(workflowEdgeReview(graphUnit, edge)));
}

function isWorkflowEdgeReviewed(review: { reason?: string; status?: string }) {
  return review.status === "confirmed" || (review.status === "acknowledged" && Boolean(review.reason));
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

function workflowBranchEffectiveReason(inputReason: string | undefined, defaultReason: string) {
  return (inputReason ?? "").trim() || defaultReason.trim();
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
  const haystack = normalizeWorkflowKey(`${node.id ?? ""} ${node.type ?? ""} ${node.semantic_node_type ?? ""} ${node.title ?? ""} ${node.question ?? ""} ${node.content ?? ""}`);
  return haystack.includes("decision") || haystack.includes("quyet dinh") || Boolean(node.question) || haystack.includes("?");
}

function classifyWorkflowNode(node: WorkflowNodeMetadata, index: number, nodeCount: number) {
  const raw = normalizeWorkflowKey(`${node.id || ""} ${node.type || ""} ${node.semantic_node_type || ""} ${node.title || ""} ${node.question || ""} ${node.content || ""}`);
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

function isSourceEvidenceUnit(unit: ExtractionUnit) {
  return unit.unit_type === "source_evidence_section" || unit.metadata.source_evidence_only === true || unit.metadata.retrieval_scope === "source_evidence";
}

function isWorkflowGraphUnit(unit: ExtractionUnit) {
  return unit.unit_type === "workflow_graph" || Boolean(unit.metadata.workflow_graph);
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

function readablePublishFailure(failure: string) {
  if (/^\d+_units_need_review$/.test(failure)) {
    return "Units still need review";
  }
  if (/^\d+_page_only_source_refs_need_ack$/.test(failure)) {
    return "Page-only source refs need acknowledgement";
  }
  if (/^\d+_units_missing_source_refs$/.test(failure)) {
    return "Units are missing source refs";
  }
  if (/^\d+_degraded_units_need_manual_curation$/.test(failure)) {
    return "Degraded units need manual curation";
  }
  if (failure.startsWith("workflow_graph_has_") && failure.includes("decision_edges_need_review")) {
    return "Decision branches need review";
  }
  if (failure.startsWith("workflow_v3_missing_visible_steps") || failure.startsWith("workflow_graph_missing_visible_steps")) {
    return "Workflow graph is missing visible steps";
  }
  if (failure.startsWith("workflow_v3_question_node_not_decision") || failure.startsWith("workflow_graph_question_steps_not_decisions")) {
    return "Visible decision was not extracted as a decision";
  }
  if (failure.startsWith("workflow_v3_missing_visible_edges")) {
    return "Workflow graph is missing visible arrows";
  }
  if (failure.includes("summary_like")) {
    return "Workflow graph looks like a summary";
  }
  const known: Record<string, string> = {
    archived_version: "Archived version cannot publish",
    extraction_failed_validation: "Extraction failed validation",
    historical_sheets_without_current_effective_date: "Historical source needs current effective date",
    missing_effective_from: "Effective date is missing",
    missing_full_sop_layer: "Document overview layer is missing",
    missing_owner_team: "Owner team is missing",
    missing_production_atomic_units: "Production atomic units are missing",
    missing_review_frequency: "Review frequency is missing",
    missing_last_reviewed_at: "Last reviewed date is missing",
    missing_next_review_due: "Next review due date is missing",
    missing_risk_level: "Risk level is missing",
    high_risk_review_due_in_past: "High-risk review due date is overdue",
    missing_workflow_graph: "Workflow graph is missing",
    no_extraction_units: "No extraction units",
    workflow_graph_acknowledgement_reason_missing: "Graph acknowledgement needs a reason",
    workflow_graph_decision_edges_missing: "Decision edges are missing",
    workflow_graph_low_confidence: "Workflow graph confidence needs acknowledgement",
    workflow_graph_missing_edges: "Workflow graph has no edges",
    workflow_graph_needs_review: "Workflow graph unit needs review",
  };
  return known[failure] ?? failure.replace(/_/g, " ");
}

function GovernanceSelect({
  label,
  onChange,
  options,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder: string;
  value: string;
}) {
  return (
    <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
      {label}
      <Select onValueChange={(nextValue) => onChange(nextValue === "unset" ? "" : nextValue)} value={value || "unset"}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="unset">{placeholder}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option} value={option}>{option}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

function documentGovernanceDefaults(document: DocumentSummary) {
  const metadata = document.metadata ?? {};
  return {
    riskLevel: String(metadata.risk_level ?? ""),
    reviewFrequency: String(metadata.review_frequency ?? ""),
    lastReviewedAt: String(metadata.last_reviewed_at ?? ""),
    nextReviewDue: String(metadata.next_review_due ?? ""),
  };
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
    content: `Draft ${requirement.label} stub. Curate this from source evidence before approval; publishing remains blocked while it needs review.`,
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

function buildWorkflowBulkEdgeReviewUpdate(
  unit: ExtractionUnit,
  edges: WorkflowEdgeMetadata[],
  status: "acknowledged",
  reason: string,
): ExtractionUnitUpdate {
  const now = new Date().toISOString();
  const reviews = {
    ...(typeof unit.metadata.workflow_edge_reviews === "object" && !Array.isArray(unit.metadata.workflow_edge_reviews)
      ? unit.metadata.workflow_edge_reviews as Record<string, unknown>
      : {}),
  };
  edges.forEach((edge) => {
    reviews[workflowEdgeKey(edge)] = {
      condition: edge.condition ?? "",
      from_node: edge.from_node ?? "",
      reason,
      reviewed_at: now,
      reviewed_by: "cs-lead-ui",
      status,
      to_node: edge.to_node ?? "",
    };
  });
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
    workflow_overview: "Short document-level workflow summary for quick orientation. It should not replace source evidence.",
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
