import { useState } from "react";
import {
  IconAlertTriangle as AlertTriangle,
  IconArrowRight as ArrowRight,
  IconCircleCheck as CheckCircle2,
  IconDatabase as Database,
  IconFileTime as FileClock,
  IconFileText as FileText,
  IconDeviceDesktop as HardDrive,
  IconLayersIntersect as Layers3,
  IconMessageReport as MessageReport,
  IconRefresh as RefreshCw,
  IconSearch as Search,
  IconServer as Server,
  IconWand as WandSparkles
} from "@tabler/icons-react";

import { EmptyPanel, StatusBadge } from "@/components/common";
import { ActionItem, HealthPill, StatStrip } from "@/components/operations";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate } from "@/lib/format";
import type { AdminResetStatus, DocumentSummary, FeedbackQueueItem, OpsAnalyticsResponse, ServiceHealth, SystemHealth } from "@/types";
import type { Workspace } from "@/constants";

export function DashboardWorkspace({
  documents,
  feedbackItems,
  adminResetStatus,
  isAdminResetStatusLoading,
  isResettingData,
  isSystemHealthLoading,
  opsAnalytics,
  onMagicReset,
  onRunSearch: _onRunSearch,
  onWorkspaceChange,
  query: _query,
  refetchSystemHealth,
  setQuery: _setQuery,
  systemHealth,
}: {
  adminResetStatus?: AdminResetStatus;
  documents: DocumentSummary[];
  feedbackItems: FeedbackQueueItem[];
  isAdminResetStatusLoading: boolean;
  isResettingData: boolean;
  isSystemHealthLoading: boolean;
  opsAnalytics?: OpsAnalyticsResponse;
  onMagicReset: (confirmation: string) => void;
  onRunSearch?: () => void;
  onWorkspaceChange: (workspace: Workspace) => void;
  query?: string;
  refetchSystemHealth: () => void;
  setQuery?: (query: string) => void;
  systemHealth?: SystemHealth;
}) {
  const activeDocuments = documents.filter((document) => document.status === "active");
  const reviewDocuments = activeDocuments.filter(
    (document) =>
      document.latest_review_status !== "approved" ||
      document.latest_version_status !== "published",
  );
  const publishedDocuments = activeDocuments.filter((document) => document.latest_version_status === "published");
  const publishedReadyDocuments = publishedDocuments.filter((document) => (document.latest_publish_state ?? "published_ready") === "published_ready");
  const indexingIssueDocuments = publishedDocuments.filter((document) =>
    ["published_indexing_failed", "published_indexing_pending", "publishing"].includes(document.latest_publish_state ?? ""),
  );
  const highRiskDocuments = activeDocuments.filter(isHighRiskDocument);
  const overdueReviewDocuments = publishedReadyDocuments.filter(isReviewOverdueDocument);
  const staleDocuments = activeDocuments.filter(isStaleDocument);
  const aiReviewDocuments = activeDocuments.filter((document) => document.latest_review_status !== "approved");

  return (
    <div className="space-y-4">
      <StatStrip
        items={[
          {
            hint: "Drafts and unpublished changes",
            key: "review",
            label: "Review queue",
            statusLabel: "Documents need review",
            tone: reviewDocuments.length ? "warning" : "default",
            value: reviewDocuments.length,
          },
          {
            hint: "Approved and published",
            key: "published",
            label: "Published ready",
            value: publishedReadyDocuments.length,
          },
          {
            hint: "Compliance or policy risk",
            key: "high-risk",
            label: "High-risk docs",
            statusLabel: "High-risk content exists",
            tone: highRiskDocuments.length ? "warning" : "default",
            value: highRiskDocuments.length,
          },
          {
            hint: "User reports to triage",
            key: "feedback",
            label: "Feedback groups",
            statusLabel: "Feedback needs triage",
            tone: feedbackItems.length ? "warning" : "default",
            value: feedbackItems.length,
          },
        ]}
      />

      <Tabs className="space-y-4" defaultValue="review">
        <TabsList className="grid h-auto grid-cols-2 gap-1 md:inline-grid md:grid-cols-4">
          <TabsTrigger value="review">Review Queue</TabsTrigger>
          <TabsTrigger value="usage">Usage Signals</TabsTrigger>
          <TabsTrigger value="health">Content Health</TabsTrigger>
          <TabsTrigger value="system">System Health</TabsTrigger>
        </TabsList>

        <TabsContent value="review">
          <ReviewQueue
            aiReviewDocuments={aiReviewDocuments}
            documents={documents}
            highRiskDocuments={highRiskDocuments}
            onWorkspaceChange={onWorkspaceChange}
            reviewDocuments={reviewDocuments}
          />
        </TabsContent>

        <TabsContent value="usage">
          <UsageSignals
            feedbackItems={feedbackItems}
            indexingIssueDocuments={indexingIssueDocuments}
            onWorkspaceChange={onWorkspaceChange}
            opsAnalytics={opsAnalytics}
          />
        </TabsContent>

        <TabsContent value="health">
          <ContentHealth
            activeDocuments={activeDocuments}
            highRiskDocuments={highRiskDocuments}
            onWorkspaceChange={onWorkspaceChange}
            overdueReviewDocuments={overdueReviewDocuments}
            staleDocuments={staleDocuments}
          />
        </TabsContent>

        <TabsContent value="system">
          <SystemHealthPanel
            adminResetStatus={adminResetStatus}
            health={systemHealth}
            isAdminResetStatusLoading={isAdminResetStatusLoading}
            isLoading={isSystemHealthLoading}
            isResettingData={isResettingData}
            onMagicReset={onMagicReset}
            onRefresh={refetchSystemHealth}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function UsageSignals({
  feedbackItems,
  indexingIssueDocuments,
  onWorkspaceChange,
  opsAnalytics,
}: {
  feedbackItems: FeedbackQueueItem[];
  indexingIssueDocuments: DocumentSummary[];
  onWorkspaceChange: (workspace: Workspace) => void;
  opsAnalytics?: OpsAnalyticsResponse;
}) {
  const metrics = opsAnalytics?.metrics ?? [];
  const eventCount = (key: string) => opsAnalytics?.events?.[key] ?? 0;
  const highFeedback = feedbackItems.filter((item) => item.severity === "high");

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(22rem,0.85fr)]">
      <section className="space-y-4">
        <StatStrip
          items={[
            { hint: "Lookup runs", key: "searches", label: "SOP searches", value: eventCount("sop_search") },
            { hint: "Grounded chat asks", key: "chat", label: "Chat messages", value: eventCount("chat_message_sent") },
            {
              hint: "All report counts",
              key: "reports",
              label: "Feedback reports",
              statusLabel: "Feedback needs triage",
              tone: feedbackItems.length ? "warning" : "default",
              value: feedbackItems.reduce((sum, item) => sum + item.count, 0),
            },
            {
              hint: "Index sync problems",
              key: "indexing",
              label: "Indexing issues",
              statusLabel: "Published content has indexing issues",
              tone: indexingIssueDocuments.length ? "warning" : "default",
              value: indexingIssueDocuments.length,
            },
          ]}
        />

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Adoption and retrieval quality</CardTitle>
            <CardDescription>Practical signals for whether agents are replacing Excel/email with approved SOP lookup.</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            {metrics.length ? (
              <ul className="divide-y">
                {metrics.map((metric) => (
                  <li className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0" key={metric.key}>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold">{metric.label}</div>
                      <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{metric.detail}</p>
                      {metric.target ? (
                        <p className="mt-1 text-[11px] text-muted-foreground">Target: {metric.target}</p>
                      ) : null}
                    </div>
                    <Badge variant={metric.tone === "warning" ? "outline" : "secondary"}>{metric.value}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyPanel
                compact
                icon={Search}
                text="Lookup, chat, feedback, macro, and tool events will populate this panel."
                title="No usage telemetry yet"
              />
            )}
          </CardContent>
        </Card>
      </section>

      <aside className="space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Feedback pressure</CardTitle>
            <CardDescription>Highest-risk report groups from CS users.</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            {highFeedback.length ? (
              <ul className="divide-y">
                {highFeedback.slice(0, 4).map((item) => (
                  <li className="space-y-1.5 py-3 first:pt-0" key={item.key}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold">{item.target_title || item.entity_id}</div>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {item.feedback_label}, {item.count} report{item.count === 1 ? "" : "s"}
                        </p>
                      </div>
                      <Badge variant="destructive">High</Badge>
                    </div>
                    <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{item.suggested_action}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyPanel
                compact
                icon={MessageReport}
                text="Wrong, outdated, missing-step, and bad-search reports will appear here."
                title="No high-risk feedback"
              />
            )}
            <Button
              className="mt-4 w-full"
              onClick={() => onWorkspaceChange("feedback")}
              type="button"
              variant="outline"
            >
              Open feedback queue
              <ArrowRight data-icon="inline-end" className="size-4" />
            </Button>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function SystemHealthPanel({
  adminResetStatus,
  health,
  isAdminResetStatusLoading,
  isLoading,
  isResettingData,
  onMagicReset,
  onRefresh,
}: {
  adminResetStatus?: AdminResetStatus;
  health?: SystemHealth;
  isAdminResetStatusLoading: boolean;
  isLoading: boolean;
  isResettingData: boolean;
  onMagicReset: (confirmation: string) => void;
  onRefresh: () => void;
}) {
  const services = health?.services ?? [];
  const downCount = services.filter((service) => service.status === "down").length;
  const degradedCount = services.filter((service) => service.status === "degraded" || service.status === "unknown").length;
  const healthyCount = services.filter((service) => service.status === "healthy").length;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Card className="rounded-xl">
        <CardHeader className="border-b pb-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <SystemStatusBadge status={health?.status ?? (isLoading ? "unknown" : "down")} />
                <Badge variant="outline">Auto refresh 30s</Badge>
              </div>
              <CardTitle className="mt-3">Infrastructure monitor</CardTitle>
              <CardDescription className="mt-2 max-w-[72ch] leading-6">
                Runtime checks for API, database, Meilisearch, AI retrieval service, pgvector, and Qdrant configuration.
              </CardDescription>
            </div>
            <Button onClick={onRefresh} type="button" variant="outline">
              <RefreshCw data-icon="inline-start" className="size-4" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          {isLoading && services.length === 0 ? (
            <EmptyPanel
              icon={Server}
              title="Checking services"
              text="The monitor is calling the API health endpoint and upstream dependencies."
            />
          ) : services.length === 0 ? (
            <EmptyPanel
              icon={AlertTriangle}
              title="No health data"
              text="The system health endpoint is unavailable or returned no service checks."
            />
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {services.map((service) => (
                <ServiceHealthRow key={service.name} service={service} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <aside className="space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Health summary</CardTitle>
            <CardDescription>
              {health?.checked_at ? `Last checked ${formatDate(health.checked_at)}` : "Waiting for first check"}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <StatStrip
              className="border-b-0 pb-0"
              items={[
                { key: "healthy", label: "Healthy", value: healthyCount },
                {
                  key: "attention",
                  label: "Needs attention",
                  statusLabel: "Service checks need attention",
                  tone: degradedCount + downCount > 0 ? "warning" : "default",
                  value: degradedCount + downCount,
                },
              ]}
            />
          </CardContent>
        </Card>
        <AdminResetPanel
          isLoading={isAdminResetStatusLoading}
          isResetting={isResettingData}
          onReset={onMagicReset}
          status={adminResetStatus}
        />
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Debug order</CardTitle>
            <CardDescription>Use this order when search, chat, or publish status looks stale.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 pt-4 text-sm">
            {[
              "API health and CORS",
              "API to AI service",
              "AI Postgres and pgvector",
              "Meilisearch index visibility",
            ].map((item, index) => (
              <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-center gap-2 rounded-lg border bg-muted/15 px-2.5 py-2" key={item}>
                <span className="text-xs font-semibold tabular-nums text-muted-foreground">{index + 1}</span>
                <span>{item}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function AdminResetPanel({
  isLoading,
  isResetting,
  onReset,
  status,
}: {
  isLoading: boolean;
  isResetting: boolean;
  onReset: (confirmation: string) => void;
  status?: AdminResetStatus;
}) {
  const [open, setOpen] = useState(false);
  const [typedConfirmation, setTypedConfirmation] = useState("");
  const requiredConfirmation = status?.required_confirmation ?? "";
  const totalRows = Object.values(status?.row_counts ?? {}).reduce((sum, count) => sum + count, 0);
  const canOpen = Boolean(status?.enabled) && !isLoading;
  const canConfirm = canOpen && typedConfirmation === requiredConfirmation && !isResetting;

  function closeDialog(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) {
      setTypedConfirmation("");
    }
  }

  return (
    <Card className="rounded-xl border-destructive/25">
      <CardHeader className="border-b pb-4">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-destructive/30 bg-destructive/10">
            <AlertTriangle className="size-4 text-destructive" />
          </div>
          <div className="min-w-0">
            <CardTitle>Magic reset</CardTitle>
            <CardDescription className="mt-1 leading-5">
              Clears uploaded KB data, generated chunks, chats, telemetry, and search documents; preserves curated synonym and taxonomy tables.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-4">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg border bg-muted/20 p-2">
            <div className="text-muted-foreground">Rows in scope</div>
            <div className="mt-1 text-sm font-semibold tabular-nums">{isLoading ? "..." : formatRowCount(totalRows)}</div>
          </div>
          <div className="rounded-lg border bg-muted/20 p-2">
            <div className="text-muted-foreground">Vector schema</div>
            <div className="mt-1 text-sm font-semibold tabular-nums">
              {status?.embedding_dimensions ? `${status.embedding_dimensions}d` : "..."}
            </div>
          </div>
        </div>
        {status?.group_counts ? (
          <div className="grid gap-1.5 text-xs text-muted-foreground">
            {Object.entries(status.group_counts).map(([group, count]) => (
              <div className="flex items-center justify-between rounded-md bg-muted/25 px-2 py-1" key={group}>
                <span>{group.replace(/_/g, " ")}</span>
                <span className="font-medium tabular-nums text-foreground">{formatRowCount(count)}</span>
              </div>
            ))}
          </div>
        ) : null}
        {status?.warning ? (
          <p className="rounded-lg border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
            {status.warning}
          </p>
        ) : null}
        <AlertDialog open={open} onOpenChange={closeDialog}>
          <AlertDialogTrigger asChild>
            <Button className="w-full" disabled={!canOpen || isResetting} type="button" variant="destructive">
              <WandSparkles data-icon="inline-start" className="size-4" />
              {isResetting ? "Resetting data" : "Magic reset data"}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Reset all knowledge data?</AlertDialogTitle>
              <AlertDialogDescription>
                This removes source documents, SOP versions, chunks, extraction jobs, chat history, audit telemetry, collection items, tools, action templates, and Meilisearch documents. It also rebuilds the chunk embedding column at the configured dimension.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-3">
              <div className="rounded-lg border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                Type <span className="font-semibold text-foreground">{requiredConfirmation}</span> to confirm.
              </div>
              <Input
                autoComplete="off"
                autoFocus
                onChange={(event) => setTypedConfirmation(event.target.value)}
                placeholder={requiredConfirmation}
                value={typedConfirmation}
              />
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isResetting}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className="border-destructive bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20"
                disabled={!canConfirm}
                onClick={(event) => {
                  if (!canConfirm) {
                    event.preventDefault();
                    return;
                  }
                  onReset(typedConfirmation);
                  closeDialog(false);
                }}
              >
                {isResetting ? "Resetting" : "Confirm reset"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}

function ServiceHealthRow({ service }: { service: ServiceHealth }) {
  const Icon = serviceIcon(service.name);
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md border bg-muted/30">
            <Icon className="size-4 text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{serviceLabel(service.name)}</div>
            <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-muted-foreground">{service.detail}</p>
          </div>
        </div>
        <SystemStatusBadge status={service.status} />
      </div>
      <div className="mt-3 flex items-center justify-between border-t pt-2 text-xs text-muted-foreground">
        <span>Latency</span>
        <span className="font-medium tabular-nums text-foreground">{service.latency_ms}ms</span>
      </div>
    </div>
  );
}

function SystemStatusBadge({ status }: { status: ServiceHealth["status"] }) {
  if (status === "healthy") {
    return <Badge variant="secondary">Healthy</Badge>;
  }
  if (status === "skipped") {
    return <Badge variant="outline">Not configured</Badge>;
  }
  if (status === "down") {
    return <Badge variant="destructive">Down</Badge>;
  }
  return <Badge variant="outline">Degraded</Badge>;
}

function serviceIcon(name: string) {
  if (name.includes("postgres") || name.includes("pgvector")) return Database;
  if (name.includes("meili")) return Search;
  if (name.includes("qdrant")) return HardDrive;
  if (name.includes("ai")) return WandSparkles;
  return Server;
}

function serviceLabel(name: string) {
  const labels: Record<string, string> = {
    api: "Go API",
    postgres: "API Postgres",
    meilisearch: "Meilisearch",
    ai_service: "AI service",
    ai_postgres_pgvector: "AI Postgres pgvector",
    qdrant: "Qdrant",
  };
  return labels[name] ?? name.replace(/_/g, " ");
}

function formatRowCount(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function ContentHealth({
  activeDocuments,
  highRiskDocuments,
  onWorkspaceChange,
  overdueReviewDocuments,
  staleDocuments,
}: {
  activeDocuments: DocumentSummary[];
  highRiskDocuments: DocumentSummary[];
  onWorkspaceChange: (workspace: Workspace) => void;
  overdueReviewDocuments: DocumentSummary[];
  staleDocuments: DocumentSummary[];
}) {
  const lowHealthDocs = [...activeDocuments]
    .sort((left, right) => healthScore(left) - healthScore(right))
    .slice(0, 6);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(22rem,0.8fr)]">
      <section className="space-y-4">
        <StatStrip
          items={[
            { hint: "Available to agents", key: "active", label: "Active SOPs", value: activeDocuments.length },
            {
              hint: "Extra review sensitivity",
              key: "high-risk",
              label: "High-risk",
              statusLabel: "High-risk content exists",
              tone: highRiskDocuments.length ? "warning" : "default",
              value: highRiskDocuments.length,
            },
            {
              hint: "Past next review date",
              key: "overdue",
              label: "Overdue review",
              statusLabel: "High-risk review is overdue",
              tone: overdueReviewDocuments.length ? "warning" : "default",
              value: overdueReviewDocuments.length,
            },
            {
              hint: "Updated over 60 days ago",
              key: "stale",
              label: "Stale docs",
              statusLabel: "Documents are stale",
              tone: staleDocuments.length ? "warning" : "default",
              value: staleDocuments.length,
            },
            { hint: "Rule-based score", key: "avg", label: "Avg health", value: `${averageHealth(activeDocuments)}%` },
          ]}
        />

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>SOP health list</CardTitle>
            <CardDescription>Rule-based score using freshness, review state, confidence, and risk metadata.</CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {lowHealthDocs.length === 0 ? (
              <EmptyPanel icon={FileText} title="No active documents" text="Upload and publish documents to start content health tracking." compact />
            ) : (
              <div className="divide-y">
                {lowHealthDocs.map((document) => (
                  <button
                    className="grid w-full gap-3 py-3 text-left transition-colors hover:bg-muted/35 md:grid-cols-[minmax(0,1fr)_7rem_8rem_7rem]"
                    key={document.document_id}
                    onClick={() => onWorkspaceChange("documents")}
                    type="button"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{document.title}</div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">{document.source_filename}</div>
                    </div>
                    <HealthPill score={healthScore(document)} />
                    <Badge variant={isHighRiskDocument(document) ? "destructive" : "outline"}>{isHighRiskDocument(document) ? "High risk" : "Normal"}</Badge>
                    <div className="text-xs text-muted-foreground">{formatDate(document.updated_at)}</div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <aside className="space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Needs attention</CardTitle>
            <CardDescription>Operational content actions, not BI decoration.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-4">
            {overdueReviewDocuments.length ? (
              <ActionItem
                action="Open documents"
                icon={AlertTriangle}
                onClick={() => onWorkspaceChange("documents")}
                title="High-risk SOP overdue review"
                text={`${overdueReviewDocuments.length} published high-risk SOP${overdueReviewDocuments.length === 1 ? "" : "s"} past next_review_due.`}
              />
            ) : null}
            <ActionItem
              action="Review docs"
              icon={FileClock}
              onClick={() => onWorkspaceChange("documents")}
              title={`${staleDocuments.length} stale documents`}
              text="Check high-risk policies before agents rely on old rules."
            />
            <ActionItem
              action="Open retrieval"
              icon={Layers3}
              onClick={() => onWorkspaceChange("retrieval")}
              title={`${highRiskDocuments.length} high-risk policies`}
              text="Validate atomic units and parent SOP citations."
            />
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function ReviewQueue({
  aiReviewDocuments,
  documents,
  highRiskDocuments,
  onWorkspaceChange,
  reviewDocuments,
}: {
  aiReviewDocuments: DocumentSummary[];
  documents: DocumentSummary[];
  highRiskDocuments: DocumentSummary[];
  onWorkspaceChange: (workspace: Workspace) => void;
  reviewDocuments: DocumentSummary[];
}) {
  const failedExtractions = documents.filter((document) => document.latest_document_type === "unknown");

  return (
    <div className="space-y-4">
      <StatStrip
        items={[
          { hint: "All source documents", key: "uploaded", label: "Uploaded", value: documents.length },
          {
            hint: "Typed by extraction",
            key: "extracted",
            label: "Extracted",
            value: documents.filter(
              (document) => document.latest_document_type && document.latest_document_type !== "unknown",
            ).length,
          },
          {
            hint: "Not approved or unpublished",
            key: "need-review",
            label: "Need review",
            statusLabel: "Documents need review",
            tone: reviewDocuments.length ? "warning" : "default",
            value: reviewDocuments.length,
          },
          {
            hint: "Extraction needs repair",
            key: "failed",
            label: "Failed or unknown",
            statusLabel: "Extraction has failed or unknown documents",
            tone: failedExtractions.length ? "warning" : "default",
            value: failedExtractions.length,
          },
        ]}
      />

      <Card className="rounded-xl">
        <CardHeader className="border-b pb-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle>AI extraction queue</CardTitle>
              <CardDescription>Review confidence, warnings, risk level, and publish readiness.</CardDescription>
            </div>
            <Button onClick={() => onWorkspaceChange("documents")} type="button">
              Open review workspace
              <ArrowRight data-icon="inline-end" className="size-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {documents.length === 0 ? (
            <EmptyPanel icon={FileText} title="No source documents" text="Upload Excel, PDF, DOCX, or image files to start the extraction queue." compact />
          ) : (
            <div className="divide-y">
              {documents.slice(0, 10).map((document) => (
                <button
                  className="grid w-full gap-3 py-3 text-left transition-colors hover:bg-muted/35 md:grid-cols-[minmax(0,1fr)_9rem_7rem_8rem_7rem]"
                  key={document.document_id}
                  onClick={() => onWorkspaceChange("documents")}
                  type="button"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{document.title}</div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">{document.source_filename}</div>
                  </div>
                  <Badge variant="outline">{document.latest_document_type ?? "unknown"}</Badge>
                  <div className="text-xs text-muted-foreground">{Math.round((document.latest_extraction_confidence ?? 0) * 100)}%</div>
                  <StatusBadge status={document.latest_review_status ?? "needs_review"} />
                  <Badge variant={highRiskDocuments.some((item) => item.document_id === document.document_id) ? "destructive" : "outline"}>
                    {highRiskDocuments.some((item) => item.document_id === document.document_id) ? "High risk" : "Normal"}
                  </Badge>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {aiReviewDocuments.length === 0 ? (
        <Card className="rounded-xl">
          <CardContent className="pt-6">
            <EmptyPanel icon={CheckCircle2} title="No SOP drafts waiting for review" text="Extraction queue is clear for this period." compact />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function isHighRiskDocument(document: DocumentSummary) {
  const metadata = document.metadata ?? {};
  const riskLevel = String(metadata.risk_level ?? metadata.riskLevel ?? "").toLowerCase();
  const serialized = JSON.stringify(metadata).toLowerCase();
  return (
    riskLevel === "high" ||
    riskLevel === "critical" ||
    serialized.includes("high-risk") ||
    serialized.includes("high risk") ||
    serialized.includes("compliance") ||
    serialized.includes("security") ||
    document.latest_document_type === "policy_rule" ||
    document.latest_document_type === "workflow_diagram"
  );
}

function isStaleDocument(document: DocumentSummary) {
  const ageMs = Date.now() - new Date(document.updated_at).getTime();
  return ageMs > 1000 * 60 * 60 * 24 * 60;
}

function isReviewOverdueDocument(document: DocumentSummary) {
  if (!isHighRiskDocument(document)) {
    return false;
  }
  const due = parseMetadataDate(document.metadata?.next_review_due);
  if (!due) {
    return false;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return due.getTime() < today.getTime();
}

function parseMetadataDate(value: unknown) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  date.setHours(0, 0, 0, 0);
  return date;
}

function healthScore(document: DocumentSummary) {
  let score = 92;
  if (document.latest_review_status !== "approved") {
    score -= 22;
  }
  if (document.latest_version_status !== "published") {
    score -= 18;
  }
  if (isStaleDocument(document)) {
    score -= 16;
  }
  if ((document.latest_extraction_confidence ?? 1) < 0.75) {
    score -= 14;
  }
  if (isHighRiskDocument(document)) {
    score -= 6;
  }
  return Math.max(28, Math.min(100, score));
}

function averageHealth(documents: DocumentSummary[]) {
  if (documents.length === 0) {
    return 0;
  }
  return Math.round(documents.reduce((sum, document) => sum + healthScore(document), 0) / documents.length);
}
