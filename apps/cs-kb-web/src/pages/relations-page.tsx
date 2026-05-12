import { lazy, Suspense } from "react";
import { useNavigate } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { workspacePaths } from "@/constants";
import { useDocuments } from "@/hooks/api/documents";
import { useAssignRelation, useRejectRelation, useRelations } from "@/hooks/api/relations";
import { useUrlSearch } from "@/hooks/use-url-search";
import { useFeedback } from "@/providers/feedback-context";
import type { DocumentRelation, RelationStatus } from "@/types";

const RelationsWorkspace = lazy(() =>
  import("@/workspaces/relations-workspace").then((module) => ({ default: module.RelationsWorkspace })),
);

export function RelationsPage() {
  const navigate = useNavigate();
  const { getParam, setParams } = useUrlSearch();
  const { reportError, reportNotice } = useFeedback();
  const status = (getParam("status", "unresolved") as RelationStatus | "all") || "unresolved";
  const relationsQuery = useRelations(status);
  const documentsQuery = useDocuments();
  const assignRelationMutation = useAssignRelation();
  const rejectRelationMutation = useRejectRelation();
  const publishedDocuments = (documentsQuery.data ?? []).filter(
    (document) => document.status === "active" && document.latest_version_status === "published",
  );

  function assignRelation(relation: DocumentRelation, targetDocumentId: string) {
    assignRelationMutation.mutate(
      { relationId: relation.id, targetDocumentId, actor: "cs-ops-ui" },
      {
        onSuccess: (updated) => reportNotice(`Approved ${updated.relation_type} relation to ${updated.target_title_resolved || updated.target_title}.`),
        onError: () => reportError("Assign failed. Target must be an active document with a current published version."),
      },
    );
  }

  function rejectRelation(relation: DocumentRelation) {
    rejectRelationMutation.mutate(
      { relationId: relation.id, actor: "cs-ops-ui", rejectionReason: "Rejected from Unresolved Relations page" },
      {
        onSuccess: () => reportNotice(`Rejected relation to ${relation.target_title}.`),
        onError: () => reportError("Reject failed. Check AI service health and retry."),
      },
    );
  }

  function uploadTarget(relation: DocumentRelation) {
    void navigate({
      to: workspacePaths.documents,
      search: {
        upload_title: relation.target_title,
        relation: relation.id,
      } as never,
    });
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading relations" />}>
      <RelationsWorkspace
        assigningRelationId={assignRelationMutation.isPending ? assignRelationMutation.variables?.relationId ?? "" : ""}
        documentsLoading={documentsQuery.isFetching}
        onAssign={assignRelation}
        onRefresh={() => void relationsQuery.refetch()}
        onReject={rejectRelation}
        onSetStatus={(nextStatus) => setParams({ status: nextStatus === "unresolved" ? "" : nextStatus })}
        onUploadTarget={uploadTarget}
        publishedDocuments={publishedDocuments}
        rejectingRelationId={rejectRelationMutation.isPending ? rejectRelationMutation.variables?.relationId ?? "" : ""}
        relations={relationsQuery.data ?? []}
        relationsLoading={relationsQuery.isFetching}
        status={status}
      />
    </Suspense>
  );
}
