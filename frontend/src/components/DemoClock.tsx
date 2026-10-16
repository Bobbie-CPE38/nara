"use client";

import { useCallback } from "react";
import { usePolling } from "@/hooks/usePolling";
import { apiRequest } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ClockView } from "@/lib/types/attendance";

/** The backend clock in the menu bar (R5-Q18): check-in and NO_SHOW use this time, not the browser's. */
export function DemoClock() {
  const load = useCallback((signal: AbortSignal) => apiRequest<ClockView>("/clock", { signal }), []);
  const { data, error } = usePolling(load);
  if (data === undefined) {
    return <span className="ml-auto text-slate-500">{error ? "Clock unavailable" : "Clock…"}</span>;
  }
  return (
    <span className="ml-auto" role="status" aria-label="Backend clock">
      Backend clock: {formatDateTime(data.now)}{" "}
      <span className="text-slate-500">{data.frozen ? "(demo, frozen)" : "(real time)"}</span>
    </span>
  );
}
