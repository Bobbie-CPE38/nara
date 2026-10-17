"use client";

import { useCallback } from "react";
import { usePolling } from "@/hooks/usePolling";
import { apiRequest } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { ClockView } from "@/lib/types/attendance";

/** The backend clock in the menu bar (R5-Q18): check-in and NO_SHOW use this time, not the browser's. */
export function DemoClock() {
  const t = useT();
  const load = useCallback((signal: AbortSignal) => apiRequest<ClockView>("/clock", { signal }), []);
  const { data, error } = usePolling(load);
  if (data === undefined) {
    return <span className="text-slate-500">{error ? t("clock.unavailable") : t("clock.loading")}</span>;
  }
  return (
    <span role="status" aria-label={t("clock.label")}>
      {t("clock.backend")} {formatDateTime(data.now)}{" "}
      <span className="text-slate-500">{data.frozen ? t("clock.frozen") : t("clock.real")}</span>
      {error && <span className="ml-1 text-amber-700">{t("clock.stale")}</span>}
    </span>
  );
}
