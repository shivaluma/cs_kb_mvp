import { BookOpen, GraduationCap, Wrench } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ActionTemplateSummary, KBCollectionSummary, ToolLinkSummary } from "@/types";

export function OnboardingWorkspace({
  actionTemplates,
  collections,
  loading,
  tools,
}: {
  actionTemplates: ActionTemplateSummary[];
  collections: KBCollectionSummary[];
  loading: boolean;
  tools: ToolLinkSummary[];
}) {
  const coreCollections = collections.filter((item) =>
    ["CS Core Operating Rules", "Account & Verification", "Trip / Order Issues"].includes(item.name),
  );

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <Badge variant="outline">new CS browse</Badge>
        <h1 className="text-3xl font-semibold tracking-tight">CS Onboarding</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          A compact starting point generated from approved collections, tools, and copy-ready action templates.
        </p>
      </header>

      {loading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading onboarding content...</CardContent></Card> : null}
      <div className="grid gap-4 xl:grid-cols-3">
        <OnboardingSection icon={<GraduationCap className="size-4" />} title="Start here">
          {coreCollections.map((collection) => (
            <Item key={collection.id} title={collection.name} detail={`${collection.item_count} reviewed items`} />
          ))}
        </OnboardingSection>
        <OnboardingSection icon={<BookOpen className="size-4" />} title="Common tasks">
          {actionTemplates.slice(0, 8).map((action) => (
            <Item key={action.id} title={action.name} detail={action.action_type} />
          ))}
        </OnboardingSection>
        <OnboardingSection icon={<Wrench className="size-4" />} title="Tool directory">
          {tools.slice(0, 8).map((tool) => (
            <Item key={tool.id} title={tool.name} detail={tool.tool_type} />
          ))}
        </OnboardingSection>
      </div>
    </div>
  );
}

function OnboardingSection({ children, icon, title }: { children: ReactNode; icon: ReactNode; title: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">{children}</CardContent>
    </Card>
  );
}

function Item({ detail, title }: { detail: string; title: string }) {
  return (
    <div className="rounded-md border p-3">
      <div className="font-medium">{title}</div>
      <div className="text-muted-foreground">{detail}</div>
    </div>
  );
}
