import {
  IconArrowRight as ArrowRight,
  IconBook as BookOpen,
  IconClock as Clock,
  IconEye as Eye,
  IconFolder as Folder,
  IconMessage as MessageSquareText,
  IconSearch as Search,
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
  suggestions,
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
  suggestions: string[];
  setQuery: (query: string) => void;
  sops: SOP[];
}) {
  const publishedSops = uniqueSops([...sops, ...homepage.recently_updated, ...homepage.most_viewed]);
  const popularSops = uniqueSops([...homepage.most_viewed, ...publishedSops].sort(compareByViews)).slice(0, 4);
  const recentSops = uniqueSops([...homepage.recently_updated, ...publishedSops].sort(compareByUpdatedAt)).slice(0, 6);
  const categoryGroups = buildCategoryGroups(publishedSops, homepage).slice(0, 8);
  const quickQueries = buildQuickQueries(analytics, publishedSops, categoryGroups).slice(0, 8);
  const totalPublished = publishedSops.length;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <section className="space-y-4">
        <div className="space-y-1.5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">SOP portal</p>
          <h2 className="max-w-2xl text-xl font-semibold leading-tight tracking-tight md:text-2xl">
            Find the approved handling path before opening a case response.
          </h2>
          <p className="max-w-[65ch] text-sm leading-6 text-muted-foreground">
            {totalPublished
              ? `${totalPublished} published SOP${totalPublished === 1 ? "" : "s"} across ${categoryGroups.length} categor${categoryGroups.length === 1 ? "y" : "ies"}. Search, browse, or jump into grounded chat.`
              : "Publish SOPs from Documents to populate the portal."}
          </p>
        </div>

        <SearchBar
          actionLabel="Search SOPs"
          id="portal-sop-search"
          loading={loading}
          minLength={2}
          onChange={setQuery}
          onSearch={() => onSearch(query)}
          onSuggestionSelect={(suggestion) => {
            setQuery(suggestion);
            onSearch(suggestion);
          }}
          placeholder="Try: tài xế bị khóa, mẫu email mở đầu, khi nào xin lỗi"
          suggestions={suggestions}
          value={query}
        />

        {quickQueries.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Try:</span>
            {quickQueries.map((item) => (
              <button
                className="rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
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
          </div>
        ) : null}
      </section>

      {!loading && !publishedSops.length ? (
        <EmptyPanel
          compact
          icon={BookOpen}
          text="Published SOPs from the governed index will appear here after review and publish."
          title="No published SOPs yet"
        />
      ) : null}

      {popularSops.length ? (
        <section className="space-y-3">
          <SectionHeader
            actionLabel="Open lookup"
            icon={BookOpen}
            onAction={() => onSearch(query || quickQueries[0] || "")}
            title="Pinned and popular"
          />
          <div className="grid gap-3 md:grid-cols-2">
            {popularSops.map((sop) => (
              <SOPPortalCard key={sop.id} onOpen={() => onOpenSOP(sop)} sop={sop} />
            ))}
            {loading && popularSops.length === 0 ? <LoadingBlock label="Loading published SOPs…" /> : null}
          </div>
        </section>
      ) : null}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.6fr)]">
        <section className="space-y-3">
          <SectionHeader icon={Clock} title="Recent activity" />
          <SOPActivityList
            emptyLabel="No recent SOP activity."
            onOpenSOP={onOpenSOP}
            sops={recentSops}
          />
        </section>

        <aside className="space-y-3">
          <SectionHeader icon={Folder} title="Browse category" />
          <p className="text-xs leading-5 text-muted-foreground">
            Categories are topic facets for quick browsing and search. Collections live in Library for workflow packages, ownership, tools, and governance.
          </p>
          <div className="overflow-hidden rounded-lg border bg-card">
            {categoryGroups.map((group, index) => (
              <button
                className={cn(
                  "flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                  index > 0 && "border-t",
                )}
                key={group.key}
                onClick={() => onOpenCategory(group.key)}
                type="button"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{group.label}</span>
                  <span className="block text-xs text-muted-foreground">
                    {group.count} SOP{group.count === 1 ? "" : "s"}
                  </span>
                </span>
                <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
              </button>
            ))}
            {!loading && !categoryGroups.length ? (
              <div className="px-3 py-6 text-sm text-muted-foreground">Categories appear after SOPs are published.</div>
            ) : null}
          </div>
        </aside>
      </div>

      <section className="flex flex-col gap-3 rounded-lg border bg-muted/20 px-4 py-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Need scoped reasoning?</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Start chat from the current search phrase, grounded to published SOPs only.
          </p>
        </div>
        <Button onClick={() => onOpenChat(query || quickQueries[0] || "")} type="button" variant="outline">
          <MessageSquareText data-icon="inline-start" className="size-4" />
          Open SOP Chat
        </Button>
      </section>
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
    <div className="flex items-end justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <Icon className="size-3.5 shrink-0 text-muted-foreground" />
        <h3 className="truncate text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      </div>
      {actionLabel && onAction ? (
        <Button className="h-7 px-2 text-xs" onClick={onAction} size="sm" type="button" variant="ghost">
          {actionLabel}
          <ArrowRight data-icon="inline-end" className="size-3.5" />
        </Button>
      ) : null}
    </div>
  );
}

function SOPPortalCard({ onOpen, sop }: { onOpen: () => void; sop: SOP }) {
  return (
    <button
      className="group/card w-full rounded-lg border bg-card p-4 text-left transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
      onClick={onOpen}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <MetaLine items={[sop.code, `v${sop.current_version.version_number}`, sop.category]} maxItems={3} />
          <h3 className="mt-1.5 line-clamp-2 text-sm font-semibold leading-snug">{sop.title}</h3>
        </div>
        <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover/card:translate-x-0.5" />
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{sop.summary}</p>
      <TagSummary className="mt-2.5" items={[...sop.case_reasons, ...sop.tags]} maxItems={3} />
      <MetaLine
        className="mt-3"
        items={[formatDate(sop.updated_at), `${sop.analytics?.views ?? 0} view${(sop.analytics?.views ?? 0) === 1 ? "" : "s"}`]}
        maxItems={2}
      />
    </button>
  );
}

function SOPActivityList({
  emptyLabel,
  onOpenSOP,
  sops,
}: {
  emptyLabel: string;
  onOpenSOP: (sop: SOP) => void;
  sops: SOP[];
}) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      {sops.map((sop, index) => (
        <button
          className={cn(
            "group/row grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-3 py-2.5 text-left transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
            index > 0 && "border-t",
          )}
          key={sop.id}
          onClick={() => onOpenSOP(sop)}
          type="button"
        >
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{sop.title}</span>
            <MetaLine
              className="mt-0.5"
              items={[sop.category, formatDate(sop.updated_at), `${sop.analytics?.views ?? 0} views`]}
              maxItems={3}
            />
          </span>
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">v{sop.current_version.version_number}</Badge>
            <ArrowRight className="size-4 text-muted-foreground/60 transition-transform group-hover/row:translate-x-0.5" />
          </span>
        </button>
      ))}
      {sops.length === 0 ? (
        <div className="flex items-center gap-2 px-3 py-6 text-sm text-muted-foreground">
          <Eye className="size-4" />
          {emptyLabel}
        </div>
      ) : null}
    </div>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return <div className="rounded-lg border border-dashed px-3 py-6 text-sm text-muted-foreground">{label}</div>;
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
