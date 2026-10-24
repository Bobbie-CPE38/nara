"use client";

import { useEffect, useState } from "react";
import type { Outcome } from "@/components/handoff/HandoffManager";
import type { HandoffCase } from "@/lib/types/handoff";

/**
 * Keeps the dialog of a case only while the list still lets the user manage it (round 6 PR
 * EV6): a case someone else staffed or closed, or one that left the list, closes the dialog
 * with a word instead of leaving a blank panel. The case list uses it too (round 6 PR EV8).
 */
export function useManagedCase(cases: readonly HandoffCase[] | undefined) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const selected = cases?.find((row) => row.id === selectedId && row.can_manage);

  useEffect(() => {
    if (selectedId === null || !cases) return;
    if (cases.some((row) => row.id === selectedId && row.can_manage)) return;
    const now = cases.find((row) => row.id === selectedId);
    setOutcome({
      kind: "info",
      message: now
        ? { key: "hand.noLonger", params: { id: selectedId, status: now.status } }
        : { key: "hand.noLongerHanded", params: { id: selectedId } },
    });
    setSelectedId(null);
  }, [cases, selectedId]);

  return {
    selected,
    outcome,
    setOutcome,
    open(caseId: number) {
      setOutcome(null);
      setSelectedId(caseId);
    },
    close() {
      setSelectedId(null);
    },
    /** The case left the handoff: the dialog closes and the page says what happened */
    done(result: Outcome) {
      setSelectedId(null);
      setOutcome(result);
    },
    reset() {
      setSelectedId(null);
      setOutcome(null);
    },
  };
}
