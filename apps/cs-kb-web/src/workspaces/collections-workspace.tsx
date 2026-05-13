import {
  IconBoxMultiple as Boxes,
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
  onSelectCollection,
  selectedCollection,
}: {
  collections: KBCollectionSummary[];
  detail: KBCollectionDetail | null;
  loading: boolean;
  onSelectCollection: (collectionId: string) => void;
  selectedCollection: string;
}) {
  return (
    <div className="space-y-5">
      {loading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading collections...</CardContent></Card> : null}
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="grid gap-3 md:grid-cols-2">
          {collections.map((collection) => (
            <Card key={collection.id} className={selectedCollection === collection.id ? "border-primary" : ""}>
              <CardHeader className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <Badge variant="secondary">{collection.collection_type}</Badge>
                  <Boxes className="size-4 text-muted-foreground" />
                </div>
                <CardTitle className="text-base">{collection.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="grid grid-cols-3 gap-2">
                  <Metric label="Items" value={collection.item_count} />
                  <Metric label="Risk" value={collection.high_risk_count} />
                  <Metric label="Gaps" value={collection.unresolved_relation_count} />
                </div>
                <Button size="sm" variant="outline" onClick={() => onSelectCollection(collection.id)}>
                  View detail
                </Button>
              </CardContent>
            </Card>
          ))}
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
