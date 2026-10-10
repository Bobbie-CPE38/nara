"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type PollingOptions<T = unknown> = {
  intervalMs?: number;
  enabled?: boolean;
  /** Abort stalled reads and retry; refresh cannot wait longer than this. */
  timeoutMs?: number;
  /** Return true to end polling after this result, e.g. a final case status. The data stays. */
  stopOnData?: (data: T) => boolean;
  /** Return true to end polling after this error, e.g. a 404. Earlier data stays. */
  stopOnError?: (error: Error) => boolean;
};

/** Memoize load with useCallback; include case/staff IDs in its dependencies. */
export function usePolling<T>(
  load: (signal: AbortSignal) => Promise<T>,
  {
    intervalMs = 2000,
    enabled = true,
    timeoutMs = 10000,
    stopOnData,
    stopOnError,
  }: PollingOptions<T> = {},
) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const refreshRef = useRef<() => void>(() => {});
  const refresh = useCallback(() => refreshRef.current(), []);
  // Read through a ref so an inline callback does not restart polling.
  const stopRef = useRef({ stopOnData, stopOnError });

  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error("Polling interval must be a positive number");
  }
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error("Polling timeout must be a positive number");
  }

  useEffect(() => {
    stopRef.current = { stopOnData, stopOnError };
  });

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
    let requestController: AbortController | undefined;
    let deadlineTimer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      inFlight = true;
      refreshQueued = false;
      const request = new AbortController();
      requestController = request;
      let timeout: ReturnType<typeof setTimeout> | undefined;
      let stop = false;
      try {
        const deadline = new Promise<T>((_, reject) => {
          timeout = setTimeout(() => {
            request.abort();
            reject(
              new Error(`Polling request timed out after ${timeoutMs} ms`),
            );
          }, timeoutMs);
          deadlineTimer = timeout;
        });
        const result = await Promise.race([load(request.signal), deadline]);
        if (!controller.signal.aborted) {
          setData(result);
          setError(null);
          stop = stopRef.current.stopOnData?.(result) ?? false;
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          const failure =
            cause instanceof Error ? cause : new Error(String(cause));
          setError(failure);
          stop = stopRef.current.stopOnError?.(failure) ?? false;
        }
      } finally {
        clearTimeout(timeout);
        inFlight = false;
        if (!controller.signal.aborted) {
          setIsLoading(false);
          // A refresh during a request waits for it, then runs once more,
          // even when this result ended the regular polling.
          if (refreshQueued) void poll();
          else if (!stop) timer = setTimeout(poll, intervalMs);
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
      requestController?.abort();
      clearTimeout(deadlineTimer);
      clearTimeout(timer);
      refreshRef.current = () => {};
    };
  }, [load, intervalMs, enabled, timeoutMs]);

  return { data, error, isLoading, refresh };
}
