export type ChatWarningLabels = {
  debugWarnings: string[];
  userWarnings: string[];
};

export function chatWarningLabels(warnings: string[], showDebug: boolean): ChatWarningLabels {
  const userWarnings = warnings
    .map((warning) => readableChatWarningLabel(warning))
    .filter(Boolean)
    .filter((warning, index, list) => list.indexOf(warning) === index)
    .slice(0, 6);
  const debugWarnings = showDebug
    ? warnings
        .map((warning) => warning.replace(/_/g, " "))
        .filter((warning, index, list) => list.indexOf(warning) === index)
        .filter((warning) => !userWarnings.includes(warning))
        .slice(0, 6)
    : [];

  return { userWarnings, debugWarnings };
}

function readableChatWarningLabel(warning: string) {
  const normalized = warning.toLowerCase().replace(/_/g, " ");
  if (isDebugWarning(normalized)) {
    return "";
  }
  if (normalized.includes("matched source has unresolved dependency")) {
    return "Source references an unapproved related SOP. Do not use that related document unless the relation is approved.";
  }
  if (normalized.includes("conflict") || normalized.includes("requires review")) {
    return "SOP guidance may conflict. Review with owner/QA.";
  }
  if (normalized.includes("no reliable source") || normalized.includes("insufficient")) {
    return "Not enough published SOP evidence.";
  }
  if (normalized.includes("grounded published sop units only")) {
    return "Answer is limited to published SOP evidence.";
  }
  if (normalized.includes("internal")) {
    return "Internal-only source needs care before customer wording.";
  }
  return warning.replace(/_/g, " ");
}

function isDebugWarning(normalizedWarning: string) {
  return [
    "raw draft",
    "archived content excluded",
    "chat kb index",
    "query understanding",
    "no approved relation expansion",
    "index query understanding",
    "meili",
    "postgres",
    "qdrant",
    "vector",
    "rerank",
    "retrieval",
    "relation expansion",
    "openrouter",
    "model:",
    "model confidence",
    "cache",
    "timeout",
  ].some((token) => normalizedWarning.includes(token));
}
