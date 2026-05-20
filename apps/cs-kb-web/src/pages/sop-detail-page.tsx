import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";

import { RouteLoading } from "@/components/route-loading";
import { workspacePaths } from "@/constants";
import { useRecordKBEvent } from "@/hooks/api/kb-index";
import { useSOPDetail } from "@/hooks/api/search";
import { categoryKey } from "@/lib/format";
import { useFeedback } from "@/providers/feedback-context";
import type { Macro, SOP } from "@/types";

const SOPDetailWorkspace = lazy(() =>
  import("@/workspaces/sop-detail-workspace").then((module) => ({ default: module.SOPDetailWorkspace })),
);

export function SOPDetailPage() {
  const navigate = useNavigate();
  const { sopId } = useParams({ from: "/sop/$sopId" });
  const sopQuery = useSOPDetail(sopId);
  const eventMutation = useRecordKBEvent();
  const { reportError, reportNotice } = useFeedback();
  const [copied, setCopied] = useState("");
  const recordedOpenRef = useRef("");

  useEffect(() => {
    if (!sopQuery.data) {
      return;
    }
    if (recordedOpenRef.current === sopQuery.data.current_version_id) {
      return;
    }
    recordedOpenRef.current = sopQuery.data.current_version_id;
    eventMutation.mutate({
      action: "full_sop_open",
      entity_type: "sop_version",
      entity_id: sopQuery.data.current_version_id,
      metadata: {
        sop_id: sopQuery.data.id,
        title: sopQuery.data.title,
        surface: "sop_detail_page",
      },
    });
  }, [eventMutation, sopQuery.data]);

  async function copyMacro(macro: Macro) {
    try {
      await navigator.clipboard.writeText(macro.content);
      setCopied(macro.title);
      window.setTimeout(() => setCopied(""), 1800);
      reportNotice(`Copied macro: ${macro.title}.`);
      eventMutation.mutate({
        action: "macro_copy",
        entity_type: "macro",
        metadata: { target_title: macro.title, sop_id: sopId, surface: "sop_detail_page" },
      });
    } catch {
      reportError("Clipboard permission blocked.");
    }
  }

  function searchRelated(query: string) {
    void navigate({
      to: "/search",
      search: { q: query } as never,
    });
  }

  function askChat(question: string) {
    void navigate({
      to: workspacePaths.chat,
      search: (question.trim() ? { q: question.trim() } : {}) as never,
    });
  }

  function openCategory(sop: SOP) {
    void navigate({
      to: "/category/$categoryKey",
      params: { categoryKey: categoryKey(sop.category || "uncategorized") },
    });
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading SOP" />}>
      <SOPDetailWorkspace
        copied={copied}
        error={sopQuery.error ? "Cannot open this SOP. It may be archived or unpublished." : ""}
        loading={sopQuery.isLoading}
        onAskChat={askChat}
        onCopyMacro={copyMacro}
        onOpenCategory={openCategory}
        onSearchRelated={searchRelated}
        sop={sopQuery.data ?? null}
      />
    </Suspense>
  );
}
