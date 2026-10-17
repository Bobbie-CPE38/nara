"use client";

import { useCallback, useRef, useState } from "react";
import { createDemoApi } from "@/lib/api";
import type { HandoverView } from "@/lib/types/case";
import { usePolling } from "@/hooks/usePolling";

export type HandoverPage = {
  active: HandoverView[];
  history: HandoverView[];
  next_cursor: string | null;
};

/** Refresh the loaded prefix from page one, so status changes and new history
 * replace old rows instead of leaving stale active assignments in the browser. */
export function useHandoverHistory(staffId: number) {
  const wanted = useRef(1);
  const busy = useRef(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const load = useCallback(async (signal: AbortSignal): Promise<HandoverPage> => {
    const api = createDemoApi(staffId);
    const first = await api<HandoverPage>("/me/handovers", { signal });
    if (!Array.isArray(first.active) || !Array.isArray(first.history)) {
      throw new Error("Invalid handover page");
    }
    const rows = new Map(first.history.map((row) => [row.handover_id, row]));
    let cursor = first.next_cursor;
    const pages = wanted.current;
    for (let page = 1; page < pages && cursor; page += 1) {
      const next = await api<HandoverPage>(
        `/me/handovers?cursor=${encodeURIComponent(cursor)}`, { signal },
      );
      for (const row of next.history) rows.set(row.handover_id, row);
      cursor = next.next_cursor;
    }
    for (const row of first.active) rows.delete(row.handover_id);
    return { active: first.active, history: [...rows.values()], next_cursor: cursor };
  }, [staffId]);
  const polling = usePolling(load);
  async function loadMore() {
    if (busy.current || !polling.data?.next_cursor) return;
    busy.current = true;
    setLoadingMore(true);
    wanted.current += 1;
    try {
      await polling.refresh();
    } finally {
      busy.current = false;
      setLoadingMore(false);
    }
  }
  return { ...polling, loadingMore, loadMore };
}
