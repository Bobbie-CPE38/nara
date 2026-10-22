"use client";

import { type FormEvent, useCallback, useState } from "react";
import { useSessionUser, useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { usePolling } from "@/hooks/usePolling";
import { apiRequest } from "@/lib/api";
import { bangkokIso } from "@/lib/authForms";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { StaffRoster } from "@/lib/types/auth";
import type { EventResult } from "@/lib/types/event";

function LeaveForm({ staffId }: { staffId: number }) {
  const t = useT();
  // Only the shifts the person is assigned to: the Backend checks it again before it writes
  const load = useCallback(
    (signal: AbortSignal) => apiRequest<StaffRoster>(`/roster?staff_id=${staffId}`, { signal }),
    [staffId],
  );
  // Polled: a shift assigned while the page is open must appear without a reload
  const { data, error, isLoading } = usePolling(load);
  const shifts = (data?.assignments ?? []).filter((row) => row.status === "ASSIGNED");
  const [chosen, setChosen] = useState<number | null>(null);
  const shiftId = chosen !== null && shifts.some((row) => row.shift.id === chosen) ? chosen : (shifts[0]?.shift.id ?? null);
  const [endAt, setEndAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [result, setResult] = useState<EventResult | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (shiftId === null) return;
    setBusy(true);
    setFailure(null);
    setResult(null);
    try {
      const end = bangkokIso(endAt);
      // The body has no staff ID, event type or reason: the Backend knows who you are
      setResult(
        await apiRequest<EventResult>("/me/unavailability", {
          method: "POST",
          json: end === undefined ? { shift_id: shiftId } : { shift_id: shiftId, end_at: end },
        }),
      );
    } catch (cause) {
      setFailure(cause);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-xl">
      {isLoading && !data && <p role="status">{t("leave.loading")}</p>}
      {error && !data && (
        <Notice kind="error" role="alert">
          {t("leave.loadFailed", { error: describeError(error, t) })}
        </Notice>
      )}
      {data && shifts.length === 0 && <p>{t("leave.noShifts")}</p>}
      {data && shifts.length > 0 && (
        <form onSubmit={(event) => void submit(event)} className="space-y-3">
          <div>
            <label className="block" htmlFor="leave-shift">
              {t("leave.shift")}
            </label>
            <select
              id="leave-shift"
              value={shiftId ?? ""}
              disabled={busy}
              onChange={(event) => setChosen(Number(event.target.value))}
            >
              {shifts.map((row) => (
                <option key={row.id} value={row.shift.id}>
                  {t("leave.shiftOption", {
                    id: row.shift.id,
                    ward: row.shift.ward_name,
                    start: formatDateTime(row.shift.start_at),
                    end: formatDateTime(row.shift.end_at),
                  })}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block" htmlFor="leave-end">
              {t("leave.endAt")}
            </label>
            <input
              id="leave-end"
              type="datetime-local"
              value={endAt}
              disabled={busy}
              onChange={(event) => setEndAt(event.target.value)}
            />
            <p className="mt-1 text-sm text-slate-600">{t("leave.endAtHint")}</p>
          </div>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? t("leave.busy") : t("leave.submit")}
          </Button>
        </form>
      )}
      {result && (
        <div role="status" className="mt-4 space-y-1 text-green-700">
          <p>{t("leave.sent", { event: result.event_id, status: result.event_status })}</p>
          <p>
            {result.case_id === null
              ? t("leave.noCase")
              : t("leave.case", { case: result.case_id, status: result.case_status ?? "" })}
          </p>
        </div>
      )}
      {failure !== null && (
        <div className="mt-4">
          <Notice kind="error" role="alert">
            {t("leave.failed", { error: describeError(failure, t) })}
          </Notice>
        </div>
      )}
    </Card>
  );
}

/** A nurse reports their own leave; it takes effect at once (docs/workflow.md 6.33.4). */
export default function LeavePage() {
  const t = useT();
  const { state } = useAuth();
  const me = useSessionUser();
  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("leave.title")} description={t("leave.intro")} />
      {state.status === "demo" && (
        <Notice kind="info" role="status">
          {t("leave.demoOnly")}
        </Notice>
      )}
      {me && <LeaveForm key={me.staff_id} staffId={me.staff_id} />}
    </main>
  );
}
