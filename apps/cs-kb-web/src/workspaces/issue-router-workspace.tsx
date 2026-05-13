import { FileText, Search, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { IssueRouterItem, KBCollectionSummary, ToolLinkSummary } from "@/types";

export function IssueRouterWorkspace({
  audience,
  collection,
  collections,
  loading,
  query,
  results,
  setAudience,
  setCollection,
  setQuery,
  tools,
}: {
  audience: string;
  collection: string;
  collections: KBCollectionSummary[];
  loading: boolean;
  query: string;
  results: IssueRouterItem[];
  setAudience: (value: string) => void;
  setCollection: (value: string) => void;
  setQuery: (value: string) => void;
  tools: ToolLinkSummary[];
}) {
  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <Badge variant="outline">operational index</Badge>
        <h1 className="text-3xl font-semibold tracking-tight">Issue Router</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Search an issue and open the reviewed SOP reference, quick action, or tool from the CS daily operations index.
        </p>
      </header>

      <div className="grid gap-3 lg:grid-cols-[1fr_220px_220px]">
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
            <SelectItem value="all">All audiences</SelectItem>
            <SelectItem value="rider">Rider</SelectItem>
            <SelectItem value="driver">Driver</SelectItem>
            <SelectItem value="merchant">Merchant</SelectItem>
            <SelectItem value="cleaner">Cleaner</SelectItem>
            <SelectItem value="vip_customer">VIP</SelectItem>
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
        {results.map((item) => (
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
                {item.task_type.map((value) => <Badge key={value} variant="secondary">{value}</Badge>)}
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
                    <Wrench className="size-3.5" /> Related tools
                  </div>
                  <div>{tools.length} approved tools available</div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
