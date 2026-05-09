import { ArrowRight, CheckCircle2, FileClock, FileText, Search, ShieldCheck, WandSparkles } from "lucide-react";
import type { ElementType } from "react";

import { EmptyPanel, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatDate } from "@/lib/format";
import type { DocumentSummary, Homepage, SynonymGroup } from "@/types";
import type { Workspace } from "@/constants";

export function DashboardWorkspace({
  documents,
  homepage,
  onRunSearch,
  onWorkspaceChange,
  query,
  setQuery,
  synonyms,
}: {
  documents: DocumentSummary[];
  homepage?: Homepage;
  onRunSearch: () => void;
  onWorkspaceChange: (workspace: Workspace) => void;
  query: string;
  setQuery: (query: string) => void;
  synonyms: SynonymGroup[];
}) {
  const activeDocuments = documents.filter((document) => document.status === "active");
  const archivedDocuments = documents.length - activeDocuments.length;
  const reviewDocuments = activeDocuments.filter(
    (document) =>
      document.latest_review_status !== "approved" ||
      document.latest_version_status !== "published",
  );
  const activeSynonyms = synonyms.filter((group) => group.status === "active");
  const governedSynonyms = synonyms.filter((group) => group.status !== "archived");
  const recentlyUpdated = homepage?.recently_updated ?? [];

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(22rem,0.75fr)]">
      <section className="min-w-0 space-y-4">
        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle>Operations queue</CardTitle>
                <CardDescription>Start from the items that can change production search quality.</CardDescription>
              </div>
              <Button onClick={() => onWorkspaceChange("documents")} type="button">
                Review documents
                <ArrowRight data-icon="inline-end" className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="grid gap-3 md:grid-cols-4">
              <HealthCell icon={FileText} label="Active docs" value={activeDocuments.length} />
              <HealthCell icon={FileClock} label="Needs review" value={reviewDocuments.length} />
              <HealthCell icon={WandSparkles} label="Active synonyms" value={activeSynonyms.length} />
              <HealthCell icon={ShieldCheck} label="Archived docs" value={archivedDocuments} />
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle>Fast lookup</CardTitle>
                <CardDescription>Run the same search surface agents use, then inspect citations.</CardDescription>
              </div>
              <Button onClick={() => onWorkspaceChange("lookup")} type="button" variant="outline">
                Open lookup
              </Button>
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-8"
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      onRunSearch();
                      onWorkspaceChange("lookup");
                    }
                  }}
                  placeholder="không nhận đủ món, xác minh tài khoản, order id..."
                  value={query}
                />
              </div>
              <Button
                onClick={() => {
                  onRunSearch();
                  onWorkspaceChange("lookup");
                }}
                type="button"
              >
                Search
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>Document intake</CardTitle>
                <CardDescription>Files waiting for curation before they become answerable.</CardDescription>
              </div>
              <Badge variant="outline">{documents.length} sources</Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            {documents.length === 0 ? (
              <EmptyPanel icon={FileText} title="No source documents" text="Upload Excel, PDF, DOCX, or image files to build the curated knowledge base." compact />
            ) : (
              <div className="divide-y">
                {documents.slice(0, 7).map((document) => (
                  <button
                    className="grid w-full gap-3 py-3 text-left transition-colors hover:bg-muted/35 md:grid-cols-[minmax(0,1fr)_8rem_8rem_7rem]"
                    key={document.document_id}
                    onClick={() => onWorkspaceChange("documents")}
                    type="button"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{document.title}</div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">{document.source_filename}</div>
                    </div>
                    <div className="text-xs text-muted-foreground">{document.latest_document_type ?? "unknown"}</div>
                    <StatusBadge status={document.latest_review_status ?? "needs_review"} />
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
            <CardTitle>Governance posture</CardTitle>
            <CardDescription>Production search only trusts approved content.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-4">
            <ChecklistItem checked text="Published versions are immutable" />
            <ChecklistItem checked text="Draft documents stay out of agent lookup" />
            <ChecklistItem checked={activeSynonyms.length > 0} text="Synonyms are DB-managed, not hardcoded" />
            <ChecklistItem checked={reviewDocuments.length === 0} text="All active documents are reviewed" />
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Recently updated SOPs</CardTitle>
            <CardDescription>{recentlyUpdated.length} published records</CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {recentlyUpdated.length === 0 ? (
              <EmptyPanel icon={ShieldCheck} title="No SOPs loaded" text="Published SOPs appear here after API seed or migration." compact />
            ) : (
              <ScrollArea className="h-[21rem] pr-3">
                <div className="divide-y">
                  {recentlyUpdated.slice(0, 8).map((sop) => (
                    <div className="py-3" key={sop.id}>
                      <div className="text-sm font-medium leading-5">{sop.title}</div>
                      <div className="mt-1 flex flex-wrap gap-2">
                        <Badge variant="secondary">v{sop.current_version.version_number}</Badge>
                        <Badge variant="outline">{sop.vertical}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader className="border-b pb-4">
            <CardTitle>Relevance config</CardTitle>
            <CardDescription>{governedSynonyms.length} governed synonym groups.</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <Button className="w-full justify-center" onClick={() => onWorkspaceChange("synonyms")} type="button" variant="outline">
              Manage synonyms
            </Button>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function HealthCell({
  icon: Icon,
  label,
  value,
}: {
  icon: ElementType;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="flex items-center justify-between gap-3">
        <Icon className="size-4 text-muted-foreground" />
        <span className="text-xl font-semibold tabular-nums">{value}</span>
      </div>
      <div className="mt-2 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function ChecklistItem({ checked, text }: { checked: boolean; text: string }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <CheckCircle2 className={checked ? "mt-0.5 size-4 text-foreground" : "mt-0.5 size-4 text-muted-foreground"} />
      <span className={checked ? "text-foreground" : "text-muted-foreground"}>{text}</span>
    </div>
  );
}
