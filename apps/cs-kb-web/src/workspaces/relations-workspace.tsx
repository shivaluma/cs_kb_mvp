import { useMemo, useState } from "react";
import { CheckCircle2, FilePlus2, GitBranch, Loader2, RefreshCw, Search, XCircle } from "lucide-react";

import { EmptyPanel, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDate } from "@/lib/format";
import type { DocumentRelation, DocumentSummary, RelationStatus } from "@/types";

export function RelationsWorkspace({
  assigningRelationId,
  documentsLoading,
  onAssign,
  onRefresh,
  onReject,
  onSetStatus,
  onUploadTarget,
  publishedDocuments,
  rejectingRelationId,
  relations,
  relationsLoading,
  status,
}: {
  assigningRelationId: string;
  documentsLoading: boolean;
  onAssign: (relation: DocumentRelation, targetDocumentId: string) => void;
  onRefresh: () => void;
  onReject: (relation: DocumentRelation) => void;
  onSetStatus: (status: RelationStatus | "all") => void;
  onUploadTarget: (relation: DocumentRelation) => void;
  publishedDocuments: DocumentSummary[];
  rejectingRelationId: string;
  relations: DocumentRelation[];
  relationsLoading: boolean;
  status: RelationStatus | "all";
}) {
  const [assigningId, setAssigningId] = useState("");
  const [targetSearch, setTargetSearch] = useState("");
  const visibleRelations = relations;
  const unresolvedCount = relations.filter((relation) => relation.status === "unresolved").length;

  return (
    <div className="space-y-4">
      <Card className="rounded-xl">
        <CardHeader className="border-b pb-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">AI gated</Badge>
                <Badge variant={unresolvedCount ? "destructive" : "outline"}>{unresolvedCount} unresolved</Badge>
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
                  <SelectItem value="approved">approved</SelectItem>
                  <SelectItem value="rejected">rejected</SelectItem>
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
  const canResolve = relation.status === "unresolved";

  return (
    <article className="px-2 py-3">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_7rem_8rem_18rem] md:items-start">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{relation.source_title}</p>
          <p className="mt-1 text-xs text-muted-foreground">{formatDate(relation.updated_at)}</p>
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{resolvedTarget}</p>
          {relation.target_title_resolved ? <p className="mt-1 text-xs text-muted-foreground">Assigned from published SOP</p> : null}
        </div>
        <Badge variant={relation.relation_type === "requires" ? "secondary" : "outline"}>{relation.relation_type}</Badge>
        <StatusBadge status={relation.status} />
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canResolve || assigning} onClick={onOpenAssign} size="sm" type="button" variant="outline">
            {assigning ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : <CheckCircle2 data-icon="inline-start" className="size-3.5" />}
            Assign existing SOP
          </Button>
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
