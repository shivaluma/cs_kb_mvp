import {
  IconExternalLink as ExternalLink,
  IconLink as Link2,
  IconTool as Wrench
} from "@tabler/icons-react";

import { SearchBar } from "@/components/search-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { KBCollectionSummary, ToolLinkSummary } from "@/types";

export function ToolsWorkspace({
  collection,
  collections,
  loading,
  onOpenTool,
  query,
  setCollection,
  setQuery,
  tools,
}: {
  collection: string;
  collections: KBCollectionSummary[];
  loading: boolean;
  onOpenTool: (tool: ToolLinkSummary) => void;
  query: string;
  setCollection: (value: string) => void;
  setQuery: (value: string) => void;
  tools: ToolLinkSummary[];
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 lg:grid-cols-[1fr_260px]">
        <SearchBar
          className="lg:block"
          onChange={setQuery}
          placeholder="Search tool, form, dashboard, owner, or system..."
          value={query}
        />
        <Select onValueChange={(value) => setCollection(value === "all" ? "" : value)} value={collection || "all"}>
          <SelectTrigger>
            <SelectValue placeholder="Collection" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All collections</SelectItem>
            {collections.map((item) => (
              <SelectItem key={item.slug} value={item.slug}>
                {item.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>{tools.length} approved tool{tools.length === 1 ? "" : "s"} match this view.</span>
        <span>Open links are tracked for source-unit usage.</span>
      </div>

      {loading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading tools...</CardContent></Card> : null}
      <div className="overflow-x-auto rounded-xl border bg-card">
        <div className="grid min-w-[48rem] grid-cols-[minmax(13rem,1.2fr)_8rem_minmax(10rem,0.8fr)_7rem_7rem] gap-3 border-b bg-muted/35 px-3 py-2 text-xs font-medium text-muted-foreground">
          <span>Tool</span>
          <span>Type</span>
          <span>Owner</span>
          <span>Sources</span>
          <span className="text-right">Action</span>
        </div>
        <div className="min-w-[48rem] divide-y">
          {tools.map((tool) => (
            <div className="grid grid-cols-[minmax(13rem,1.2fr)_8rem_minmax(10rem,0.8fr)_7rem_7rem] items-center gap-3 px-3 py-2.5 text-sm" key={tool.id}>
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <Wrench className="size-4 shrink-0 text-muted-foreground" />
                  <span className="truncate font-medium">{tool.name}</span>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{tool.description || "No description yet."}</p>
              </div>
              <Badge className="w-fit" variant="secondary">{tool.tool_type}</Badge>
              <span className="truncate text-muted-foreground">{tool.owner_team || "Unassigned"}</span>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Link2 className="size-3.5" />
                {tool.used_by.length}
              </span>
              <div className="flex justify-end">
                {tool.url ? (
                  <Button asChild className="h-8 px-2" size="sm" onClick={() => onOpenTool(tool)} variant="outline">
                    <a href={tool.url} rel="noreferrer" target="_blank">
                      <ExternalLink data-icon="inline-start" className="size-3.5" />
                      Open
                    </a>
                  </Button>
                ) : (
                  <Button className="h-8 px-2" disabled size="sm" variant="outline">
                    Missing URL
                  </Button>
                )}
              </div>
            </div>
          ))}
          {!loading && tools.length === 0 ? (
            <div className="px-3 py-6 text-sm text-muted-foreground">No approved tools match this view.</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
