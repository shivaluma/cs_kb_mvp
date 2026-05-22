import { IconExternalLink as ExternalLink, IconCopy as Copy } from "@tabler/icons-react";
import { useEffect, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetaLine } from "@/components/common";
import { formatDate } from "@/lib/format";
import { blockMatchesHighlight, highlightedSegments, sourceDisplayLabel, type SourceDisplayGroup } from "@/lib/source-display";
import { isDebugUiEnabled } from "@/lib/ui-mode";
import { cn } from "@/lib/utils";

export function SourceContextCard({
  autoScrollToHighlight = false,
  className,
  compact = false,
  group,
  onCopyExcerpt,
  onOpenSource,
  onSelect,
  selected = false,
  showDebugScore,
}: {
  autoScrollToHighlight?: boolean;
  className?: string;
  compact?: boolean;
  group: SourceDisplayGroup;
  onCopyExcerpt?: (text: string) => void;
  onOpenSource?: () => void;
  onSelect?: () => void;
  selected?: boolean;
  showDebugScore?: boolean;
}) {
  const firstHighlightRef = useRef<HTMLElement | null>(null);
  const segments = highlightedSegments(group.content, group.highlights);
  const primaryMatch = group.matches[0];
  const debugScoreVisible = showDebugScore ?? isDebugUiEnabled();
  let highlightRefAssigned = false;
  const renderBlocks = group.blocks.length > 0 && (group.displayUnitType === "table_section" || segments.every((segment) => !segment.highlighted));
  const assignFirstHighlightRef = (node: HTMLElement | null) => {
    firstHighlightRef.current = node;
  };
  const metaItems = [
    group.category,
    ...group.collections.slice(0, 2),
    group.effectiveDate ? `effective ${group.effectiveDate}` : "",
    group.publishedAt ? `published ${formatDate(group.publishedAt)}` : "",
    group.lastUpdated ? formatDate(group.lastUpdated) : "",
  ].filter(Boolean);

  useEffect(() => {
    if (!debugScoreVisible) {
      return;
    }
    if (group.sourceResolutionStatus === "parent_missing") {
      console.warn("source_parent_missing", sourceLogPayload(group));
      return;
    }
    if (group.sourceResolutionStatus === "version_mismatch") {
      console.warn("source_version_mismatch", sourceLogPayload(group));
      return;
    }
    if (group.sourceResolutionStatus === "permission_denied") {
      console.warn("source_permission_denied", sourceLogPayload(group));
      return;
    }
    if (group.fallbackExcerpts.length) {
      console.debug("source_highlight_failed", sourceLogPayload(group));
      return;
    }
    if (group.highlights.length) {
      console.debug("source_highlight_success", sourceLogPayload(group));
    }
  }, [debugScoreVisible, group]);

  useEffect(() => {
    if (autoScrollToHighlight) {
      firstHighlightRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [autoScrollToHighlight, group.id, group.highlights.length]);

  return (
    <article
      onClick={onSelect}
      onKeyDown={(event) => {
        if (!onSelect || (event.key !== "Enter" && event.key !== " ")) {
          return;
        }
        event.preventDefault();
        onSelect();
      }}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      className={cn(
        "min-w-0 rounded-lg border bg-card text-left transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
        onSelect && "cursor-pointer",
        selected ? "border-foreground/60 bg-muted/35" : "hover:bg-muted/20",
        className,
      )}
    >
      <div className={cn("space-y-3", compact ? "p-3" : "p-4")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary">{sourceDisplayLabel(group.displayUnitType)}</Badge>
              <Badge variant="outline">v{group.versionNumber}</Badge>
              {group.matches.length > 1 ? <Badge variant="outline">{group.matches.length} matches</Badge> : null}
            </div>
            <h3 className="mt-2 text-sm font-semibold leading-snug">{group.title}</h3>
            {primaryMatch?.sectionTitle ? (
              <p className="mt-1 truncate text-xs text-muted-foreground">{primaryMatch.sectionTitle}</p>
            ) : null}
            {metaItems.length ? <MetaLine className="mt-1" items={metaItems} /> : null}
          </div>
          {debugScoreVisible ? (
            <div className="shrink-0 text-right text-[11px] text-muted-foreground">
              <div>score</div>
              <div className="font-medium tabular-nums text-foreground">{group.score.toFixed(4)}</div>
            </div>
          ) : null}
        </div>

        {renderBlocks ? (
          <div className={cn("grid gap-1.5 text-sm leading-6", compact ? "max-h-72 overflow-hidden" : "max-h-[32rem] overflow-auto pr-1")}>
            {group.blocks.map((block) => {
              const highlighted = blockMatchesHighlight(block, group.highlights);
              const ref = highlighted && !highlightRefAssigned ? assignFirstHighlightRef : undefined;
              if (highlighted) {
                highlightRefAssigned = true;
              }
              return (
                <div
                  className={cn(
                    "whitespace-pre-wrap break-words rounded-md border px-3 py-2",
                    highlighted ? "border-amber-400/60 bg-amber-200/45 text-foreground dark:bg-amber-300/15" : "bg-muted/15 text-muted-foreground",
                  )}
                  key={block.id || `${block.source_anchor?.table_id}-${block.source_anchor?.row_index}`}
                  ref={ref}
                >
                  {block.title && group.displayUnitType !== "table_section" ? <p className="mb-1 text-xs font-medium text-foreground">{block.title}</p> : null}
                  {block.content}
                </div>
              );
            })}
          </div>
        ) : (
          <div className={cn("whitespace-pre-wrap break-words text-sm leading-7", compact ? "line-clamp-6" : "max-h-[32rem] overflow-auto pr-1")}>
            {segments.map((segment, index) => {
              if (!segment.highlighted) {
                return <span key={`${segment.text}-${index}`}>{segment.text}</span>;
              }
              const ref = highlightRefAssigned ? undefined : assignFirstHighlightRef;
              highlightRefAssigned = true;
              return (
                <mark
                  className="rounded-[3px] bg-amber-200/75 px-0.5 text-foreground ring-1 ring-amber-400/40 dark:bg-amber-300/25 dark:ring-amber-300/30"
                  key={`${segment.text}-${index}`}
                  ref={ref}
                >
                  {segment.text}
                </mark>
              );
            })}
          </div>
        )}

        {group.fallbackExcerpts.length ? (
          <div className="rounded-lg border bg-muted/20 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Relevant excerpt</p>
            <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-xs leading-5 text-muted-foreground">
              {group.fallbackExcerpts[0]}
            </p>
          </div>
        ) : null}

        {(onOpenSource || onCopyExcerpt) ? (
          <div className="flex flex-wrap gap-2 border-t pt-2">
            {onOpenSource ? (
              <Button className="h-8 rounded-full px-3" onClick={(event) => { event.stopPropagation(); onOpenSource(); }} size="sm" type="button" variant="outline">
                <ExternalLink data-icon="inline-start" className="size-3.5" />
                Open in SOP
              </Button>
            ) : null}
            {onCopyExcerpt ? (
              <Button className="h-8 rounded-full px-3" onClick={(event) => { event.stopPropagation(); onCopyExcerpt(primaryMatch?.excerpt || group.content); }} size="sm" type="button" variant="ghost">
                <Copy data-icon="inline-start" className="size-3.5" />
                Copy excerpt
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function sourceLogPayload(group: SourceDisplayGroup) {
  return {
    chunk_ids: group.matches.map((match) => match.chunkId),
    reason: group.sourceResolutionReason,
    section_id: group.matches[0]?.result.source_anchor?.section_id || group.results[0]?.section_id,
    sop_id: group.documentId,
    sop_version_id: group.versionId,
  };
}
