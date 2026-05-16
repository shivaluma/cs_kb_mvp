import {
  IconMessageReport as MessageReport,
  IconRefresh as RefreshCw
} from "@tabler/icons-react";

import { EmptyPanel } from "@/components/common";
import { StatStrip } from "@/components/operations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import type { FeedbackQueueItem, OpsAnalyticsResponse } from "@/types";

export function FeedbackWorkspace({
  analytics,
  feedbackItems,
  loading,
  onRefresh,
}: {
  analytics?: OpsAnalyticsResponse;
  feedbackItems: FeedbackQueueItem[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const highSeverity = feedbackItems.filter((item) => item.severity === "high");
  const wrongOutdated = analytics?.metrics.find((metric) => metric.key === "wrong_outdated_reports");
  const northStar = analytics?.metrics.find((metric) => metric.key === "quick_answer_action_usage");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">Last {analytics?.window_days ?? 7} days</Badge>
          <span className="text-sm text-muted-foreground">Triage repeated reports before they become SOP edits.</span>
        </div>
        <Button onClick={onRefresh} type="button" variant="outline">
          <RefreshCw data-icon="inline-start" className="size-4" />
          Refresh
        </Button>
      </div>

      <StatStrip
        items={[
          {
            hint: "Grouped repeat issues",
            key: "open",
            label: "Open report groups",
            statusLabel: "Feedback groups need review",
            tone: feedbackItems.length ? "warning" : "default",
            value: feedbackItems.length,
          },
          {
            hint: "Wrong, outdated, missing-step",
            key: "high",
            label: "High severity",
            statusLabel: "High severity feedback needs immediate attention",
            tone: highSeverity.length ? "danger" : "default",
            value: highSeverity.length,
          },
          {
            hint: "Policy trust issues",
            key: "wrong",
            label: "Wrong or outdated",
            statusLabel: "Wrong or outdated reports need review",
            tone: Number(wrongOutdated?.value ?? 0) ? "warning" : "default",
            value: wrongOutdated?.value ?? "0",
          },
          {
            hint: "Useful answer actions",
            key: "action-usage",
            label: "Action usage",
            value: northStar?.value ?? "0",
          },
        ]}
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(22rem,0.7fr)]">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Feedback queue</CardTitle>
            <CardDescription>Grouped by source, feedback type, and unit so repeat issues float up first.</CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {loading && !feedbackItems.length ? (
              <div className="py-6 text-sm text-muted-foreground">Loading feedback...</div>
            ) : feedbackItems.length === 0 ? (
              <EmptyPanel icon={MessageReport} title="No feedback yet" text="Feedback buttons on lookup units, chat sources, and macros will populate this queue." compact />
            ) : (
              <div className="divide-y">
                {feedbackItems.map((item) => (
                  <FeedbackRow item={item} key={item.key} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Usage metrics</CardTitle>
            <CardDescription>Operational proxies until real case runtime integration exists.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-4">
            {(analytics?.metrics ?? []).map((metric) => (
              <div className="rounded-xl border bg-card p-3" key={metric.key}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{metric.label}</div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{metric.detail}</p>
                  </div>
                  <Badge variant={metric.tone === "warning" ? "outline" : "secondary"}>{metric.value}</Badge>
                </div>
                {metric.target ? <div className="mt-2 text-[11px] text-muted-foreground">Target: {metric.target}</div> : null}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FeedbackRow({ item }: { item: FeedbackQueueItem }) {
  return (
    <article className="grid gap-3 py-3 md:grid-cols-[minmax(0,1fr)_9rem_8rem]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={item.severity === "high" ? "destructive" : item.severity === "medium" ? "outline" : "secondary"}>
            {item.feedback_label}
          </Badge>
          <Badge variant="outline">{item.entity_type}</Badge>
          <span className="text-xs text-muted-foreground">{item.count} report{item.count === 1 ? "" : "s"}</span>
        </div>
        <h3 className="mt-2 truncate text-sm font-semibold">{item.target_title || item.entity_id}</h3>
        {item.source_title ? <p className="mt-1 truncate text-xs text-muted-foreground">Source: {item.source_title}</p> : null}
        {item.sample_query ? <p className="mt-2 rounded-lg bg-muted/30 px-3 py-2 text-xs leading-5">Query: {item.sample_query}</p> : null}
        {item.sample_comment ? <p className="mt-2 text-xs leading-5 text-muted-foreground">Sample: {item.sample_comment}</p> : null}
        <p className="mt-2 text-xs leading-5 text-muted-foreground">Suggested action: {item.suggested_action}</p>
      </div>
      <div className="text-xs text-muted-foreground">
        <div className="font-medium text-foreground">Last seen</div>
        <div className="mt-1">{formatDate(item.last_seen)}</div>
      </div>
      <div className="text-xs text-muted-foreground">
        <div className="font-medium text-foreground">Triage path</div>
        <div className="mt-1">Draft update, relation fix, synonym, or macro request.</div>
      </div>
    </article>
  );
}
