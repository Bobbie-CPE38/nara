"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
  const refreshRef = useRef<() => void>(() => {});
  const refresh = useCallback(() => refreshRef.current(), []);

  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error("Polling interval must be a positive number");
  }

  useEffect(() => {
    setData(undefined);
    setError(null);
    setIsLoading(enabled);
    refreshRef.current = () => {};
    if (!enabled) return;

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;
    let refreshQueued = false;

    async function poll() {
      inFlight = true;
      refreshQueued = false;
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
        inFlight = false;
        if (!controller.signal.aborted) {
          setIsLoading(false);
          // A refresh during a request waits for it, then runs once more.
          if (refreshQueued) void poll();
          else timer = setTimeout(poll, intervalMs);
        }
      }
    }

    refreshRef.current = () => {
      clearTimeout(timer);
      if (inFlight) refreshQueued = true;
      else void poll();
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
      refreshRef.current = () => {};
    };
  }, [load, intervalMs, enabled]);

  return { data, error, isLoading, refresh };
}
