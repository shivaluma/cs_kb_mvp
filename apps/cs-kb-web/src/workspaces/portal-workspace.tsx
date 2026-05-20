import {
  IconArrowRight as ArrowRight,
  IconBook as BookOpen,
  IconClock as Clock,
  IconEye as Eye,
  IconFolder as Folder,
  IconMessage as MessageSquareText,
  IconSearch as Search,
  IconSparkles as Sparkles,
} from "@tabler/icons-react";

import { EmptyPanel, MetaLine, TagSummary } from "@/components/common";
import { SearchBar } from "@/components/search-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { categoryKey, formatDate, labelFromKey } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Homepage, OpsAnalyticsResponse, SOP } from "@/types";

export function PortalWorkspace({
  analytics,
  homepage,
  loading,
  onOpenCategory,
  onOpenChat,
  onOpenSOP,
  onSearch,
  query,
  setQuery,
  sops,
}: {
  analytics?: OpsAnalyticsResponse;
  homepage: Homepage;
  loading: boolean;
  onOpenCategory: (categoryKey: string) => void;
  onOpenChat: (query: string) => void;
  onOpenSOP: (sop: SOP) => void;
  onSearch: (query?: string) => void;
  query: string;
  setQuery: (query: string) => void;
  sops: SOP[];
}) {
  const publishedSops = uniqueSops([...sops, ...homepage.recently_updated, ...homepage.most_viewed]);
  const popularSops = uniqueSops([...homepage.most_viewed, ...publishedSops].sort(compareByViews)).slice(0, 4);
  const recentSops = uniqueSops([...homepage.recently_updated, ...publishedSops].sort(compareByUpdatedAt)).slice(0, 5);
  const categoryGroups = buildCategoryGroups(publishedSops, homepage).slice(0, 8);
  const quickQueries = buildQuickQueries(analytics, publishedSops, categoryGroups).slice(0, 10);
  const updatedThisWeek = publishedSops.filter((sop) => daysSince(sop.updated_at) <= 7).length;
  const totalViews = publishedSops.reduce((sum, sop) => sum + (sop.analytics?.views ?? 0), 0);

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border bg-card p-4 md:p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="min-w-0 space-y-4">
            <div className="space-y-2">
              <Badge variant="secondary">published SOP portal</Badge>
              <h2 className="max-w-3xl text-2xl font-semibold tracking-tight md:text-3xl">
                Find the approved handling path before opening a case response.
              </h2>
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
                Search, browse, or jump into grounded chat using the same approved SOP index agents use in production.
              </p>
            </div>
            <SearchBar
              actionLabel="Search SOP"
              id="portal-sop-search"
              loading={loading}
              onChange={setQuery}
              onSearch={() => onSearch(query)}
              placeholder="Search case reason, policy, channel, macro, or customer issue"
              value={query}
            />
            <div className="flex flex-wrap gap-2">
              {quickQueries.map((item) => (
                <button
                  className="rounded-full border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
                  key={item}
                  onClick={() => {
                    setQuery(item);
                    onSearch(item);
                  }}
                  type="button"
                >
                  {item}
                </button>
              ))}
              {!quickQueries.length ? (
                <span className="text-xs leading-7 text-muted-foreground">Upload and publish SOPs to populate quick searches.</span>
              ) : null}
            </div>
          </div>
          <div className="grid content-start gap-2 sm:grid-cols-2 xl:grid-cols-1">
            <PortalMetric label="Published SOPs" value={publishedSops.length} />
            <PortalMetric label="Categories" value={categoryGroups.length} />
            <PortalMetric label="Updated this week" value={updatedThisWeek} />
            <PortalMetric label="Recorded views" value={totalViews} />
          </div>
        </div>
      </section>

      {!loading && !publishedSops.length ? (
        <EmptyPanel
          compact
          icon={BookOpen}
          text="Published SOPs from the governed index will appear here after review and publish."
          title="No published SOPs yet"
        />
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(22rem,0.75fr)]">
        <div className="space-y-4">
          <SectionHeader
            actionLabel="Open lookup"
            icon={Sparkles}
            onAction={() => onSearch(query || quickQueries[0] || "")}
            title="Pinned and popular"
          />
          <div className="grid gap-3 md:grid-cols-2">
            {popularSops.map((sop) => (
              <SOPPortalCard key={sop.id} onOpen={() => onOpenSOP(sop)} sop={sop} />
            ))}
            {loading && popularSops.length === 0 ? (
              <LoadingBlock label="Loading published SOPs..." />
            ) : null}
          </div>
        </div>

        <aside className="space-y-4">
          <SectionHeader icon={Folder} title="Browse category" />
          <div className="grid gap-2">
            {categoryGroups.map((group) => (
              <button
                className="flex items-center justify-between gap-3 rounded-xl border bg-card px-3 py-3 text-left transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
                key={group.key}
                onClick={() => onOpenCategory(group.key)}
                type="button"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">{group.label}</span>
                  <span className="block text-xs text-muted-foreground">{group.count} approved SOP{group.count === 1 ? "" : "s"}</span>
                </span>
                <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
              </button>
            ))}
            {!loading && !categoryGroups.length ? (
              <LoadingBlock label="Categories appear after SOPs are published." />
            ) : null}
          </div>
        </aside>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <SectionHeader icon={Clock} title="Recently updated" />
          <SOPCompactList emptyLabel="No recent SOP updates." onOpenSOP={onOpenSOP} sops={recentSops} />
        </div>
        <div className="space-y-4">
          <SectionHeader icon={Eye} title="Most accessed" />
          <SOPCompactList emptyLabel="Usage appears after agents open SOPs." onOpenSOP={onOpenSOP} sops={popularSops} showViews />
        </div>
      </section>

      <section className="flex flex-col gap-3 rounded-2xl border bg-muted/25 p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="text-sm font-semibold">Need scoped reasoning?</h3>
          <p className="mt-1 text-sm text-muted-foreground">Start chat from the current search phrase and keep the answer grounded to published SOPs.</p>
        </div>
        <Button onClick={() => onOpenChat(query || quickQueries[0] || "")} type="button" variant="outline">
          <MessageSquareText data-icon="inline-start" className="size-4" />
          Open SOP Chat
        </Button>
      </section>
    </div>
  );
}

function PortalMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border bg-background/70 px-3 py-2">
      <div className="text-lg font-semibold tabular-nums">{value.toLocaleString()}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function SectionHeader({
  actionLabel,
  icon: Icon,
  onAction,
  title,
}: {
  actionLabel?: string;
  icon: typeof Search;
  onAction?: () => void;
  title: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <Icon className="size-4 shrink-0 text-muted-foreground" />
        <h3 className="truncate text-sm font-semibold">{title}</h3>
      </div>
      {actionLabel && onAction ? (
        <Button className="h-8 px-2" onClick={onAction} size="sm" type="button" variant="ghost">
          {actionLabel}
          <ArrowRight data-icon="inline-end" className="size-3.5" />
        </Button>
      ) : null}
    </div>
  );
}

function SOPPortalCard({ onOpen, sop }: { onOpen: () => void; sop: SOP }) {
  return (
    <article className="rounded-xl border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <MetaLine items={[sop.code, `v${sop.current_version.version_number}`, sop.category]} maxItems={3} />
          <h3 className="mt-2 line-clamp-2 text-base font-semibold leading-6">{sop.title}</h3>
        </div>
        <Badge className="shrink-0" variant="secondary">{sop.current_version.status}</Badge>
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{sop.summary}</p>
      <TagSummary className="mt-3" items={[...sop.case_reasons, ...sop.tags]} maxItems={3} />
      <div className="mt-4 flex items-center justify-between gap-3">
        <MetaLine items={[formatDate(sop.updated_at), `${sop.analytics.views} views`]} maxItems={2} />
        <Button className="h-8 px-2" onClick={onOpen} size="sm" type="button" variant="outline">
          Open
          <ArrowRight data-icon="inline-end" className="size-3.5" />
        </Button>
      </div>
    </article>
  );
}

function SOPCompactList({
  emptyLabel,
  onOpenSOP,
  showViews = false,
  sops,
}: {
  emptyLabel: string;
  onOpenSOP: (sop: SOP) => void;
  showViews?: boolean;
  sops: SOP[];
}) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      {sops.map((sop, index) => (
        <button
          className={cn(
            "grid w-full grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
            index > 0 && "border-t",
          )}
          key={sop.id}
          onClick={() => onOpenSOP(sop)}
          type="button"
        >
          <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-xs font-semibold tabular-nums text-muted-foreground">
            {index + 1}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{sop.title}</span>
            <MetaLine items={[sop.category, formatDate(sop.updated_at)]} maxItems={2} />
          </span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {showViews ? `${sop.analytics.views} views` : `v${sop.current_version.version_number}`}
          </span>
        </button>
      ))}
      {sops.length === 0 ? (
        <div className="px-3 py-6 text-sm text-muted-foreground">{emptyLabel}</div>
      ) : null}
    </div>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return <div className="rounded-xl border border-dashed px-3 py-6 text-sm text-muted-foreground">{label}</div>;
}

type CategoryGroup = {
  key: string;
  label: string;
  count: number;
};

function buildCategoryGroups(sops: SOP[], homepage: Homepage): CategoryGroup[] {
  const groups = new Map<string, CategoryGroup>();
  for (const shortcut of homepage.category_shortcuts ?? []) {
    const key = categoryKey(shortcut.key || shortcut.label);
    if (key) {
      groups.set(key, { key, label: shortcut.label || labelFromKey(key), count: 0 });
    }
  }
  for (const sop of sops) {
    const key = categoryKey(sop.category || "Uncategorized");
    if (!key) {
      continue;
    }
    const current = groups.get(key) ?? { key, label: sop.category || labelFromKey(key), count: 0 };
    groups.set(key, { ...current, count: current.count + 1 });
  }
  return [...groups.values()].sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

function buildQuickQueries(analytics: OpsAnalyticsResponse | undefined, sops: SOP[], categories: CategoryGroup[]) {
  const candidates = [
    ...(analytics?.recent_queries ?? []).map((item) => item.query),
    ...(analytics?.popular_queries ?? []).map((item) => item.query),
    ...categories.map((item) => item.label),
    ...sops.flatMap((sop) => [...sop.case_reasons, ...sop.tags]).slice(0, 16),
  ];
  const seen = new Set<string>();
  return candidates.filter((item) => {
    const value = item.trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function uniqueSops(sops: SOP[]) {
  const seen = new Set<string>();
  return sops.filter((sop) => {
    if (!sop.id || seen.has(sop.id)) {
      return false;
    }
    seen.add(sop.id);
    return true;
  });
}

function compareByViews(left: SOP, right: SOP) {
  return (right.analytics?.views ?? 0) - (left.analytics?.views ?? 0);
}

function compareByUpdatedAt(left: SOP, right: SOP) {
  return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
}

function daysSince(value: string) {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) {
    return Number.POSITIVE_INFINITY;
  }
  return (Date.now() - timestamp) / 86_400_000;
}
