import type { Dispatch, SetStateAction } from "react";
import { Archive, Database, FileText, GitBranch, History, Loader2, RefreshCw, ShieldCheck, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyPanel, Field, StatusBadge } from "@/components/common";
import { ExtractionReviewEditor } from "@/components/extraction-review-editor";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentChunk, DocumentSummary, ExtractionUnit, ExtractionUnitUpdate, UploadState, VersionSummary } from "@/types";

export function DocumentsWorkspace({
  busyKey,
  chunks,
  chunksLoading,
  documents,
  extractionUnits,
  extractionUnitsLoading,
  onArchiveDocument,
  onInspectVersion,
  onPublishVersion,
  onRefreshDocuments,
  onSelectDocument,
  onUpdateExtractionUnit,
  onUpload,
  selectedDocument,
  selectedChunkVersionId,
  savingUnitId,
  setSelectedDocument,
  setUpload,
  upload,
  versions,
}: {
  busyKey: string;
  chunks: DocumentChunk[];
  chunksLoading: boolean;
  documents: DocumentSummary[];
  extractionUnits: ExtractionUnit[];
  extractionUnitsLoading: boolean;
  onArchiveDocument: (document: DocumentSummary) => void;
  onInspectVersion: (versionId: string) => void;
  onPublishVersion: (versionId: string) => void;
  onRefreshDocuments: () => void;
  onSelectDocument: (documentId: string) => void;
  onUpload: () => void;
  selectedDocument: DocumentSummary | null;
  selectedChunkVersionId: string;
  setSelectedDocument: (document: DocumentSummary) => void;
  setUpload: Dispatch<SetStateAction<UploadState>>;
  onUpdateExtractionUnit: (unit: ExtractionUnit, update: ExtractionUnitUpdate) => void;
  savingUnitId: string;
  upload: UploadState;
  versions: VersionSummary[];
}) {
  const selectedFile = upload.file;
  const maxBytes = 15 * 1024 * 1024;
  const allowedExtensions = [".txt", ".md", ".markdown", ".pdf", ".docx", ".xlsx", ".xlsm", ".xls", ".png", ".jpg", ".jpeg", ".webp"];
  const validType = selectedFile
    ? allowedExtensions.some((extension) => selectedFile.name.toLowerCase().endsWith(extension))
    : false;
  const validSize = selectedFile ? selectedFile.size <= maxBytes : false;
  const uploadReady = Boolean(selectedFile && validType && validSize);
  const uploadSteps = ["Upload", "Extract", "Chunk", "Embed", "Index"];
  const selectedVersion = versions.find((version) => version.version_id === selectedChunkVersionId);
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

  return (
    <div className="grid gap-4 2xl:grid-cols-[22rem_minmax(0,1fr)]">
      <aside className="space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>New source</CardTitle>
            <CardDescription>Upload as draft. Review and publish happen after extraction.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="document-file">Source file</label>
              <Input
                accept=".txt,.md,.markdown,.pdf,.docx,.xlsx,.xlsm,.xls,.png,.jpg,.jpeg,.webp"
                id="document-file"
                onChange={(event) =>
                  setUpload((current) => ({
                    ...current,
                    file: event.target.files?.[0] ?? null,
                    status: "draft",
                  }))
                }
                type="file"
              />
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

            <Field label="Title" value={upload.title} onChange={(title) => setUpload((current) => ({ ...current, title }))} placeholder="Quy định xác minh tài khoản" />
            <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
              <Field label="Vertical" value={upload.vertical} onChange={(vertical) => setUpload((current) => ({ ...current, vertical }))} />
              <Field label="Audience" value={upload.audience} onChange={(audience) => setUpload((current) => ({ ...current, audience }))} />
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

            <Button className="w-full justify-center" disabled={busyKey === "upload" || !uploadReady} onClick={onUpload} type="button">
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
                <CardDescription>{documents.length} files</CardDescription>
              </div>
              <Button onClick={onRefreshDocuments} size="icon" type="button" variant="ghost">
                <RefreshCw className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <ScrollArea className="h-[32rem] pr-3">
              <div className="divide-y">
                {documents.length === 0 ? (
                  <EmptyPanel icon={FileText} title="No documents" text="Upload a source document to create the first draft." compact />
                ) : (
                  documents.map((document) => (
                    <button
                      className={cn(
                        "grid w-full gap-2 py-3 text-left transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                        selectedDocument?.document_id === document.document_id && "bg-muted/45",
                      )}
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
                        <Badge variant="outline">v{document.latest_version_number ?? "-"}</Badge>
                      </div>
                      <p className="truncate text-xs text-muted-foreground">{document.source_filename}</p>
                      <div className="flex flex-wrap gap-2">
                        <StatusBadge status={document.latest_review_status ?? "needs_review"} />
                        <Badge variant="outline">{document.latest_document_type ?? "unknown"}</Badge>
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
                  <Badge variant={selectedDocument.status === "active" ? "secondary" : "outline"}>{selectedDocument.status}</Badge>
                  <Badge variant="outline">{selectedDocument.latest_document_type ?? "unknown type"}</Badge>
                  <Button
                    disabled={busyKey === "archive-document" || selectedDocument.status === "archived"}
                    onClick={() => onArchiveDocument(selectedDocument)}
                    size="sm"
                    type="button"
                    variant="outline"
                  >
                    {busyKey === "archive-document" ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <Archive data-icon="inline-start" className="size-4" />}
                    Archive
                  </Button>
                </div>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="grid gap-3 md:grid-cols-4">
              <DocumentFact label="Review" value={selectedDocument?.latest_review_status ?? "-"} />
              <DocumentFact label="Version" value={selectedDocument?.latest_version_number ? `v${selectedDocument.latest_version_number}` : "-"} />
              <DocumentFact label="Confidence" value={selectedDocument?.latest_extraction_confidence ? `${Math.round(selectedDocument.latest_extraction_confidence * 100)}%` : "-"} />
              <DocumentFact label="Updated" value={selectedDocument ? formatDate(selectedDocument.updated_at) : "-"} />
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 xl:grid-cols-[minmax(20rem,0.72fr)_minmax(0,1.28fr)]">
          <Card className="rounded-xl">
            <CardHeader className="border-b pb-4">
              <CardTitle>Versions</CardTitle>
              <CardDescription>Publish locks a curated version and syncs indexes.</CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              {versions.length === 0 ? (
                <EmptyPanel icon={History} title="No versions loaded" text="Select a document to inspect immutable versions." compact />
              ) : (
                <div className="space-y-3">
                  {versions.map((version) => (
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
                          <Button disabled={busyKey === "publishing"} onClick={() => onPublishVersion(version.version_id)} size="sm" type="button">
                            {busyKey === "publishing" ? "Publishing" : "Publish"}
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
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="rounded-xl">
            <CardHeader className="border-b pb-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>Extraction review</CardTitle>
                  <CardDescription>Edit AI-extracted units before publishing.</CardDescription>
                </div>
                {reviewStats.total ? (
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">{reviewStats.reviewed}/{reviewStats.total} reviewed</Badge>
                    <Badge variant="outline">{reviewStats.security} security notes</Badge>
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
                <ScrollArea className="h-[35rem] pr-3">
                  <div className="space-y-3">
                    {extractionUnits.map((unit) => (
                      <ExtractionReviewEditor
                        disabled={selectedVersion?.status === "published"}
                        key={unit.unit_id}
                        onSave={onUpdateExtractionUnit}
                        saving={savingUnitId === unit.unit_id}
                        unit={unit}
                      />
                    ))}
                  </div>
                </ScrollArea>
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
              <EmptyPanel icon={Database} title="No chunks available" text="Draft or archived versions may not have active chunks selected." compact />
            ) : (
              <ScrollArea className="h-[22rem] pr-3">
                <div className="divide-y">
                  {chunks.map((chunk) => (
                    <article className="py-4" key={chunk.chunk_id}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="secondary">chunk {chunk.chunk_index}</Badge>
                          <Badge variant="outline">{chunk.section}</Badge>
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

function DocumentFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-sm font-medium">{value}</div>
    </div>
  );
}
