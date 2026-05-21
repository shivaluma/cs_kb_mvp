import {
  IconArrowLeft as ArrowLeft,
  IconArrowRight as ArrowRight,
  IconBook as BookOpen,
  IconClock as Clock,
  IconFolder as Folder,
  IconSearch as Search,
} from "@tabler/icons-react";
import type { ElementType } from "react";

import { EmptyPanel, MetaLine, TagSummary } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import type { SOP } from "@/types";

export function CategoryWorkspace({
  categoryKey,
  categoryLabel,
  loading,
  onOpenSOP,
  onSearchCategory,
  sops,
  totalSops,
}: {
  categoryKey: string;
  categoryLabel: string;
  loading: boolean;
  onOpenSOP: (sop: SOP) => void;
  onSearchCategory: () => void;
  sops: SOP[];
  totalSops: number;
}) {
  const sorted = [...sops].sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  const recentlyUpdatedCount = sorted.filter((sop) => daysSince(sop.updated_at) <= 7).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
          onClick={() => history.back()}
          type="button"
        >
          <ArrowLeft className="size-4" />
          Back
        </button>
        <Button onClick={onSearchCategory} type="button" variant="outline">
          <Search data-icon="inline-start" className="size-4" />
          Search this category
        </Button>
      </div>

      <section className="rounded-2xl border bg-card p-4 md:p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="min-w-0">
            <Badge variant="secondary">category</Badge>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">{categoryLabel}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              Category is a topic facet for browsing, search, and retrieval ranking. Ownership, routing, tools, templates, risk, and governance live in Collections.
            </p>
            <MetaLine className="mt-3" items={[categoryKey, `${sorted.length} matching SOPs`, `${totalSops} total published SOPs`]} />
          </div>
          <div className="grid content-start gap-2 sm:grid-cols-3 xl:grid-cols-1">
            <Metric label="SOPs" value={sorted.length} />
            <Metric label="Updated in 7d" value={recentlyUpdatedCount} />
            <Metric label="Total published" value={totalSops} />
          </div>
        </div>
      </section>

      {loading ? (
        <EmptyPanel compact icon={Folder} text="Loading published SOP category data." title="Loading category" />
      ) : null}

      {!loading && sorted.length === 0 ? (
        <EmptyPanel
          compact
          icon={BookOpen}
          text="No published SOP currently uses this category metadata. Try lookup search or review source metadata in Document Review."
          title="No SOPs in this category"
        />
      ) : null}

      <section className="grid gap-3">
        {sorted.map((sop) => (
          <article className="rounded-xl border bg-card p-4" key={sop.id}>
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="min-w-0">
                <MetaLine items={[sop.code, `v${sop.current_version.version_number}`, sop.owner_team, formatDate(sop.updated_at)]} maxItems={4} />
                <h3 className="mt-2 text-base font-semibold leading-6">{sop.title}</h3>
                <p className="mt-2 line-clamp-2 max-w-4xl text-sm leading-6 text-muted-foreground">{sop.summary}</p>
                <TagSummary className="mt-3" items={[...sop.case_reasons, ...sop.tags, ...sop.audience]} maxItems={5} />
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2 md:flex-col md:items-end">
                <Badge variant="secondary">{sop.current_version.status}</Badge>
                <Button className="h-8 px-2" onClick={() => onOpenSOP(sop)} size="sm" type="button" variant="outline">
                  Open SOP
                  <ArrowRight data-icon="inline-end" className="size-3.5" />
                </Button>
              </div>
            </div>
            <div className="mt-4 grid gap-2 border-t pt-3 sm:grid-cols-3">
              <SmallFact icon={Clock} label="Updated" value={formatDate(sop.updated_at)} />
              <SmallFact icon={Search} label="Views" value={String(sop.analytics.views)} />
              <SmallFact icon={Folder} label="Facet" value="Category" />
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border bg-background/70 px-3 py-2">
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function SmallFact({
  icon: Icon,
  label,
  value,
}: {
  icon: ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
      <Icon className="size-3.5 shrink-0" />
      <span className="shrink-0">{label}</span>
      <span className="min-w-0 truncate font-medium text-foreground">{value}</span>
    </div>
  );
}

function daysSince(value: string) {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) {
    return Number.POSITIVE_INFINITY;
  }
  return (Date.now() - timestamp) / 86_400_000;
}
