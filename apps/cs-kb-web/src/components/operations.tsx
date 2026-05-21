import type { ElementType, ReactNode } from "react";
import {
  IconAlertTriangle as AlertTriangle,
  IconCircleCheck as CheckCircle2
} from "@tabler/icons-react";

import { Metric } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type StatItem = {
  hint?: string;
  key: string;
  label: string;
  statusLabel?: string;
  tone?: "default" | "warning" | "danger";
  value: number | string;
};

export function StatStrip({
  className,
  items,
  size = "md",
}: {
  className?: string;
  items: StatItem[];
  size?: "sm" | "md" | "lg";
}) {
  if (!items.length) {
    return null;
  }
  return (
    <dl
      className={cn(
        "flex flex-wrap items-baseline gap-x-8 gap-y-3 border-b pb-3",
        className,
      )}
    >
      {items.map((item) => (
        <Metric
          hint={item.hint}
          key={item.key}
          label={item.label}
          size={size}
          tone={item.tone}
          value={item.value}
        />
      ))}
    </dl>
  );
}

export function Stat(props: Omit<StatItem, "key">) {
  return <Metric hint={props.hint} label={props.label} tone={props.tone} value={props.value} />;
}

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
    <div className="min-w-0">
      <div className="flex items-center justify-between gap-3">
        <Icon className={cn("size-4", tone === "warning" ? "text-destructive" : "text-muted-foreground")} />
        {trend ? <Badge variant="outline">{trend}</Badge> : null}
      </div>
      <div className="mt-3 text-2xl font-semibold tabular-nums leading-tight">{value}</div>
      <div className="mt-1 text-xs font-medium text-muted-foreground">{label}</div>
      {note ? <div className="mt-1.5 text-[11px] leading-snug text-muted-foreground">{note}</div> : null}
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
    <div className="flex items-start gap-3 rounded-lg border bg-muted/15 p-3">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium leading-snug">{title}</div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p>
        <Button className="mt-2.5" onClick={onClick} size="sm" type="button" variant="outline">
          {action}
        </Button>
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
