import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type DataTableColumn<Row> = {
  align?: "left" | "right" | "center";
  className?: string;
  header: ReactNode;
  key: string;
  render: (row: Row, index: number) => ReactNode;
  width?: string;
};

export function DataTable<Row>({
  columns,
  empty,
  getRowKey,
  loading,
  loadingLabel = "Loading…",
  minWidth = "48rem",
  onRowClick,
  rows,
  selectedRowKey,
}: {
  columns: DataTableColumn<Row>[];
  empty?: ReactNode;
  getRowKey: (row: Row, index: number) => string;
  loading?: boolean;
  loadingLabel?: string;
  minWidth?: string;
  onRowClick?: (row: Row, index: number) => void;
  rows: Row[];
  selectedRowKey?: string;
}) {
  const template = columns.map((column) => column.width ?? "minmax(0, 1fr)").join(" ");
  return (
    <div className="overflow-x-auto rounded-lg border bg-card">
      <div
        className="grid gap-3 border-b bg-muted/30 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
        style={{ minWidth, gridTemplateColumns: template }}
      >
        {columns.map((column) => (
          <span key={column.key} className={cn(alignClass(column.align), column.className)}>
            {column.header}
          </span>
        ))}
      </div>
      <div className="divide-y" style={{ minWidth }}>
        {loading && rows.length === 0 ? (
          <div className="px-3 py-6 text-sm text-muted-foreground">{loadingLabel}</div>
        ) : rows.length === 0 ? (
          <div className="px-3 py-6 text-sm text-muted-foreground">
            {empty ?? "No matching rows."}
          </div>
        ) : (
          rows.map((row, index) => {
            const key = getRowKey(row, index);
            const isSelected = selectedRowKey === key;
            const baseClasses =
              "grid items-center gap-3 px-3 py-2.5 text-sm transition-colors";
            if (onRowClick) {
              return (
                <button
                  aria-pressed={isSelected}
                  className={cn(
                    baseClasses,
                    "w-full text-left hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                    isSelected && "bg-muted/40",
                  )}
                  key={key}
                  onClick={() => onRowClick(row, index)}
                  style={{ gridTemplateColumns: template }}
                  type="button"
                >
                  {columns.map((column) => (
                    <span
                      className={cn("min-w-0", alignClass(column.align), column.className)}
                      key={column.key}
                    >
                      {column.render(row, index)}
                    </span>
                  ))}
                </button>
              );
            }
            return (
              <div
                className={cn(baseClasses, isSelected && "bg-muted/40")}
                key={key}
                style={{ gridTemplateColumns: template }}
              >
                {columns.map((column) => (
                  <span
                    className={cn("min-w-0", alignClass(column.align), column.className)}
                    key={column.key}
                  >
                    {column.render(row, index)}
                  </span>
                ))}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function alignClass(align?: "left" | "right" | "center") {
  if (align === "right") return "justify-self-end text-right";
  if (align === "center") return "justify-self-center text-center";
  return "";
}
