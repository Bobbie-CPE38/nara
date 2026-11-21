"use client";

import { useBackendClock } from "@/components/ClockProvider";
import { formatDateTime } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { ClockView } from "@/lib/types/attendance";

/** What the clock does, after its time. An older Backend sends no mode: frozen or real */
const MODE_TEXT: Record<NonNullable<ClockView["mode"]>, MessageKey> = {
  frozen: "clock.frozen",
  real: "clock.real",
  scenario: "clock.scenario",
  // Round 6 PR EV6: real speed from a time set on the Demo control
  running: "clock.running",
};

/** The backend clock in the menu bar (R5-Q18): check-in and NO_SHOW use this time, not the browser's. */
export function DemoClock() {
  const t = useT();
  const { data, error } = useBackendClock();
  if (data === undefined) {
    return <span className="text-slate-500">{error ? t("clock.unavailable") : t("clock.loading")}</span>;
  }
  return (
    <span role="status" aria-label={t("clock.label")}>
      {t("clock.backend")} {formatDateTime(data.now)}{" "}
      <span className="text-slate-500">
        {t(MODE_TEXT[data.mode ?? (data.frozen ? "frozen" : "real")])}
      </span>
      {error && <span className="ml-1 text-amber-700">{t("clock.stale")}</span>}
    </span>
  );
}
