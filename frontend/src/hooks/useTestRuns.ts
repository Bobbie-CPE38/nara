"use client";

import { useCallback } from "react";
import { usePolling } from "@/hooks/usePolling";
import { apiRequest } from "@/lib/api";
import type { TestRunView } from "@/lib/types/testRun";

/**
 * GET /demo/test-runs, read again every few seconds (round 6 PR EV5b, 6.35.5). An open run is
 * read from the Backend, not kept in the page, so it is still known after a reload or an API
 * restart, and on every page that shows it.
 */
export function useTestRuns() {
  const load = useCallback(async (signal: AbortSignal) => {
    const runs = await apiRequest<TestRunView[]>("/demo/test-runs", { signal });
    if (!Array.isArray(runs)) throw new Error("Invalid test run list");
    return runs;
  }, []);
  return usePolling(load);
}
