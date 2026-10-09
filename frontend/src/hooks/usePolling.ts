"use client";

import { useEffect, useState } from "react";

export type PollingOptions = {
  intervalMs?: number;
  enabled?: boolean;
};

/** Memoize load with useCallback; include case/staff IDs in its dependencies. */
export function usePolling<T>(
  load: (signal: AbortSignal) => Promise<T>,
  { intervalMs = 2000, enabled = true }: PollingOptions = {},
) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);

  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error("Polling interval must be a positive number");
  }

  useEffect(() => {
    setData(undefined);
    setError(null);
    setIsLoading(enabled);
    if (!enabled) return;

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const result = await load(controller.signal);
        if (!controller.signal.aborted) {
          setData(result);
          setError(null);
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause : new Error(String(cause)));
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
          // Schedule after completion so slow requests never overlap.
          timer = setTimeout(poll, intervalMs);
        }
      }
    }

    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, intervalMs, enabled]);

  return { data, error, isLoading };
}
