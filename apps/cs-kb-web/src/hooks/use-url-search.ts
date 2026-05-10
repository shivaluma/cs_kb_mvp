import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useMemo } from "react";

type SearchValue = string | number | boolean | null | undefined;
type SearchPatch = Record<string, SearchValue>;

function cleanSearch(search: Record<string, unknown>, patch: SearchPatch) {
  const next: Record<string, unknown> = { ...search };
  for (const [key, value] of Object.entries(patch)) {
    if (value === "" || value === null || value === undefined || value === false) {
      delete next[key];
    } else {
      next[key] = value;
    }
  }
  return next;
}

export function useUrlSearch() {
  const navigate = useNavigate();
  const search = useRouterState({
    select: (state) => state.location.search as Record<string, unknown>,
  });

  return useMemo(
    () => ({
      getParam: (key: string, fallback = "") => {
        const value = search[key];
        return typeof value === "string" ? value : fallback;
      },
      search,
      setParams: (patch: SearchPatch, replace = true) => {
        void navigate({
          replace,
          search: (previous: Record<string, unknown>) => cleanSearch(previous, patch),
        } as never);
      },
    }),
    [navigate, search],
  );
}
