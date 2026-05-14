import {
  IconAlertTriangle as AlertTriangle,
  IconArrowRight as ArrowRight,
  IconBook as BookOpen,
  IconCircleCheck as CheckCircle2,
  IconDatabase as Database,
  IconFileTime as FileClock,
  IconFileText as FileText,
  IconGitPullRequest as GitPullRequest,
  IconDeviceDesktop as HardDrive,
  IconLayersIntersect as Layers3,
  IconRefresh as RefreshCw,
  IconSearch as Search,
  IconServer as Server,
  IconShieldCheck as ShieldCheck,
  IconSparkles as Sparkles,
  IconWand as WandSparkles
} from "@tabler/icons-react";

import { EmptyPanel, StatusBadge } from "@/components/common";
import { ActionItem, HealthPill, KpiCard } from "@/components/operations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate } from "@/lib/format";
import type { DocumentSummary, ServiceHealth, SystemHealth } from "@/types";
import type { Workspace } from "@/constants";

export function DashboardWorkspace({
  documents,
  isSystemHealthLoading,
  onRunSearch,
  onWorkspaceChange,
  query,
  refetchSystemHealth,
  setQuery,
  systemHealth,
}: {
  documents: DocumentSummary[];
  isSystemHealthLoading: boolean;
  onRunSearch: () => void;
  onWorkspaceChange: (workspace: Workspace) => void;
  query: string;
  refetchSystemHealth: () => void;
  setQuery: (query: string) => void;
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

  function runLookup() {
    onRunSearch();
    onWorkspaceChange("lookup");
  }

  return (
    <div className="space-y-4">
      <Card className="rounded-xl">
        <CardHeader className="border-b pb-4">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">Operational dashboard</Badge>
                <Badge variant="outline">Live document state</Badge>
              </div>
              <CardTitle className="mt-3 text-2xl">SOP operations cockpit</CardTitle>
              <CardDescription className="mt-2 max-w-[76ch] leading-6">
                Action-first view for lookup health, content quality, extraction review, and governance risk.
              </CardDescription>
            </div>
            <div className="flex w-full flex-col gap-2 sm:flex-row xl:max-w-xl">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-8"
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      runLookup();
                    }
                  }}
                  placeholder="Search SOP, rule, macro, case reason..."
                  value={query}
                />
              </div>
              <Button onClick={runLookup} type="button">
                Search
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid gap-3 md:grid-cols-4">
            <KpiCard icon={GitPullRequest} label="Review queue" tone={reviewDocuments.length ? "warning" : "default"} value={reviewDocuments.length} />
            <KpiCard icon={ShieldCheck} label="Published ready" value={publishedReadyDocuments.length} />
            <KpiCard icon={AlertTriangle} label="High-risk docs" tone={highRiskDocuments.length ? "warning" : "default"} value={highRiskDocuments.length} />
            <KpiCard icon={FileClock} label="Indexing issues" tone={indexingIssueDocuments.length ? "warning" : "default"} value={indexingIssueDocuments.length} />
          </div>
        </CardContent>
      </Card>

      <Tabs className="space-y-4" defaultValue="review">
        <TabsList className="grid h-auto grid-cols-2 gap-1 md:inline-grid md:grid-cols-3">
          <TabsTrigger value="review">Review Queue</TabsTrigger>
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
            health={systemHealth}
            isLoading={isSystemHealthLoading}
            onRefresh={refetchSystemHealth}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SystemHealthPanel({
  health,
  isLoading,
  onRefresh,
}: {
  health?: SystemHealth;
  isLoading: boolean;
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
          <CardContent className="space-y-3 pt-4">
            <KpiCard icon={CheckCircle2} label="Healthy" value={healthyCount} />
            <KpiCard icon={AlertTriangle} label="Needs attention" tone={degradedCount + downCount > 0 ? "warning" : "default"} value={degradedCount + downCount} />
          </CardContent>
        </Card>
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Debug order</CardTitle>
            <CardDescription>Use this order when a deployed page looks like a CORS failure.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-4 text-sm leading-6 text-muted-foreground">
            <p>1. API process and CORS headers.</p>
            <p>2. API to AI internal URL.</p>
            <p>3. AI to Postgres pgvector.</p>
            <p>4. Meilisearch indexing and query health.</p>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function ServiceHealthRow({ service }: { service: ServiceHealth }) {
  const Icon = serviceIcon(service.name);
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/30">
            <Icon className="size-4 text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{serviceLabel(service.name)}</div>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{service.detail}</p>
          </div>
        </div>
        <SystemStatusBadge status={service.status} />
      </div>
      <div className="mt-4 flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
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
        <div className="grid gap-3 md:grid-cols-5">
          <KpiCard icon={BookOpen} label="Active SOP docs" value={activeDocuments.length} />
          <KpiCard icon={ShieldCheck} label="High-risk" tone={highRiskDocuments.length ? "warning" : "default"} value={highRiskDocuments.length} />
          <KpiCard icon={AlertTriangle} label="Overdue review" tone={overdueReviewDocuments.length ? "warning" : "default"} value={overdueReviewDocuments.length} />
          <KpiCard icon={FileClock} label="Stale docs" tone={staleDocuments.length ? "warning" : "default"} value={staleDocuments.length} />
          <KpiCard icon={CheckCircle2} label="Avg health" value={`${averageHealth(activeDocuments)}%`} />
        </div>

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
      <div className="grid gap-3 md:grid-cols-4">
        <KpiCard icon={FileText} label="Uploaded" value={documents.length} />
        <KpiCard icon={Sparkles} label="Extracted" value={documents.filter((document) => document.latest_document_type && document.latest_document_type !== "unknown").length} />
        <KpiCard icon={GitPullRequest} label="Need review" tone={reviewDocuments.length ? "warning" : "default"} value={reviewDocuments.length} />
        <KpiCard icon={AlertTriangle} label="Failed/unknown" tone={failedExtractions.length ? "warning" : "default"} value={failedExtractions.length} />
      </div>

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
