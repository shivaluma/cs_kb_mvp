import { useEffect, useState } from "react";

import { useCollection, useCollections, useRecordKBEvent } from "@/hooks/api/kb-index";
import { useFeedback } from "@/providers/feedback-context";
import { CollectionsWorkspace } from "@/workspaces/collections-workspace";

export function CollectionsPage() {
  const collectionsQuery = useCollections();
  const [selectedCollection, setSelectedCollection] = useState("");
  const collectionQuery = useCollection(selectedCollection);
  const eventMutation = useRecordKBEvent();
  const { reportError, reportNotice } = useFeedback();

  useEffect(() => {
    const firstCollection = collectionsQuery.data?.[0];
    if (!selectedCollection && firstCollection) {
      setSelectedCollection(firstCollection.id);
    }
  }, [collectionsQuery.data, selectedCollection]);

  function selectCollection(collectionId: string) {
    setSelectedCollection(collectionId);
    eventMutation.mutate({
      action: "collection_view",
      entity_type: "kb_collection",
      entity_id: collectionId,
    });
  }

  async function copyActionTemplate(templateId: string, name: string, copyTemplate: string) {
    try {
      await navigator.clipboard.writeText(copyTemplate || name);
      eventMutation.mutate({
        action: "action_template_copy",
        entity_type: "action_template",
        entity_id: templateId,
        metadata: { target_title: name, collection_id: selectedCollection },
      });
      reportNotice(`Copied action template: ${name}.`);
    } catch {
      reportError("Clipboard permission blocked.");
    }
  }

  return (
    <CollectionsWorkspace
      collections={collectionsQuery.data ?? []}
      detail={collectionQuery.data ?? null}
      loading={collectionsQuery.isLoading}
      onCopyActionTemplate={copyActionTemplate}
      onSelectCollection={selectCollection}
      selectedCollection={selectedCollection}
    />
  );
}
