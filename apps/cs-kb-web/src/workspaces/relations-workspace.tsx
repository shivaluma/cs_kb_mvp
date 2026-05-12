import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowRight, CheckCircle2, CircleHelp, FilePlus2, GitBranch, Loader2, PlusCircle, RefreshCw, Search, XCircle } from "lucide-react";

import { EmptyPanel, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useDocumentChunks } from "@/hooks/api/documents";
import { formatDate } from "@/lib/format";
import type { DocumentChunk, DocumentRelation, DocumentSummary, RelationStatus, RelationType } from "@/types";

type CreateRelationPayload = {
  metadata?: Record<string, unknown>;
  relationType: RelationType;
  sourceChunkId?: string;
  sourceDocumentId: string;
  targetDocumentId?: string;
  targetTitle: string;
};

const RELATION_TYPE_OPTIONS: Array<{ value: RelationType; label: string; help: string }> = [
  { value: "references", label: "references", help: "Chỉ xem thêm hoặc liên quan nhẹ." },
  { value: "requires", label: "requires", help: "Cần đọc hoặc làm theo SOP đích để xử lý đúng." },
  { value: "must_follow", label: "must_follow", help: "Bắt buộc tuân thủ SOP đích, có tác động mạnh tới publish gate." },
  { value: "routes_to", label: "routes_to", help: "Chuyển case, task, queue hoặc team." },
  { value: "escalates_to", label: "escalates_to", help: "Escalate lên team, lead hoặc level khác." },
  { value: "uses_macro", label: "uses_macro", help: "Dùng macro, script hoặc mẫu phản hồi từ SOP đích." },
  { value: "exception_of", label: "exception_of", help: "SOP hoặc rule này là ngoại lệ của SOP đích." },
  { value: "supersedes", label: "supersedes", help: "SOP này thay thế SOP hoặc version cũ." },
  { value: "related_to", label: "related_to", help: "Liên quan nghiệp vụ, không bắt buộc context expansion." },
  { value: "possible_conflict", label: "possible_conflict", help: "Có khả năng mâu thuẫn, cần CS Ops kiểm tra." },
];

const BLOCKING_RELATION_TYPES = new Set<RelationType>(["requires", "must_follow", "exception_of", "supersedes"]);

export function RelationsWorkspace({
  assigningRelationId,
  creatingRelation,
  documentsLoading,
  onAssign,
  onCreate,
  onRefresh,
  onReject,
  onSetStatus,
  onUploadTarget,
  publishedDocuments,
  rejectingRelationId,
  relations,
  relationsLoading,
  sourceDocuments,
  status,
}: {
  assigningRelationId: string;
  creatingRelation: boolean;
  documentsLoading: boolean;
  onAssign: (relation: DocumentRelation, targetDocumentId: string) => void;
  onCreate: (payload: CreateRelationPayload) => void;
  onRefresh: () => void;
  onReject: (relation: DocumentRelation) => void;
  onSetStatus: (status: RelationStatus | "all") => void;
  onUploadTarget: (relation: DocumentRelation) => void;
  publishedDocuments: DocumentSummary[];
  rejectingRelationId: string;
  relations: DocumentRelation[];
  relationsLoading: boolean;
  sourceDocuments: DocumentSummary[];
  status: RelationStatus | "all";
}) {
  const [assigningId, setAssigningId] = useState("");
  const [targetSearch, setTargetSearch] = useState("");
  const visibleRelations = relations;
  const unresolvedCount = relations.filter((relation) => relation.status === "unresolved").length;
  const suggestedCount = relations.filter((relation) => relation.status === "suggested").length;

  return (
    <div className="space-y-4">
      <ManualRelationCreator
        creating={creatingRelation}
        onCreate={onCreate}
        publishedDocuments={publishedDocuments}
        relations={relations}
        sourceDocuments={sourceDocuments}
      />
      <Card className="rounded-xl">
        <CardHeader className="border-b pb-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">AI gated</Badge>
                <Badge variant={unresolvedCount ? "destructive" : "outline"}>{unresolvedCount} unresolved</Badge>
                <Badge variant={suggestedCount ? "secondary" : "outline"}>{suggestedCount} suggested</Badge>
              </div>
              <CardTitle className="mt-3">Unresolved Relations</CardTitle>
              <CardDescription className="mt-2 max-w-[72ch] leading-6">
                Review extracted SOP dependencies. Search and chat expansion only use relations approved here.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Select onValueChange={(value) => onSetStatus(value as RelationStatus | "all")} value={status || "unresolved"}>
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unresolved">unresolved</SelectItem>
                  <SelectItem value="suggested">suggested</SelectItem>
                  <SelectItem value="approved">approved</SelectItem>
                  <SelectItem value="rejected">rejected</SelectItem>
                  <SelectItem value="archived">archived</SelectItem>
                  <SelectItem value="all">all</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={onRefresh} type="button" variant="outline">
                <RefreshCw data-icon="inline-start" className="size-4" />
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {relationsLoading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading relation queue
            </div>
          ) : visibleRelations.length === 0 ? (
            <div className="py-6">
              <EmptyPanel icon={GitBranch} title="No relations in this view" text="New related_document units will appear here after extraction." compact />
            </div>
          ) : (
            <div className="divide-y">
              <div className="grid gap-3 px-2 py-3 text-xs font-medium text-muted-foreground md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_7rem_8rem_18rem]">
                <span>Source SOP</span>
                <span>Target title</span>
                <span>Type</span>
                <span>Status</span>
                <span>Actions</span>
              </div>
              {visibleRelations.map((relation) => (
                <RelationRow
                  assigning={assigningRelationId === relation.id}
                  assigningOpen={assigningId === relation.id}
                  documentsLoading={documentsLoading}
                  key={relation.id}
                  onAssign={onAssign}
                  onOpenAssign={() => {
                    setAssigningId(assigningId === relation.id ? "" : relation.id);
                    setTargetSearch("");
                  }}
                  onReject={onReject}
                  onUploadTarget={onUploadTarget}
                  publishedDocuments={publishedDocuments}
                  rejecting={rejectingRelationId === relation.id}
                  relation={relation}
                  targetSearch={targetSearch}
                  setTargetSearch={setTargetSearch}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ManualRelationCreator({
  creating,
  onCreate,
  publishedDocuments,
  relations,
  sourceDocuments,
}: {
  creating: boolean;
  onCreate: (payload: CreateRelationPayload) => void;
  publishedDocuments: DocumentSummary[];
  relations: DocumentRelation[];
  sourceDocuments: DocumentSummary[];
}) {
  const [sourceDocumentId, setSourceDocumentId] = useState("");
  const [sourceScope, setSourceScope] = useState<"whole" | "unit">("whole");
  const [sourceChunkId, setSourceChunkId] = useState("");
  const [sourceUnitSearch, setSourceUnitSearch] = useState("");
  const [evidenceText, setEvidenceText] = useState("");
  const [targetDocumentId, setTargetDocumentId] = useState("__manual__");
  const [targetTitle, setTargetTitle] = useState("");
  const [targetSearch, setTargetSearch] = useState("");
  const [relationType, setRelationType] = useState<RelationType>("references");
  const chunksQuery = useDocumentChunks(sourceDocumentId);
  const sourceDocument = sourceDocuments.find((document) => document.document_id === sourceDocumentId);
  const selectedTarget = publishedDocuments.find((document) => document.document_id === targetDocumentId);
  const selectedChunk = (chunksQuery.data ?? []).find((chunk) => chunk.chunk_id === sourceChunkId);
  const effectiveTargetTitle = (selectedTarget?.title || targetTitle).trim();
  const resultStatus = selectedTarget ? "approved" : "unresolved";
  const affectsPublishGate = BLOCKING_RELATION_TYPES.has(relationType);
  const relationTypeHelp = RELATION_TYPE_OPTIONS.find((option) => option.value === relationType)?.help ?? "";
  const sourceLabel = sourceScope === "unit" && selectedChunk ? unitLabel(selectedChunk) : sourceDocument?.title || "Source SOP";
  const targetLabel = selectedTarget?.title || effectiveTargetTitle || "Unresolved target";
  const canCreate = Boolean(sourceDocumentId && effectiveTargetTitle && (sourceScope === "whole" || sourceChunkId));
  const sourceChunks = (chunksQuery.data ?? []).filter((chunk) => {
    const query = sourceUnitSearch.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return [chunk.heading, chunk.section, chunk.content].join(" ").toLowerCase().includes(query);
  }).slice(0, 6);
  const targetCandidates = publishedDocuments
    .filter((document) => document.document_id !== sourceDocumentId)
    .filter((document) => {
      const query = targetSearch.trim().toLowerCase();
      if (!query) {
        return true;
      }
      return [document.title, document.source_filename, document.latest_document_type ?? "", String(document.metadata?.owner_team ?? ""), String(document.metadata?.category ?? "")]
        .join(" ")
        .toLowerCase()
        .includes(query);
    })
    .slice(0, 6);
  const existingRelations = sourceDocumentId ? relations.filter((relation) => relation.source_document_id === sourceDocumentId).slice(0, 5) : [];

  useEffect(() => {
    setSourceChunkId("");
    setSourceUnitSearch("");
  }, [sourceDocumentId, sourceScope]);

  function submit() {
    if (!canCreate) {
      return;
    }
    onCreate({
      relationType,
      sourceChunkId: sourceScope === "unit" ? sourceChunkId : undefined,
      sourceDocumentId,
      targetDocumentId: selectedTarget?.document_id,
      targetTitle: effectiveTargetTitle,
      metadata: {
        affects_publish_gate: affectsPublishGate,
        evidence_text: evidenceText.trim(),
        manual_reason: evidenceText.trim(),
        publish_impact: affectsPublishGate ? "blocks_high_risk_when_unresolved" : "warning_only",
        risk_impact: affectsPublishGate ? "high" : relationType === "possible_conflict" ? "medium" : "low",
        source_chunk_heading: selectedChunk?.heading ?? "",
        source_chunk_section: selectedChunk?.section ?? "",
        source_scope: sourceScope,
      },
    });
    setTargetTitle("");
    setTargetSearch("");
    setTargetDocumentId("__manual__");
    setEvidenceText("");
  }

  return (
    <TooltipProvider delayDuration={150}>
      <Card className="rounded-xl">
        <CardHeader className="border-b pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">manual</Badge>
                <Badge variant="secondary">human curated</Badge>
              </div>
              <CardTitle className="mt-3">Add Relation</CardTitle>
              <CardDescription className="mt-2 max-w-[72ch] leading-6">
                Tạo edge nghiệp vụ có source, evidence, target và tác động publish rõ ràng. Relation chỉ được search/chat dùng sau khi approved.
              </CardDescription>
            </div>
            <Button disabled={!canCreate || creating} onClick={submit} type="button">
              {creating ? <Loader2 data-icon="inline-start" className="size-4 animate-spin" /> : <PlusCircle data-icon="inline-start" className="size-4" />}
              {selectedTarget ? "Add approved relation" : "Add unresolved relation"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <FieldLabel tooltip="SOP nguồn là tài liệu đang nhắc tới hoặc phụ thuộc vào SOP khác. Ví dụ: trong SOP A có câu “thực hiện theo SOP B” thì chọn SOP A ở đây.">
                  Source SOP
                </FieldLabel>
                <Select onValueChange={setSourceDocumentId} value={sourceDocumentId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose source" />
                  </SelectTrigger>
                  <SelectContent>
                    {sourceDocuments.map((document) => (
                      <SelectItem key={document.document_id} value={document.document_id}>
                        {document.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <FieldLabel tooltip="Whole SOP dùng khi relation áp dụng cho toàn tài liệu. Specific unit dùng khi relation chỉ áp dụng cho một rule, condition hoặc step cụ thể.">
                  Source scope
                </FieldLabel>
                <div className="inline-flex rounded-lg border bg-muted/20 p-1">
                  <Button className="h-8 px-3" onClick={() => setSourceScope("whole")} type="button" variant={sourceScope === "whole" ? "secondary" : "ghost"}>
                    Whole SOP
                  </Button>
                  <Button className="h-8 px-3" onClick={() => setSourceScope("unit")} type="button" variant={sourceScope === "unit" ? "secondary" : "ghost"}>
                    Specific unit
                  </Button>
                </div>
              </div>

              {sourceScope === "unit" ? (
                <div className="space-y-1.5">
                  <FieldLabel tooltip="Chọn rule/condition/step cụ thể trong source SOP. Field này trả lời câu hỏi relation xuất phát từ đoạn nào.">
                    Source unit
                  </FieldLabel>
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input className="pl-8" disabled={!sourceDocumentId || chunksQuery.isFetching} onChange={(event) => setSourceUnitSearch(event.target.value)} placeholder="Search unit or condition..." value={sourceUnitSearch} />
                  </div>
                  {sourceDocumentId ? (
                    <div className="max-h-48 overflow-auto rounded-lg border bg-muted/10 p-1">
                      {chunksQuery.isFetching ? (
                        <p className="px-2 py-2 text-xs text-muted-foreground">Loading source units...</p>
                      ) : sourceChunks.length === 0 ? (
                        <p className="px-2 py-2 text-xs text-muted-foreground">No unit matches this search.</p>
                      ) : (
                        sourceChunks.map((chunk) => (
                          <button
                            className={`w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted/50 ${chunk.chunk_id === sourceChunkId ? "bg-muted text-foreground" : "text-muted-foreground"}`}
                            key={chunk.chunk_id}
                            onClick={() => setSourceChunkId(chunk.chunk_id)}
                            type="button"
                          >
                            <span className="block truncate text-xs font-medium">{unitLabel(chunk)}</span>
                            <span className="mt-0.5 line-clamp-2 block text-xs">{chunk.content}</span>
                          </button>
                        ))
                      )}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="space-y-1.5">
                <FieldLabel tooltip="Paste câu gốc trong SOP hoặc lý do manual. Ví dụ: “CS thực hiện theo Quy định sử dụng tasklist”.">
                  Evidence / reason
                </FieldLabel>
                <textarea
                  className="min-h-20 w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none transition-shadow placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
                  onChange={(event) => setEvidenceText(event.target.value)}
                  placeholder="Dẫn chứng từ source SOP hoặc lý do CS Ops xác nhận relation này"
                  value={evidenceText}
                />
              </div>
            </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <FieldLabel tooltip={relationTypeHelp}>
                  Relation type
                </FieldLabel>
                <Select onValueChange={(value) => setRelationType(value as RelationType)} value={relationType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RELATION_TYPE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <FieldLabel tooltip="Tìm SOP đích đã publish. Chọn target ở đây sẽ tạo approved relation ngay. Nếu không tìm thấy, tạo unresolved target bên dưới.">
                  Target
                </FieldLabel>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input className="pl-8" onChange={(event) => setTargetSearch(event.target.value)} placeholder="Search published SOP..." value={targetSearch} />
                </div>
                <div className="max-h-52 overflow-auto rounded-lg border bg-muted/10 p-1">
                  <button
                    className={`w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted/50 ${targetDocumentId === "__manual__" ? "bg-muted text-foreground" : "text-muted-foreground"}`}
                    onClick={() => setTargetDocumentId("__manual__")}
                    type="button"
                  >
                    <span className="block text-xs font-medium">No matching published SOP</span>
                    <span className="mt-0.5 block text-xs">Tạo unresolved target để upload hoặc assign sau.</span>
                  </button>
                  {targetCandidates.map((document) => (
                    <button
                      className={`mt-1 w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted/50 ${document.document_id === targetDocumentId ? "bg-muted text-foreground" : "text-muted-foreground"}`}
                      key={document.document_id}
                      onClick={() => {
                        setTargetDocumentId(document.document_id);
                        setTargetTitle("");
                      }}
                      type="button"
                    >
                      <span className="block truncate text-xs font-medium">{document.title}</span>
                      <span className="mt-0.5 block truncate text-xs">
                        {document.latest_document_type || "SOP"} · {document.metadata?.owner_team ? `Owner: ${String(document.metadata.owner_team)} · ` : ""}v{document.latest_version_number ?? 1} · {document.latest_version_status || "unknown"} · {formatDate(document.updated_at)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {targetDocumentId === "__manual__" ? (
                <div className="space-y-1.5">
                  <FieldLabel tooltip="Nhập tên SOP còn thiếu. Relation sẽ ở trạng thái unresolved để CS Ops upload hoặc assign target sau.">
                    Unresolved target title
                  </FieldLabel>
                  <Input onChange={(event) => setTargetTitle(event.target.value)} placeholder="Tên SOP còn thiếu" value={targetTitle} />
                </div>
              ) : null}
            </div>
          </div>

          <div className="rounded-xl border bg-muted/15 p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="outline">Preview</Badge>
              <span className="max-w-72 truncate font-medium">{sourceLabel}</span>
              <ArrowRight className="size-4 text-muted-foreground" />
              <Badge variant={affectsPublishGate ? "secondary" : "outline"}>{relationType}</Badge>
              <ArrowRight className="size-4 text-muted-foreground" />
              <span className="max-w-72 truncate font-medium">{targetLabel}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant={resultStatus === "approved" ? "secondary" : "destructive"}>Result: {resultStatus}</Badge>
              <Badge variant={affectsPublishGate ? "destructive" : "outline"}>
                Publish impact: {affectsPublishGate ? "blocks high-risk if unresolved" : "warning only"}
              </Badge>
              <Badge variant="outline">Search/chat: {resultStatus === "approved" ? "enabled after create" : "disabled until approved"}</Badge>
            </div>
            {targetDocumentId === "__manual__" ? (
              <p className="mt-2 text-xs text-muted-foreground">Relation này sẽ unresolved. Sau khi tạo, dùng Assign existing SOP hoặc Upload target SOP trong danh sách bên dưới.</p>
            ) : null}
          </div>

          {existingRelations.length ? (
            <div className="rounded-xl border p-3">
              <p className="text-xs font-medium text-muted-foreground">Existing relations for this SOP</p>
              <div className="mt-2 grid gap-2">
                {existingRelations.map((relation) => (
                  <div className="flex flex-wrap items-center gap-2 text-xs" key={relation.id}>
                    <Badge variant={relation.status === "approved" ? "secondary" : relation.status === "unresolved" ? "destructive" : "outline"}>{relation.status}</Badge>
                    <Badge variant="outline">{relation.relation_type}</Badge>
                    <span className="truncate font-medium">{relation.target_title_resolved || relation.target_title}</span>
                    {typeof relation.metadata?.evidence_text === "string" && relation.metadata.evidence_text ? (
                      <span className="truncate text-muted-foreground">Evidence: {relation.metadata.evidence_text}</span>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}

function FieldLabel({ children, tooltip }: { children: ReactNode; tooltip: ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <p className="text-xs font-medium text-muted-foreground">{children}</p>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            aria-label={`Giải thích ${String(children)}`}
            className="inline-flex size-4 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            type="button"
          >
            <CircleHelp className="size-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-80 items-start text-left leading-5" side="top">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

function unitLabel(chunk: DocumentChunk) {
  const heading = chunk.heading || chunk.section || `Unit ${chunk.chunk_index + 1}`;
  return `${chunk.chunk_index + 1}. ${heading}`;
}

function RelationRow({
  assigning,
  assigningOpen,
  documentsLoading,
  onAssign,
  onOpenAssign,
  onReject,
  onUploadTarget,
  publishedDocuments,
  rejecting,
  relation,
  setTargetSearch,
  targetSearch,
}: {
  assigning: boolean;
  assigningOpen: boolean;
  documentsLoading: boolean;
  onAssign: (relation: DocumentRelation, targetDocumentId: string) => void;
  onOpenAssign: () => void;
  onReject: (relation: DocumentRelation) => void;
  onUploadTarget: (relation: DocumentRelation) => void;
  publishedDocuments: DocumentSummary[];
  rejecting: boolean;
  relation: DocumentRelation;
  setTargetSearch: (value: string) => void;
  targetSearch: string;
}) {
  const candidates = useMemo(() => {
    const query = targetSearch.trim().toLowerCase();
    return publishedDocuments
      .filter((document) => document.document_id !== relation.source_document_id)
      .filter((document) => !query || document.title.toLowerCase().includes(query) || document.source_filename.toLowerCase().includes(query))
      .slice(0, 8);
  }, [publishedDocuments, relation.source_document_id, targetSearch]);
  const resolvedTarget = relation.target_title_resolved || relation.target_title;
  const canResolve = relation.status === "unresolved" || relation.status === "suggested";
  const relationSource = typeof relation.metadata?.relation_source === "string" ? relation.metadata.relation_source : "";
  const evidenceText = typeof relation.metadata?.evidence_text === "string" ? relation.metadata.evidence_text : "";
  const sourceScope = typeof relation.metadata?.source_scope === "string" ? relation.metadata.source_scope : relation.source_chunk_id ? "unit" : "whole";
  const sourceChunkHeading = typeof relation.metadata?.source_chunk_heading === "string" ? relation.metadata.source_chunk_heading : "";
  const sourceUrl = typeof relation.metadata?.source_url === "string" ? relation.metadata.source_url : typeof relation.metadata?.target_url === "string" ? relation.metadata.target_url : "";

  return (
    <article className="px-2 py-3">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_7rem_8rem_18rem] md:items-start">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{relation.source_title}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {sourceScope === "unit" ? `Unit: ${sourceChunkHeading || relation.source_chunk_id}` : "Whole SOP"} · {formatDate(relation.updated_at)}
          </p>
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{resolvedTarget}</p>
          {relation.target_title_resolved ? <p className="mt-1 text-xs text-muted-foreground">Assigned from published SOP</p> : null}
          {relationSource ? <p className="mt-1 text-xs text-muted-foreground">{relationSource}</p> : null}
        </div>
        <Badge variant={relation.relation_type === "requires" ? "secondary" : "outline"}>{relation.relation_type}</Badge>
        <StatusBadge status={relation.status} />
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canResolve || assigning} onClick={onOpenAssign} size="sm" type="button" variant="outline">
            {assigning ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <CheckCircle2 data-icon="inline-start" className="size-3.5" />}
            Assign existing SOP
          </Button>
          {relation.status === "suggested" && relation.target_document_id ? (
            <Button disabled={assigning} onClick={() => onAssign(relation, relation.target_document_id as string)} size="sm" type="button" variant="secondary">
              {assigning ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <CheckCircle2 data-icon="inline-start" className="size-3.5" />}
              Approve suggestion
            </Button>
          ) : null}
          <Button disabled={!canResolve} onClick={() => onUploadTarget(relation)} size="sm" type="button" variant="outline">
            <FilePlus2 data-icon="inline-start" className="size-3.5" />
            Upload target SOP
          </Button>
          <Button disabled={!canResolve || rejecting} onClick={() => onReject(relation)} size="sm" type="button" variant="ghost">
            {rejecting ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <XCircle data-icon="inline-start" className="size-3.5" />}
            Reject
          </Button>
        </div>
      </div>
      {evidenceText || sourceUrl ? (
        <div className="mt-2 rounded-lg border bg-muted/15 px-3 py-2 text-xs leading-5 text-muted-foreground">
          {evidenceText ? <p>Evidence: {evidenceText}</p> : null}
          {sourceUrl ? <p className="truncate">URL: {sourceUrl}</p> : null}
        </div>
      ) : null}

      {assigningOpen && canResolve ? (
        <div className="mt-3 rounded-xl border bg-muted/15 p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-8" onChange={(event) => setTargetSearch(event.target.value)} placeholder="Filter published SOPs" value={targetSearch} />
          </div>
          <div className="mt-3 grid gap-2">
            {documentsLoading ? (
              <p className="text-sm text-muted-foreground">Loading published documents...</p>
            ) : candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">No published SOP matches. Upload the target first, publish it, then assign here.</p>
            ) : (
              candidates.map((document) => (
                <button
                  className="flex w-full items-center justify-between gap-3 rounded-lg border bg-background px-3 py-2 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
                  key={document.document_id}
                  onClick={() => onAssign(relation, document.document_id)}
                  type="button"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{document.title}</span>
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">{document.source_filename}</span>
                  </span>
                  <Badge variant="secondary">v{document.latest_version_number ?? 1}</Badge>
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}
    </article>
  );
}
