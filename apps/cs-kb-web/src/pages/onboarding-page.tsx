import { useActionTemplates, useCollections, useTools } from "@/hooks/api/kb-index";
import { OnboardingWorkspace } from "@/workspaces/onboarding-workspace";

export function OnboardingPage() {
  const collectionsQuery = useCollections();
  const toolsQuery = useTools();
  const actionsQuery = useActionTemplates();

  return (
    <OnboardingWorkspace
      actionTemplates={actionsQuery.data ?? []}
      collections={collectionsQuery.data ?? []}
      loading={collectionsQuery.isLoading || toolsQuery.isLoading || actionsQuery.isLoading}
      tools={toolsQuery.data ?? []}
    />
  );
}
