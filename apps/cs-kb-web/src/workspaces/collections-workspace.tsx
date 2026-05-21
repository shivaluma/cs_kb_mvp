import {
  IconBoxMultiple as Boxes,
  IconCopy as Copy,
  IconGitBranch as GitBranch,
  IconShieldExclamation as ShieldAlert
} from "@tabler/icons-react";

import { Metric, SectionTitle } from "@/components/common";
import { DataTable, type DataTableColumn } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  const columns: DataTableColumn<KBCollectionSummary>[] = [
    {
      key: "name",
      header: "Collection",
      width: "minmax(14rem, 1.4fr)",
      render: (collection) => (
        <span className="flex min-w-0 items-center gap-2">
          <Boxes className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0">
            <span className="block truncate font-medium">{collection.name}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {collection.owner_team || "Unassigned owner"}
            </span>
          </span>
        </span>
      ),
    },
    {
      key: "type",
      header: "Type",
      width: "9rem",
      render: (collection) => (
        <Badge className="w-fit" variant="outline">
          {collection.collection_type}
        </Badge>
      ),
    },
    {
      key: "items",
      header: "Items",
      width: "5rem",
      align: "right",
      render: (collection) => <span className="tabular-nums">{collection.item_count}</span>,
    },
    {
      key: "risk",
      header: "Risk",
      width: "5rem",
      align: "right",
      render: (collection) => <span className="tabular-nums">{collection.high_risk_count}</span>,
    },
    {
      key: "gaps",
      header: "Gaps",
      width: "5rem",
      align: "right",
      render: (collection) => <span className="tabular-nums">{collection.unresolved_relation_count}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {collections.length} collection{collections.length === 1 ? "" : "s"} organize approved routing, tools, and action templates. Select a row to inspect operational pressure.
      </p>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(20rem,0.75fr)]">
        <DataTable
          columns={columns}
          empty="No collections are available yet."
          getRowKey={(row) => row.id}
          loading={loading}
          loadingLabel="Loading collections…"
          minWidth="50rem"
          onRowClick={(collection) => onSelectCollection(collection.id)}
          rows={collections}
          selectedRowKey={selectedCollection}
        />

        <aside className="rounded-lg border bg-card">
          <header className="border-b px-4 py-3">
            <h2 className="text-sm font-semibold">{detail?.name ?? "Collection detail"}</h2>
          </header>
          <div className="space-y-4 p-4 text-sm">
            {!detail ? (
              <p className="text-muted-foreground">
                Select a collection to inspect approved issue router units, tools, actions, and unresolved relation pressure.
              </p>
            ) : (
              <>
                <dl className="grid grid-cols-3 gap-3 border-b pb-3">
                  <Metric label="Items" size="sm" value={detail.item_count} />
                  <Metric label="Tools" size="sm" value={detail.tools.length} />
                  <Metric label="Actions" size="sm" value={detail.action_templates.length} />
                </dl>

                <section className="space-y-2">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="size-3.5 text-muted-foreground" />
                    <SectionTitle title="Issue router" />
                  </div>
                  {detail.issue_router_units.slice(0, 6).length ? (
                    <ul className="space-y-1.5">
                      {detail.issue_router_units.slice(0, 6).map((item) => (
                        <li className="rounded-md border bg-card px-3 py-2" key={item.chunk_id}>
                          <div className="truncate text-sm font-medium">{item.title}</div>
                          <div className="truncate text-xs text-muted-foreground">
                            {item.target_sop_title || "Unresolved target"}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">No router units.</p>
                  )}
                </section>

                {detail.action_templates.length ? (
                  <section className="space-y-2">
                    <SectionTitle title="Action templates" />
                    <ul className="space-y-1.5">
                      {detail.action_templates.slice(0, 4).map((item) => (
                        <li className="flex items-start justify-between gap-3 rounded-md border bg-card px-3 py-2" key={item.id}>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium">{item.name}</div>
                            <p className="line-clamp-2 text-xs text-muted-foreground">
                              {item.description || item.action_type}
                            </p>
                          </div>
                          <Button
                            disabled={!item.copy_template && !item.name}
                            onClick={() => onCopyActionTemplate(item.id, item.name, item.copy_template)}
                            size="xs"
                            type="button"
                            variant="ghost"
                          >
                            <Copy className="size-3" />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}

                <section className="space-y-1">
                  <div className="flex items-center gap-2">
                    <GitBranch className="size-3.5 text-muted-foreground" />
                    <SectionTitle title="Relations" />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {detail.unresolved_relation_count} unresolved or suggested relations need review.
                  </p>
                </section>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
