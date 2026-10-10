"use client";

import { useEffect, useRef, useState } from "react";

export type PollingOptions<T = unknown> = {
  intervalMs?: number;
  enabled?: boolean;
  /** Return true to end polling after this result, e.g. a final case status. The data stays. */
  stopOnData?: (data: T) => boolean;
  /** Return true to end polling after this error, e.g. a 404. Earlier data stays. */
  stopOnError?: (error: Error) => boolean;
};

/** Memoize load with useCallback; include case/staff IDs in its dependencies. */
export function usePolling<T>(
  load: (signal: AbortSignal) => Promise<T>,
  { intervalMs = 2000, enabled = true, stopOnData, stopOnError }: PollingOptions<T> = {},
) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  // Read through a ref so an inline callback does not restart polling.
  const stopRef = useRef({ stopOnData, stopOnError });

  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error("Polling interval must be a positive number");
  }

  useEffect(() => {
    stopRef.current = { stopOnData, stopOnError };
  });

  useEffect(() => {
    setData(undefined);
    setError(null);
    setIsLoading(enabled);
    if (!enabled) return;

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      let stop = false;
      try {
        const result = await load(controller.signal);
        if (!controller.signal.aborted) {
          setData(result);
          setError(null);
          stop = stopRef.current.stopOnData?.(result) ?? false;
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          const failure = cause instanceof Error ? cause : new Error(String(cause));
          setError(failure);
          stop = stopRef.current.stopOnError?.(failure) ?? false;
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
          // Schedule after completion so slow requests never overlap.
          if (!stop) timer = setTimeout(poll, intervalMs);
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
