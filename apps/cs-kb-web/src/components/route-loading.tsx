import { Loader2 } from "lucide-react";

export function RouteLoading({ label = "Loading workspace" }: { label?: string }) {
  return (
    <div className="grid min-h-[28rem] place-items-center rounded-2xl border border-dashed bg-muted/15">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        {label}
      </div>
    </div>
  );
}
