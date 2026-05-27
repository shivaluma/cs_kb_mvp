export type NavItemLike<TId extends string = string> = {
  id: TId;
};

export type NavGroupSpec<TId extends string = string> = {
  label: string;
  itemIds: readonly TId[];
};

export const documentWorkflowStepIds = ["documentUpload", "documentQueue", "documents"] as const;

export const sidebarGroupSpecs = [
  {
    label: "Daily workspace",
    itemIds: ["dashboard", "lookup", "chat", "caseAssist"],
  },
  {
    label: "Knowledge",
    itemIds: ["documents", "documentUpload", "collections", "tools"],
  },
  {
    label: "Review",
    itemIds: ["feedback", "relations"],
  },
] as const satisfies readonly NavGroupSpec[];

export const commandGroupSpecs = [
  {
    label: "Daily workspace",
    itemIds: ["dashboard", "lookup", "chat", "caseAssist"],
  },
  {
    label: "Knowledge",
    itemIds: ["documents", "documentUpload", "documentQueue", "collections", "tools"],
  },
  {
    label: "Review",
    itemIds: ["feedback", "relations"],
  },
  {
    label: "System",
    itemIds: ["operations", "synonyms", "retrieval"],
  },
] as const satisfies readonly NavGroupSpec[];

export function buildNavGroups<TItem extends NavItemLike>(
  items: readonly TItem[],
  specs: readonly NavGroupSpec[],
) {
  const byId = new Map(items.map((item) => [item.id, item]));

  return specs
    .map((spec) => ({
      label: spec.label,
      items: spec.itemIds
        .map((id) => byId.get(id))
        .filter((item): item is TItem => Boolean(item)),
    }))
    .filter((group) => group.items.length > 0);
}
