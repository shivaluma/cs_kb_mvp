import {
  IconExternalLink as ExternalLink,
  IconLink as Link2,
  IconSearch as Search,
  IconTool as Wrench
} from "@tabler/icons-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            className="pl-9"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search tool, form, dashboard, owner, or system..."
            value={query}
          />
        </div>
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

      {loading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading tools...</CardContent></Card> : null}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {tools.map((tool) => (
          <Card key={tool.id}>
            <CardHeader className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <Badge variant="secondary">{tool.tool_type}</Badge>
                <Wrench className="size-4 text-muted-foreground" />
              </div>
              <CardTitle className="text-base">{tool.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <p className="line-clamp-3 text-muted-foreground">{tool.description || "No description yet."}</p>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Link2 className="size-3.5" />
                <span>{tool.used_by.length} linked source units</span>
              </div>
              {tool.url ? (
                <Button asChild size="sm" onClick={() => onOpenTool(tool)}>
                  <a href={tool.url} rel="noreferrer" target="_blank">
                    <ExternalLink className="mr-2 size-4" />
                    Open tool
                  </a>
                </Button>
              ) : (
                <Button disabled size="sm" variant="outline">
                  Missing URL
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      {!loading && tools.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">No approved tools match this view.</CardContent>
        </Card>
      ) : null}
    </div>
  );
}
