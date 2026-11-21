"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import type { HandoverView } from "@/lib/types/case";

export type HandoverPage = {
  active: HandoverView[];
  history: HandoverView[];
  next_cursor: string | null;
};

function validatePage(page: HandoverPage): HandoverPage {
  if (!page || !Array.isArray(page.active) || !Array.isArray(page.history)
    || !(page.next_cursor === null || typeof page.next_cursor === "string")) {
    throw new Error("Invalid handover page");
  }
  return page;
}

function mergeHistory(active: HandoverView[], ...pages: HandoverView[][]): HandoverView[] {
  const rows = new Map<number, HandoverView>();
  for (const page of pages) {
    for (const row of page) if (!rows.has(row.handover_id)) rows.set(row.handover_id, row);
  }
  for (const row of active) rows.delete(row.handover_id);
  return [...rows.values()].sort((a, b) =>
    Date.parse(b.generated_at) - Date.parse(a.generated_at) || b.handover_id - a.handover_id,
  );
}

/** Poll only page one. Older history is cached until the page is reopened; clicking
 * Load more fetches exactly one page, with its own deadline and cancellation. */
export function useHandoverHistory(staffId: number) {
  const cache = useRef<HandoverPage | undefined>(undefined);
  const expanded = useRef(false);
  const moreRequest = useRef<AbortController | null>(null);
  const revision = useRef(0);
  const generation = useRef(0);
  const [data, setData] = useState<HandoverPage>();
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<Error | null>(null);

  useEffect(() => {
    cache.current = undefined;
    expanded.current = false;
    setData(undefined);
    setMoreError(null);
    setLoadingMore(false);
    return () => {
      generation.current += 1;
      moreRequest.current?.abort();
      moreRequest.current = null;
    };
  }, [staffId]);

  const load = useCallback(async (signal: AbortSignal): Promise<HandoverPage> => {
    const first = validatePage(await createDemoApi(staffId)<HandoverPage>("/me/handovers", { signal }));
    if (signal.aborted) throw new Error("Handover read cancelled");
    revision.current += 1;
    const previous = cache.current;
    // A complete first page is authoritative, including an empty list after demo reset.
    if (first.next_cursor === null) {
      expanded.current = false;
      generation.current += 1;
    }
    // A missing active row may have been deleted, not completed. Only retain
    // history explicitly returned by the server; never invent an inactive row.
    const page = expanded.current && previous ? {
      active: first.active,
      history: mergeHistory(first.active, first.history, previous.history),
      next_cursor: previous.next_cursor,
    } : first;
    cache.current = page;
    setData(page);
    return page;
  }, [staffId]);
  const polling = usePolling(load);

  async function loadMore() {
    const cursor = cache.current?.next_cursor;
    if (moreRequest.current || !cursor) return;
    const controller = new AbortController();
    const startedRevision = revision.current;
    const startedGeneration = generation.current;
    moreRequest.current = controller;
    setLoadingMore(true);
    setMoreError(null);
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const deadline = new Promise<never>((_, reject) => {
        timeout = setTimeout(() => {
          controller.abort();
          reject(new Error("Handover history request timed out after 10000 ms"));
        }, 10000);
      });
      const next = validatePage(await Promise.race([
        createDemoApi(staffId)<HandoverPage>(
          `/me/handovers?cursor=${encodeURIComponent(cursor)}`, { signal: controller.signal },
        ),
        deadline,
      ]));
      if (controller.signal.aborted || generation.current !== startedGeneration) return;
      const previous = cache.current!;
      // A page-one poll completed while this read was pending: keep its newer active list.
      const active = revision.current === startedRevision ? next.active : previous.active;
      const page = {
        active,
        history: mergeHistory(active, next.history, previous.history),
        next_cursor: next.next_cursor,
      };
      expanded.current = true;
      cache.current = page;
      setData(page);
    } catch (cause) {
      if (generation.current === startedGeneration) {
        setMoreError(cause instanceof Error ? cause : new Error(String(cause)));
      }
    } finally {
      clearTimeout(timeout);
      if (moreRequest.current === controller) {
        moreRequest.current = null;
        setLoadingMore(false);
      }
    }
  }
  return {
    ...polling, data, error: moreError ?? polling.error,
    loadMoreError: moreError, loadingMore, loadMore,
  };
}
