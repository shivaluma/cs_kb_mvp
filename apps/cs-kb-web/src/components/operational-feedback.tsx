import { IconMessageReport as MessageReport } from "@tabler/icons-react";

import { Button } from "@/components/ui/button";
import { useRecordKBEvent } from "@/hooks/api/kb-index";
import { useFeedback } from "@/providers/feedback-context";

const FEEDBACK_TYPES = [
  { value: "outdated", label: "Outdated" },
  { value: "wrong", label: "Wrong" },
  { value: "missing_step", label: "Missing step" },
  { value: "need_macro", label: "Need macro" },
  { value: "hard_to_understand", label: "Hard to understand" },
  { value: "search_result_wrong", label: "Search result wrong" },
] as const;

export function OperationalFeedbackButtons({
  className = "",
  entityId,
  entityType,
  metadata,
  sampleQuery,
  sourceTitle,
  targetTitle,
}: {
  className?: string;
  entityId: string;
  entityType: string;
  metadata?: Record<string, unknown>;
  sampleQuery?: string;
  sourceTitle?: string;
  targetTitle: string;
}) {
  const eventMutation = useRecordKBEvent();
  const { reportError, reportNotice } = useFeedback();

  function submitFeedback(feedbackType: string, label: string) {
    eventMutation.mutate(
      {
        action: "feedback_submitted",
        entity_type: entityType,
        entity_id: entityId,
        metadata: {
          feedback_type: feedbackType,
          target_title: targetTitle,
          source_title: sourceTitle ?? "",
          sample_query: sampleQuery ?? "",
          ...metadata,
        },
      },
      {
        onSuccess: () => reportNotice(`Feedback recorded: ${label}.`),
        onError: () => reportError("Could not record feedback. Please try again."),
      },
    );
  }

  return (
    <div className={className}>
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <MessageReport className="size-3.5" />
        Report issue
      </div>
      <div className="flex flex-wrap gap-1.5">
        {FEEDBACK_TYPES.map((item) => (
          <Button
            className="h-7 rounded-full px-2 text-xs"
            disabled={eventMutation.isPending}
            key={item.value}
            onClick={() => submitFeedback(item.value, item.label)}
            size="sm"
            type="button"
            variant="outline"
          >
            {item.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
