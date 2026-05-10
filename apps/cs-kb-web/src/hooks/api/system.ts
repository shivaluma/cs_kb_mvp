import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import type { SystemHealth } from "@/types";

import { queryKeys } from "./query-keys";

export function useSystemHealth() {
  return useQuery({
    queryKey: queryKeys.systemHealth,
    queryFn: () => apiGet<SystemHealth>("/api/v1/system/health"),
    refetchInterval: 30000,
  });
}
