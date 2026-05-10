import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import type { Homepage } from "@/types";

import { queryKeys } from "./query-keys";

export function useHomepage() {
  return useQuery({
    queryKey: queryKeys.homepage,
    queryFn: () => apiGet<Homepage>("/api/v1/homepage"),
  });
}
