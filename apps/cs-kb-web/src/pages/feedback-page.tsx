import { useFeedbackQueue, useOpsAnalytics } from "@/hooks/api/kb-index";
import { FeedbackWorkspace } from "@/workspaces/feedback-workspace";

export function FeedbackPage() {
  const feedbackQuery = useFeedbackQueue();
  const analyticsQuery = useOpsAnalytics(7);

  return (
    <FeedbackWorkspace
      analytics={analyticsQuery.data}
      feedbackItems={feedbackQuery.data ?? []}
      loading={feedbackQuery.isLoading || analyticsQuery.isLoading}
      onRefresh={() => {
        void feedbackQuery.refetch();
        void analyticsQuery.refetch();
      }}
    />
  );
}
