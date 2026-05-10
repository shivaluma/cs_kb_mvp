import type { ElementType, ReactNode } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function KpiCard({
  icon: Icon,
  label,
  note,
  tone = "default",
  trend,
  value,
}: {
  icon: ElementType;
  label: string;
  note?: string;
  tone?: "default" | "warning";
  trend?: string;
  value: number | string;
}) {
  return (
    <div className="rounded-xl border bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <Icon className={tone === "warning" ? "size-4 text-destructive" : "size-4 text-muted-foreground"} />
        {trend ? <Badge variant="outline">{trend}</Badge> : null}
      </div>
      <div className="mt-3 text-2xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs font-medium text-muted-foreground">{label}</div>
      {note ? <div className="mt-2 text-[11px] text-muted-foreground">{note}</div> : null}
    </div>
  );
}

export function ActionItem({
  action,
  icon: Icon,
  onClick,
  text,
  title,
}: {
  action: string;
  icon: ElementType;
  onClick: () => void;
  text: string;
  title: string;
}) {
  return (
    <div className="rounded-xl border bg-muted/20 p-3">
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 size-4 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">{title}</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p>
          <Button className="mt-3" onClick={onClick} size="sm" type="button" variant="outline">
            {action}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ActionTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[42rem] text-left text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            {columns.map((column) => (
              <th className="px-3 py-3 font-medium" key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((row, rowIndex) => (
            <tr className="hover:bg-muted/30" key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td className="px-3 py-3" key={`${rowIndex}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function MiniTrend({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex h-48 items-end gap-2 rounded-xl border bg-muted/20 p-4">
      {values.map((value, index) => (
        <div className="flex min-w-0 flex-1 flex-col items-center gap-2" key={`${value}-${index}`}>
          <div
            className="w-full rounded-t-lg bg-primary/80"
            style={{ height: `${Math.max((value / max) * 100, 8)}%` }}
          />
          <span className="text-[10px] text-muted-foreground">D{index + 1}</span>
        </div>
      ))}
    </div>
  );
}

export function HealthPill({ score }: { score: number }) {
  const label = score >= 80 ? "Healthy" : score >= 60 ? "Needs review" : "Problem";
  return <Badge variant={score >= 80 ? "secondary" : "outline"}>{score}% {label}</Badge>;
}

export function ReadinessCheck({
  detail,
  label,
  passed,
}: {
  detail: string;
  label: string;
  passed: boolean;
}) {
  const Icon = passed ? CheckCircle2 : AlertTriangle;
  return (
    <div className={cn("rounded-lg border p-3", passed ? "bg-muted/15" : "border-destructive/30 bg-destructive/5")}>
      <div className="flex items-center gap-2 text-sm font-medium">
        <Icon className={cn("size-4", passed ? "text-muted-foreground" : "text-destructive")} />
        {label}
      </div>
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{detail}</p>
    </div>
  );
}

export function DocumentFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-sm font-medium">{value}</div>
    </div>
  );
}
