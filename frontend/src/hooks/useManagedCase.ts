"use client";

import { useCallback, useEffect, useState } from "react";
import type { Outcome } from "@/components/handoff/HandoffManager";
import type { createDemoApi } from "@/lib/api";
import type { CasePage, HandoffCase } from "@/lib/types/handoff";

type Api = ReturnType<typeof createDemoApi>;

/** Enough rows to find one case among the few whose shift has the same number as its ID */
const OWN_ROW_PAGE_SIZE = 100;

/**
 * Keeps the dialog of a case only while the case can still be managed (round 6 PR EV6): a case
 * someone else staffed or closed closes the dialog with a word instead of leaving a blank panel.
 * The case list uses it too (round 6 PR EV8).
 *
 * Only the case's own row decides (review of #147): newer cases can push it off the page the
 * user is on (the case list is newest first), so a case missing from the page is read again by
 * its ID, with the same rights, and the dialog stays open while that row can be managed. The
 * last such row is kept meanwhile, so the dialog never closes and opens again between reads.
 */
export function useManagedCase(cases: readonly HandoffCase[] | undefined, api: Api) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // The last row of the selected case that could be managed, from the page or read by its ID
  const [lastRow, setLastRow] = useState<HandoffCase | null>(null);
  const listed = cases?.find((row) => row.id === selectedId);
  const known = listed ?? (lastRow !== null && lastRow.id === selectedId ? lastRow : undefined);
  const selected = known?.can_manage ? known : undefined;

  const stop = useCallback((caseId: number, status: string | null) => {
    setOutcome({
      kind: "info",
      message:
        status !== null
          ? { key: "hand.noLonger", params: { id: caseId, status } }
          : { key: "hand.noLongerHanded", params: { id: caseId } },
    });
    setSelectedId(null);
    setLastRow(null);
  }, []);

  useEffect(() => {
    if (selectedId === null || !cases) return;
    const row = cases.find((item) => item.id === selectedId);
    if (row !== undefined) {
      if (row.can_manage) setLastRow(row);
      else stop(selectedId, row.status);
      return;
    }
    let current = true;
    api<CasePage>(`/cases/search?q=${selectedId}&page=1&page_size=${OWN_ROW_PAGE_SIZE}`)
      .then((page) => {
        if (!current) return;
        const own = page.items.find((item) => item.id === selectedId);
        if (own?.can_manage) setLastRow(own);
        // Gone from what the user may read (a reset), or no longer handed off
        else stop(selectedId, own?.status ?? null);
      })
      // A read that failed keeps the dialog: the next poll of the list asks again
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [api, cases, selectedId, stop]);

  return {
    selected,
    outcome,
    setOutcome,
    open(caseId: number) {
      setOutcome(null);
      setLastRow(cases?.find((row) => row.id === caseId) ?? null);
      setSelectedId(caseId);
    },
    close() {
      setSelectedId(null);
      setLastRow(null);
    },
    /** The case left the handoff: the dialog closes and the page says what happened */
    done(result: Outcome) {
      setSelectedId(null);
      setLastRow(null);
      setOutcome(result);
    },
    reset() {
      setSelectedId(null);
      setLastRow(null);
      setOutcome(null);
    },
  };
}
