import { ExternalLink, Link2, Wrench } from "lucide-react";

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
  setCollection,
  tools,
}: {
  collection: string;
  collections: KBCollectionSummary[];
  loading: boolean;
  onOpenTool: (tool: ToolLinkSummary) => void;
  setCollection: (value: string) => void;
  tools: ToolLinkSummary[];
}) {
  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <Badge variant="outline">approved links</Badge>
          <h1 className="text-3xl font-semibold tracking-tight">Tool Directory</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Working links imported from reviewed CS index workbooks. Tool links are not SOPs; they are supporting assets used by SOP units and action templates.
          </p>
        </div>
        <Select onValueChange={(value) => setCollection(value === "all" ? "" : value)} value={collection || "all"}>
          <SelectTrigger className="w-full lg:w-[260px]">
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
      </header>

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
              <Button asChild size="sm" onClick={() => onOpenTool(tool)}>
                <a href={tool.url} rel="noreferrer" target="_blank">
                  <ExternalLink className="mr-2 size-4" />
                  Open tool
                </a>
              </Button>
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
