import {
  IconBoxMultiple as Boxes,
  IconCopy as Copy,
  IconGitBranch as GitBranch,
  IconShieldExclamation as ShieldAlert
} from "@tabler/icons-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { KBCollectionDetail, KBCollectionSummary } from "@/types";

export function CollectionsWorkspace({
  collections,
  detail,
  loading,
  onCopyActionTemplate,
  onSelectCollection,
  selectedCollection,
}: {
  collections: KBCollectionSummary[];
  detail: KBCollectionDetail | null;
  loading: boolean;
  onCopyActionTemplate: (templateId: string, name: string, copyTemplate: string) => void;
  onSelectCollection: (collectionId: string) => void;
  selectedCollection: string;
}) {
  return (
    <div className="space-y-5">
      {loading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading collections...</CardContent></Card> : null}
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>{collections.length} collection{collections.length === 1 ? "" : "s"} organize approved routing, tools, and action templates.</span>
        <span>Select a row to inspect operational pressure.</span>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="overflow-x-auto rounded-xl border bg-card">
          <div className="grid min-w-[50rem] grid-cols-[minmax(14rem,1fr)_9rem_5rem_5rem_5rem_6rem] gap-3 border-b bg-muted/35 px-3 py-2 text-xs font-medium text-muted-foreground">
            <span>Collection</span>
            <span>Type</span>
            <span>Items</span>
            <span>Risk</span>
            <span>Gaps</span>
            <span className="text-right">Action</span>
          </div>
          <div className="min-w-[50rem] divide-y">
            {collections.map((collection) => {
              const selected = selectedCollection === collection.id;
              return (
                <button
                  className={`grid w-full grid-cols-[minmax(14rem,1fr)_9rem_5rem_5rem_5rem_6rem] items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 ${selected ? "bg-primary/5" : ""}`}
                  key={collection.id}
                  onClick={() => onSelectCollection(collection.id)}
                  type="button"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Boxes className="size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{collection.name}</span>
                      <span className="block truncate text-xs text-muted-foreground">{collection.owner_team || "Unassigned owner"}</span>
                    </span>
                  </span>
                  <Badge className="w-fit" variant="secondary">{collection.collection_type}</Badge>
                  <span className="tabular-nums">{collection.item_count}</span>
                  <span className="tabular-nums">{collection.high_risk_count}</span>
                  <span className="tabular-nums">{collection.unresolved_relation_count}</span>
                  <span className="text-right text-xs text-muted-foreground">{selected ? "Selected" : "View"}</span>
                </button>
              );
            })}
            {!loading && collections.length === 0 ? (
              <div className="px-3 py-6 text-sm text-muted-foreground">No collections are available yet.</div>
            ) : null}
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{detail?.name ?? "Collection detail"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {!detail ? (
              <p className="text-muted-foreground">Select a collection to inspect approved issue router units, tools, actions, and unresolved relation pressure.</p>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-2">
                  <Metric label="Items" value={detail.item_count} />
                  <Metric label="Tools" value={detail.tools.length} />
                  <Metric label="Actions" value={detail.action_templates.length} />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-2 font-medium"><ShieldAlert className="size-4" /> Issue router</div>
                  {detail.issue_router_units.slice(0, 6).map((item) => (
                    <div key={item.chunk_id} className="rounded-md border p-3">
                      <div className="font-medium">{item.title}</div>
                      <div className="text-muted-foreground">{item.target_sop_title || "Unresolved target"}</div>
                    </div>
                  ))}
                </div>
                {detail.action_templates.length ? (
                  <div className="space-y-2">
                    <div className="font-medium">Action templates</div>
                    {detail.action_templates.slice(0, 4).map((item) => (
                      <div className="flex items-start justify-between gap-3 rounded-md border p-3" key={item.id}>
                        <div className="min-w-0">
                          <div className="truncate font-medium">{item.name}</div>
                          <div className="mt-1 line-clamp-2 text-muted-foreground">{item.description || item.action_type}</div>
                        </div>
                        <Button
                          className="h-8 rounded-full px-3"
                          disabled={!item.copy_template && !item.name}
                          onClick={() => onCopyActionTemplate(item.id, item.name, item.copy_template)}
                          size="sm"
                          type="button"
                          variant="outline"
                        >
                          <Copy data-icon="inline-start" className="size-3.5" />
                          Copy
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="space-y-2">
                  <div className="flex items-center gap-2 font-medium"><GitBranch className="size-4" /> Relations</div>
                  <p className="text-muted-foreground">{detail.unresolved_relation_count} unresolved or suggested relations need review.</p>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
