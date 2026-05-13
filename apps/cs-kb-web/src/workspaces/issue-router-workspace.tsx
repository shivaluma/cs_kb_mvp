import {
  IconFileText as FileText,
  IconSearch as Search,
  IconTool as Wrench
} from "@tabler/icons-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { FilterOption, IssueRouterItem, KBCollectionSummary, ToolLinkSummary } from "@/types";

export function IssueRouterWorkspace({
  audience,
  audienceOptions,
  collection,
  collections,
  loading,
  query,
  riskLevel,
  results,
  setAudience,
  setCollection,
  setQuery,
  setRiskLevel,
  setTaskType,
  setVertical,
  taskType,
  taskTypeOptions,
  tools,
  vertical,
  verticalOptions,
}: {
  audience: string;
  audienceOptions: FilterOption[];
  collection: string;
  collections: KBCollectionSummary[];
  loading: boolean;
  query: string;
  riskLevel: string;
  results: IssueRouterItem[];
  setAudience: (value: string) => void;
  setCollection: (value: string) => void;
  setQuery: (value: string) => void;
  setRiskLevel: (value: string) => void;
  setTaskType: (value: string) => void;
  setVertical: (value: string) => void;
  taskType: string;
  taskTypeOptions: FilterOption[];
  tools: ToolLinkSummary[];
  vertical: string;
  verticalOptions: FilterOption[];
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 xl:grid-cols-[1fr_220px_180px_180px_180px_160px]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            className="pl-9"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search issue, SOP, queue, macro, or task..."
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
        <Select onValueChange={(value) => setAudience(value === "all" ? "" : value)} value={audience || "all"}>
          <SelectTrigger>
            <SelectValue placeholder="Audience" />
          </SelectTrigger>
          <SelectContent>
            {audienceOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select onValueChange={(value) => setVertical(value === "all" ? "" : value)} value={vertical || "all"}>
          <SelectTrigger>
            <SelectValue placeholder="Vertical" />
          </SelectTrigger>
          <SelectContent>
            {verticalOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select onValueChange={(value) => setTaskType(value === "all" ? "" : value)} value={taskType || "all"}>
          <SelectTrigger>
            <SelectValue placeholder="Task" />
          </SelectTrigger>
          <SelectContent>
            {taskTypeOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select onValueChange={(value) => setRiskLevel(value === "all" ? "" : value)} value={riskLevel || "all"}>
          <SelectTrigger>
            <SelectValue placeholder="Risk" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All risk</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        {loading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading issue router...</CardContent></Card> : null}
        {!loading && results.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              No approved issue router units match the current filters.
            </CardContent>
          </Card>
        ) : null}
        {results.map((item) => {
          const relatedTools = tools.filter((tool) => item.tool_ids.includes(tool.id));
          return (
            <Card key={item.chunk_id} className="overflow-hidden">
              <CardHeader className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{item.relation_status || "approved unit"}</Badge>
                  {item.risk_level ? <Badge variant="outline">{item.risk_level} risk</Badge> : null}
                  {item.collection ? <Badge variant="outline">{item.collection}</Badge> : null}
                </div>
                <CardTitle className="text-base">{item.title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="line-clamp-4 whitespace-pre-line text-muted-foreground">{item.content}</p>
                <div className="flex flex-wrap gap-2">
                  {item.audience.map((value) => <Badge key={value} variant="secondary">{value}</Badge>)}
                  {item.vertical.map((value) => <Badge key={value} variant="secondary">{value}</Badge>)}
                  {item.case_type.map((value) => <Badge key={value} variant="outline">{value}</Badge>)}
                  {item.task_type.map((value) => <Badge key={value} variant="outline">{value}</Badge>)}
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-md border p-3">
                    <div className="mb-1 flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
                      <FileText className="size-3.5" /> Target SOP
                    </div>
                    <div>{item.target_sop_title || "Unresolved target"}</div>
                  </div>
                  <div className="rounded-md border p-3">
                    <div className="mb-1 flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
                      <Wrench className="size-3.5" /> Linked tools
                    </div>
                    <div className="space-y-1">
                      {relatedTools.length ? relatedTools.slice(0, 3).map((tool) => (
                        <div className="truncate" key={tool.id}>{tool.name}</div>
                      )) : <span className="text-muted-foreground">No tool linked to this router unit.</span>}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
