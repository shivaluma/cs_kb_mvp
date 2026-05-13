import { useState } from "react";

import { useCollection, useCollections, useRecordKBEvent } from "@/hooks/api/kb-index";
import { CollectionsWorkspace } from "@/workspaces/collections-workspace";

export function CollectionsPage() {
  const collectionsQuery = useCollections();
  const [selectedCollection, setSelectedCollection] = useState("");
  const collectionQuery = useCollection(selectedCollection);
  const eventMutation = useRecordKBEvent();

  function selectCollection(collectionId: string) {
    setSelectedCollection(collectionId);
    eventMutation.mutate({
      action: "collection_view",
      entity_type: "kb_collection",
      entity_id: collectionId,
    });
  }

  return (
    <CollectionsWorkspace
      collections={collectionsQuery.data ?? []}
      detail={collectionQuery.data ?? null}
      loading={collectionsQuery.isLoading}
      onSelectCollection={selectCollection}
      selectedCollection={selectedCollection}
    />
  );
}
