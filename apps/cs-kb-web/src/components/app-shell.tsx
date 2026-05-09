import { Bell, CircleHelp, ShieldCheck } from "lucide-react";
import type React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { navItems, type Workspace } from "@/constants";
import { StatusMessage } from "@/components/common";

export function AppShell({
  children,
  documentCount,
  error,
  latency,
  notice,
  onDismissError,
  onDismissNotice,
  onWorkspaceChange,
  synonymCount,
  workspace,
}: {
  children: React.ReactNode;
  documentCount: number;
  error: string;
  latency: string;
  notice: string;
  onDismissError: () => void;
  onDismissNotice: () => void;
  onWorkspaceChange: (workspace: Workspace) => void;
  synonymCount: number;
  workspace: Workspace;
}) {
  const current = navItems.find((item) => item.id === workspace) ?? navItems[0];

  return (
    <main className="min-h-svh bg-background text-foreground">
      <a
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        href="#main-content"
      >
        Skip to main content
      </a>

      <div className="grid min-h-svh lg:grid-cols-[15.5rem_minmax(0,1fr)]">
        <aside className="border-b bg-sidebar px-3 py-3 lg:border-b-0 lg:border-r lg:px-4">
          <div className="flex items-center gap-2.5 px-1">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck className="size-5" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">CS SOP KB</p>
              <p className="truncate text-xs text-muted-foreground">Policy operations</p>
            </div>
          </div>

          <nav aria-label="Main navigation" className="mt-5 grid grid-cols-2 gap-1.5 lg:grid-cols-1">
            {navItems.map((item) => (
              <Button
                className="h-auto justify-start px-2 py-2"
                key={item.id}
                onClick={() => onWorkspaceChange(item.id)}
                type="button"
                variant={workspace === item.id ? "secondary" : "ghost"}
              >
                <item.icon data-icon="inline-start" className="size-4" />
                <span className="truncate">{item.label}</span>
              </Button>
            ))}
          </nav>

          <section className="mt-5 hidden rounded-lg border bg-background p-3 text-xs leading-5 text-muted-foreground lg:block">
            <div className="font-medium text-foreground">Production rule</div>
            Only published, approved versions should enter lookup and AI answer flows.
          </section>
        </aside>

        <section className="min-w-0" id="main-content">
          <header className="border-b bg-background px-4 py-3 md:px-6">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <div className="text-xs text-muted-foreground">CS Knowledge Base</div>
                <h1 className="mt-0.5 text-xl font-semibold tracking-tight">{current.label}</h1>
                <p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">{current.description}</p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">{documentCount} docs</Badge>
                <Badge variant="outline">{synonymCount} synonym groups</Badge>
                <Badge variant="outline">retrieval {latency}</Badge>
                <Button aria-label="Help" size="icon" type="button" variant="ghost">
                  <CircleHelp className="size-4" />
                </Button>
                <Button aria-label="Notifications" size="icon" type="button" variant="ghost">
                  <Bell className="size-4" />
                </Button>
              </div>
            </div>
            {notice || error ? (
              <div className="mt-3 grid gap-2">
                {notice ? (
                  <StatusMessage tone="success" message={notice} onDismiss={onDismissNotice} />
                ) : null}
                {error ? (
                  <StatusMessage tone="error" message={error} onDismiss={onDismissError} />
                ) : null}
              </div>
            ) : null}
          </header>

          <div className="p-4 md:p-5">{children}</div>
        </section>
      </div>
    </main>
  );
}
