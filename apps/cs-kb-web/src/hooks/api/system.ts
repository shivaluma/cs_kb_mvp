import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import type { AdminResetResponse, AdminResetStatus, SystemHealth } from "@/types";

import { queryKeys } from "./query-keys";

export function useSystemHealth() {
  return useQuery({
    queryKey: queryKeys.systemHealth,
    queryFn: () => apiGet<SystemHealth>("/api/v1/system/health"),
    refetchInterval: 30000,
  });
}

export function useAdminResetStatus() {
  return useQuery({
    queryKey: queryKeys.adminResetStatus,
    queryFn: () => apiGet<AdminResetStatus>("/api/v1/ai/admin/reset-status"),
    retry: false,
  });
}

export function useMagicResetData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { confirmation: string; actor: string; reason?: string }) =>
      apiPost<AdminResetResponse>("/api/v1/ai/admin/reset-data", payload, 90000),
    onSuccess: () => {
      void queryClient.invalidateQueries({ predicate: () => true });
    },
  });
}
