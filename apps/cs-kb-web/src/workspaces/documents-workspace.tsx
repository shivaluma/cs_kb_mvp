import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Archive, BookOpen, ClipboardList, Database, FileText, GitBranch, History, Layers3, Loader2, Network, RefreshCw, ShieldCheck, Upload, WandSparkles } from "lucide-react";

import { DocumentFact, ReadinessCheck } from "@/components/operations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyPanel, Field, StatusBadge } from "@/components/common";
import { ExtractionReviewEditor } from "@/components/extraction-review-editor";
import { API_BASE_URL } from "@/config";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentChunk, DocumentMetadataPreview, DocumentSummary, ExtractionUnit, ExtractionUnitUpdate, UploadState, VersionRawText, VersionSummary } from "@/types";

type WorkflowGraphMetadata = {
  workflow_id?: string;
  title?: string;
  start_node_id?: string;
  graph_confidence?: number;
  requires_human_review?: boolean;
  review_reason?: string;
  nodes?: Array<{ id?: string; type?: string; actor?: string; phase?: string; title?: string; question?: string }>;
  edges?: Array<{ from_node?: string; to_node?: string; condition?: string }>;
};

export function DocumentsWorkspace({
  busyKey,
  chunks,
  chunksLoading,
  documents,
  extractionUnits,
  extractionUnitsLoading,
  onArchiveDocument,
  onBulkReviewVersion,
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
  onArchiveDocument: (document: DocumentSummary) => void;
  onBulkReviewVersion: (versionId: string, scope?: "all" | "atomic") => void;
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
  const [sourceMode, setSourceMode] = useState<"file" | "text">("file");
  const [confirmingPublishVersionId, setConfirmingPublishVersionId] = useState("");
  const [rawTextError, setRawTextError] = useState("");
  const [rawTextName, setRawTextName] = useState("raw-sop-draft.md");
  const [rawTextStats, setRawTextStats] = useState({ bytes: 0, chars: 0, lines: 0 });
  const [sourceFilter, setSourceFilter] = useState<"active" | "archived" | "all">("active");
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
  const atomicUnits = extractionUnits.filter((unit) => !isDocumentLayer(unit) && unit.unit_type !== "workflow_graph" && !unit.metadata.workflow_graph);
  const selectedIsArchived = selectedDocument?.status === "archived";
  const pendingReviewCount = extractionUnits.filter((unit) => unit.review_status === "needs_review").length;
  const pendingAtomicReviewCount = atomicUnits.filter((unit) => unit.review_status === "needs_review").length;
  const highRiskUnitCount = extractionUnits.filter(hasRiskSignal).length;
  const effectiveDateReviewed = extractionUnits.some(hasEffectiveDateSignal);
  const ownerAssigned = Boolean(selectedDocument?.metadata?.owner_team || selectedDocument?.metadata?.ownerTeam);
  const policyRequiresGovernance = ["policy_rule", "policy_table"].includes(String(selectedDocument?.latest_document_type ?? ""));
  const workflowRequiresGraph = selectedDocument?.latest_document_type === "workflow_diagram";
  const workflowGraphConfidence = Number(workflowGraphUnit?.metadata.graph_confidence ?? workflowGraph?.graph_confidence ?? workflowGraphUnit?.confidence ?? 0);
  const pageOnlySourceRefUnacknowledged = extractionUnits.filter(
    (unit) => unit.metadata.source_ref_quality === "page_only" && unit.metadata.source_ref_acknowledged !== true,
  ).length;
  const aggregateExtractionText = extractionUnits
    .map((unit) => `${unit.title} ${unit.content} ${JSON.stringify(unit.metadata)}`)
    .join(" ")
    .toLowerCase();
  const isChatSocialWorkflow = workflowRequiresGraph && ["chat social", "fanpage", "pancake", "source internal", "84912345678"].some((term) => aggregateExtractionText.includes(term));
  const requiredChatSocialUnits = [
    { key: "sla_rule", label: "SLA rule", types: ["sla_rule"] },
    { key: "decision_rule", label: "Decision rule", types: ["decision_rule", "decision_point"] },
    { key: "escalation_rule", label: "Escalation rule", types: ["escalation_rule"] },
    { key: "case_creation_rule", label: "Case creation rule", types: ["case_creation_rule"] },
    { key: "handoff_rule", label: "SI/OB handoff rule", types: ["handoff_rule"] },
    { key: "macro_script", label: "Closing macro", types: ["macro_script"] },
    { key: "operational_note", label: "Operational note", types: ["operational_note"] },
  ];
  const missingChatSocialUnits = requiredChatSocialUnits.filter(
    (required) => !extractionUnits.some((unit) => required.types.includes(unit.unit_type) && unit.review_status !== "needs_review"),
  );
  const correctionRuleCount = extractionUnits.reduce((count, unit) => {
    const rules = unit.metadata.email_correction_rules;
    return count + (Array.isArray(rules) ? rules.length : 0);
  }, 0);
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
        ? `${workflowGraph?.nodes?.length ?? 0} nodes, ${workflowGraph?.edges?.length ?? 0} edges, ${Math.round(workflowGraphConfidence * 100)}% confidence`
        : "Workflow graph missing",
      label: "Workflow graph reviewed",
      passed: !workflowRequiresGraph || Boolean(workflowGraphUnit && workflowGraphUnit.review_status !== "needs_review" && workflowGraphConfidence >= 0.7 && (workflowGraph?.edges?.length ?? 0) > 0),
    },
    {
      detail: pageOnlySourceRefUnacknowledged
        ? `${pageOnlySourceRefUnacknowledged} page-only source refs still need acknowledgement`
        : "Source refs reviewed or structured",
      label: "Source refs acknowledged",
      passed: !workflowRequiresGraph || pageOnlySourceRefUnacknowledged === 0,
    },
    {
      detail: !isChatSocialWorkflow
        ? "Not a Chat Social workflow"
        : missingChatSocialUnits.length
          ? `Missing/review needed: ${missingChatSocialUnits.map((unit) => unit.label).join(", ")}`
          : "Required Chat Social units reviewed",
      label: "Chat Social workflow units",
      passed: !isChatSocialWorkflow || missingChatSocialUnits.length === 0,
    },
    {
      detail: pendingReviewCount === 0 ? "No unit needs review" : `${pendingReviewCount} unit(s) still need review`,
      label: "Atomic units reviewed",
      passed: pendingReviewCount === 0,
    },
    {
      detail: highRiskUnitCount || correctionRuleCount ? `${highRiskUnitCount} risk units, ${correctionRuleCount} correction rules` : "No risk/correction metadata detected",
      label: "High-risk warning acknowledged",
      passed: !policyRequiresGovernance || highRiskUnitCount > 0 || correctionRuleCount > 0,
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
  const bulkReviewBlocked =
    highRiskUnitCount > 0 ||
    selectedDocument?.latest_document_type === "workflow_diagram" ||
    Number(selectedVersion?.extraction_confidence ?? 1) < 0.85;
  const selectedVersionCanBulkReview = Boolean(selectedVersion) && canEditSelectedVersion && pendingReviewCount > 0 && !bulkReviewBlocked;
  const selectedVersionCanBulkReviewAtomic = Boolean(selectedVersion) && canEditSelectedVersion && pendingAtomicReviewCount > 0 && !bulkReviewBlocked;

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
                  className="w-full justify-start overflow-hidden"
                  onClick={() => fileInputRef.current?.click()}
                  type="button"
                  variant="outline"
                >
                  <Upload data-icon="inline-start" className="size-4 shrink-0" />
                  <span className="truncate">{selectedFile ? selectedFile.name : "Choose source file"}</span>
                </Button>
                {selectedFile ? (
                  <div className="rounded-lg border bg-muted/25 p-3">
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

        {workflowRequiresGraph ? (
          <WorkflowGraphPanel
            graph={workflowGraph}
            graphUnit={workflowGraphUnit}
            confidence={workflowGraphConfidence}
          />
        ) : null}

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Full SOP page</CardTitle>
                <CardDescription>Document-level layer for reading, training, and audit. Atomic units remain below for retrieval.</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">document layer</Badge>
                <Badge variant="outline">{atomicUnits.length} atomic units</Badge>
                {correctionRuleCount ? <Badge variant="outline">{correctionRuleCount} correction rules</Badge> : null}
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
                        ) : null}
                      </div>
                      <Button
                        className="mt-3"
                        onClick={() => onInspectVersion(version.version_id)}
                        size="sm"
                        type="button"
                        variant={selectedChunkVersionId === version.version_id ? "secondary" : "outline"}
                      >
                        Inspect version
                      </Button>
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
                  <CardDescription>Edit the full SOP page and atomic retrieval units before publishing.</CardDescription>
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
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="text-xs font-medium text-muted-foreground">Structured units</div>
                      <Badge variant="outline">{selectedIsArchived ? "audit only" : selectedVersion?.status === "published" ? "locked" : "editable draft"}</Badge>
                    </div>
                    <ScrollArea className="h-[52rem] pr-3">
                      <div className="space-y-3">
                        {fullSopUnit ? (
                          <section className="space-y-2">
                            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                              <BookOpen className="size-4" />
                              Document layer
                            </div>
                            <ExtractionReviewEditor
                              disabled={!canEditSelectedVersion}
                              onSave={onUpdateExtractionUnit}
                              saving={savingUnitId === fullSopUnit.unit_id}
                              unit={fullSopUnit}
                            />
                          </section>
                        ) : null}
                        <section className="space-y-2">
                          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                            <Layers3 className="size-4" />
                            Atomic retrieval units
                          </div>
                          {atomicUnits.map((unit) => (
                            <ExtractionReviewEditor
                              disabled={!canEditSelectedVersion}
                              key={unit.unit_id}
                              onSave={onUpdateExtractionUnit}
                              saving={savingUnitId === unit.unit_id}
                              unit={unit}
                            />
                          ))}
                        </section>
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

function ValidationPill({ text, valid }: { text: string; valid: boolean }) {
  return (
    <div className={cn("rounded-lg border px-2 py-1 text-[11px]", valid ? "bg-secondary text-secondary-foreground" : "border-destructive/30 bg-destructive/10 text-destructive")}>
      {valid ? "OK" : "Block"}: {text}
    </div>
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
  confidence,
  graph,
  graphUnit,
}: {
  confidence: number;
  graph?: WorkflowGraphMetadata;
  graphUnit?: ExtractionUnit;
}) {
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
            <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.25fr)_minmax(20rem,0.75fr)]">
              <div className="min-h-[30rem] rounded-xl border bg-background p-3">
                <WorkflowMermaid graph={graph} />
              </div>
              <ScrollArea className="h-[30rem] rounded-xl border p-3">
                <div className="space-y-3">
                  <div className="grid gap-3">
                    {(graph.nodes ?? []).slice(0, 40).map((node) => (
                      <div className="rounded-lg border bg-card p-3" key={node.id ?? node.title}>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="secondary">{node.type ?? "node"}</Badge>
                          {node.phase ? <Badge variant="outline">{node.phase}</Badge> : null}
                          {node.actor ? <Badge variant="outline">{node.actor}</Badge> : null}
                        </div>
                        <p className="mt-2 text-sm font-medium">{node.title ?? node.question}</p>
                        <p className="mt-1 font-mono text-[10px] text-muted-foreground">{node.id}</p>
                      </div>
                    ))}
                  </div>
                  {(graph.edges ?? []).length ? (
                    <div className="rounded-lg border bg-muted/20 p-3">
                      <p className="text-xs font-semibold text-muted-foreground">Edges</p>
                      <div className="mt-2 space-y-1">
                        {(graph.edges ?? []).slice(0, 80).map((edge, index) => (
                          <p className="font-mono text-[11px] text-muted-foreground" key={`${edge.from_node}-${edge.to_node}-${index}`}>
                            {edge.from_node} {edge.condition ? `--${edge.condition}--` : "--"}&gt; {edge.to_node}
                          </p>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </ScrollArea>
            </div>
          </div>
        ) : (
          <EmptyPanel icon={Network} title="No workflow graph" text="Re-extract this workflow diagram. Publish is blocked until graph nodes and edges exist." compact />
        )}
      </CardContent>
    </Card>
  );
}

function WorkflowMermaid({ graph }: { graph: WorkflowGraphMetadata }) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
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

  return (
    <div className="rounded-lg border bg-background p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-muted-foreground">Mermaid workflow preview</p>
        <Badge variant="outline">{graph.edges?.length ?? 0} edges</Badge>
      </div>
      {svg ? (
        <div className="overflow-auto rounded-md bg-muted/20 p-2">
          <div className="[&_svg]:mx-auto [&_svg]:max-w-none" dangerouslySetInnerHTML={{ __html: svg }} />
        </div>
      ) : error ? (
        <div className="rounded-md border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
          Mermaid could not render this graph. Use the node and edge list below to review the extraction.
          <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded border bg-background p-2 font-mono text-[10px]">{chart}</pre>
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
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];
  if (!nodes.length) {
    return "";
  }
  const nodeIdByOriginal = new Map<string, string>();
  const lines = ["flowchart LR"];

  nodes.slice(0, 80).forEach((node, index) => {
    const originalId = String(node.id || node.title || node.question || `node_${index}`);
    const mermaidId = `n${index}`;
    nodeIdByOriginal.set(originalId, mermaidId);
    if (node.title) {
      nodeIdByOriginal.set(String(node.title), mermaidId);
    }
    if (node.question) {
      nodeIdByOriginal.set(String(node.question), mermaidId);
    }
    const labelParts = [node.title || node.question || originalId, node.actor, node.phase].filter(Boolean);
    const label = escapeMermaidLabel(labelParts.join(" | "));
    lines.push(`  ${mermaidId}["${label}"]`);
  });

  edges.slice(0, 120).forEach((edge) => {
    const from = nodeIdByOriginal.get(String(edge.from_node || "")) ?? sanitizeMermaidId(edge.from_node);
    const to = nodeIdByOriginal.get(String(edge.to_node || "")) ?? sanitizeMermaidId(edge.to_node);
    if (!from || !to) {
      return;
    }
    const condition = String(edge.condition || "").trim();
    lines.push(condition ? `  ${from} -->|"${escapeMermaidLabel(condition)}"| ${to}` : `  ${from} --> ${to}`);
  });

  return lines.join("\n");
}

function sanitizeMermaidId(value?: string) {
  const normalized = String(value || "")
    .replace(/[^a-zA-Z0-9_]/g, "_")
    .replace(/^_+|_+$/g, "");
  return normalized ? `x_${normalized}` : "";
}

function escapeMermaidLabel(value: string) {
  return value.replace(/"/g, "'").replace(/\|/g, "/").slice(0, 140);
}

function isDocumentLayer(unit: ExtractionUnit) {
  return unit.unit_type === "full_sop" || unit.metadata.retrieval_scope === "document";
}

function hasRiskSignal(unit: ExtractionUnit) {
  const haystack = `${unit.unit_type} ${unit.title} ${JSON.stringify(unit.metadata)}`.toLowerCase();
  return haystack.includes("zt") || haystack.includes("risk") || haystack.includes("security") || haystack.includes("compliance");
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
