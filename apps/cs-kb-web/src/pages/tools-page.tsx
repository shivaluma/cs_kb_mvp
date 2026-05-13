import { useState } from "react";

import { useCollections, useRecordKBEvent, useTools } from "@/hooks/api/kb-index";
import { ToolsWorkspace } from "@/workspaces/tools-workspace";

export function ToolsPage() {
  const [collection, setCollection] = useState("");
  const collectionsQuery = useCollections();
  const toolsQuery = useTools(collection);
  const eventMutation = useRecordKBEvent();

  return (
    <ToolsWorkspace
      collection={collection}
      collections={collectionsQuery.data ?? []}
      loading={toolsQuery.isLoading}
      onOpenTool={(tool) =>
        eventMutation.mutate({
          action: "tool_link_open",
          entity_type: "tool_link",
          entity_id: tool.id,
          metadata: { name: tool.name, url: tool.url },
        })
      }
      setCollection={setCollection}
      tools={toolsQuery.data ?? []}
    />
  );
}
