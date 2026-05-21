import {
  IconExternalLink as ExternalLink,
  IconLink as Link2,
  IconTool as Wrench
} from "@tabler/icons-react";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { SearchBar } from "@/components/search-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  const columns: DataTableColumn<ToolLinkSummary>[] = [
    {
      key: "tool",
      header: "Tool",
      width: "minmax(14rem, 1.4fr)",
      render: (tool) => (
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-2">
            <Wrench className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate font-medium">{tool.name}</span>
          </span>
          <span className="ms-6 block truncate text-xs text-muted-foreground">
            {tool.description || "No description yet."}
          </span>
        </span>
      ),
    },
    {
      key: "type",
      header: "Type",
      width: "8rem",
      render: (tool) => (
        <Badge className="w-fit" variant="outline">
          {tool.tool_type}
        </Badge>
      ),
    },
    {
      key: "owner",
      header: "Owner",
      width: "minmax(10rem, 0.8fr)",
      render: (tool) => (
        <span className="truncate text-muted-foreground">{tool.owner_team || "Unassigned"}</span>
      ),
    },
    {
      key: "sources",
      header: "Sources",
      width: "7rem",
      align: "right",
      render: (tool) => (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Link2 className="size-3.5" />
          {tool.used_by.length}
        </span>
      ),
    },
    {
      key: "action",
      header: "Action",
      width: "7rem",
      align: "right",
      render: (tool) =>
        tool.url ? (
          <Button asChild onClick={() => onOpenTool(tool)} size="xs" type="button" variant="outline">
            <a href={tool.url} rel="noreferrer" target="_blank">
              <ExternalLink data-icon="inline-start" className="size-3" />
              Open
            </a>
          </Button>
        ) : (
          <Button disabled size="xs" type="button" variant="outline">
            No URL
          </Button>
        ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
        <SearchBar
          onChange={setQuery}
          placeholder="Search tool, form, dashboard, owner, or system…"
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

      <p className="text-sm text-muted-foreground">
        {tools.length} approved tool{tools.length === 1 ? "" : "s"} match this view. Open links are tracked for source-unit usage.
      </p>

      <DataTable
        columns={columns}
        empty="No approved tools match this view."
        getRowKey={(row) => row.id}
        loading={loading}
        loadingLabel="Loading tools…"
        minWidth="48rem"
        rows={tools}
      />
    </div>
  );
}
