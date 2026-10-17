"use client";

import Link from "next/link";
import { Suspense, useCallback, useMemo, useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { ActingAs } from "@/components/ActingAs";
import { GapIntervals } from "@/components/case/GapTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { wardName } from "@/lib/demo";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type { Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { Dashboard, GapShiftDetail, GapShiftSummary } from "@/lib/types/dashboard";

/** The API's own words for a refused read (403 ward, 404 shift, 409 not set up). */
function errorText(cause: Error, t: Translate): string {
  return cause instanceof ApiError ? `${describeError(cause, t)} (HTTP ${cause.status})` : describeError(cause, t);
}

/** Read-only: this page never creates an event or a case; that stays in Demo control (R6-Q17). */
function ShiftDetail({ detail }: { detail: GapShiftDetail }) {
  const t = useT();
  return (
    <Card label={t("gapPage.detail")} title={t("gapPage.detailTitle", { id: detail.shift_id, ward: wardName(detail.ward_id) })} className="mt-4">
      <p className="mt-1 text-sm">
        {t("gapPage.range", { start: formatDateTime(detail.start_at), end: formatDateTime(detail.end_at) })}
        {detail.evaluated_from && detail.evaluated_from !== detail.start_at &&
          ` · ${t("gapPage.measuredFrom", { time: formatDateTime(detail.evaluated_from) })}`}
      </p>
      <p className="mt-1">
        {detail.case_id === null ? (
          t("gapPage.noCase")
        ) : (
          <Link className="underline" href={`/cases/${detail.case_id}`}>
            {t("gapPage.openCase", { id: detail.case_id })}
          </Link>
        )}
      </p>
      <GapIntervals intervals={detail.intervals} />
      <h3 className="mt-4">{t("gapPage.roster")}</h3>
      {detail.roster.length === 0 ? (
        <p className="mt-1">{t("gapPage.noRoster")}</p>
      ) : (
        <ScrollX>
          <table aria-label={t("gapPage.roster")} className="mt-2">
            <thead>
              <tr>
                <th>{t("common.staff")}</th>
                <th>{t("common.name")}</th>
                <th>{t("cand.status")}</th>
                <th>{t("common.from")}</th>
                <th>{t("common.until")}</th>
                <th>{t("gapPage.onLeave")}</th>
                <th>{t("gapPage.checkedIn")}</th>
              </tr>
            </thead>
            <tbody>
              {detail.roster.map((row) => (
                <tr key={row.roster_assignment_id}>
                  <td>{row.staff_id}</td>
                  <td>{row.name}</td>
                  <td className={row.status === "CANCELLED" ? "text-slate-500" : ""}>
                    {row.status}
                  </td>
                  <td>{formatDateTime(row.effective_start_at)}</td>
                  <td>{formatDateTime(row.effective_end_at)}</td>
                  <td className={row.on_leave ? "font-medium text-amber-700" : ""}>
                    {row.on_leave ? t("gapPage.yes") : t("gapPage.no")}
                  </td>
                  <td>{row.checked_in ? t("gapPage.yes") : t("gapPage.no")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollX>
      )}
    </Card>
  );
}

function GapCheckPage() {
  const t = useT();
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);

  // One read tells which wards this user sees and what day the Backend Clock is on
  const loadWards = useCallback((signal: AbortSignal) => api<Dashboard>("/dashboard", { signal }), [api]);
  const stopAfterFirstRead = useCallback(() => true, []);
  const { data: dashboard, error: wardsError } = usePolling(loadWards, { stopOnData: stopAfterFirstRead });

  const [wardChoice, setWardChoice] = useState<number | null>(null);
  const [dateChoice, setDateChoice] = useState<string | null>(null);
  const [shiftId, setShiftId] = useState<number | null>(null);

  const wardIds = dashboard?.wards ?? [];
  const wardId = wardChoice !== null && wardIds.includes(wardChoice) ? wardChoice : (wardIds[0] ?? null);
  // The day of the Backend Clock in Bangkok, as YYYY-MM-DD
  const clockDate = dashboard ? formatDateTime(dashboard.now).slice(0, 10) : "";
  const date = dateChoice ?? clockDate;
  const canList = wardId !== null && date !== "";

  const loadShifts = useCallback(
    (signal: AbortSignal) =>
      api<GapShiftSummary[]>(`/gap/shifts?ward_id=${wardId}&date=${encodeURIComponent(date)}`, { signal }),
    [api, wardId, date],
  );
  const { data: shifts, error: shiftsError } = usePolling(loadShifts, { enabled: canList });

  const loadDetail = useCallback(
    (signal: AbortSignal) => api<GapShiftDetail>(`/gap/shifts/${shiftId}`, { signal }),
    [api, shiftId],
  );
  const { data: detail, error: detailError } = usePolling(loadDetail, { enabled: shiftId !== null });

  function changeActor(id: number) {
    setActorId(id);
    setWardChoice(null);
    setShiftId(null);
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("gapPage.title")} description={t("gapPage.intro")}>
        <ActingAs id="gap-viewing-as" value={actorId} onChange={changeActor} />
      </PageHeader>

      {wardsError && <Notice kind="error" role="alert">{errorText(wardsError, t)}</Notice>}
      {!dashboard && !wardsError && <p>{t("common.loading")}</p>}
      {dashboard && (
        <Card>
          <form className="flex flex-wrap items-end gap-4" onSubmit={(event) => event.preventDefault()}>
            <label className="block text-sm font-medium" htmlFor="gap-ward">
              {t("common.ward")}{" "}
              <select
                id="gap-ward"
                value={wardId ?? ""}
                onChange={(event) => {
                  setWardChoice(Number(event.target.value));
                  setShiftId(null);
                }}
              >
                {wardIds.map((id) => (
                  <option key={id} value={id}>
                    {wardName(id)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm font-medium" htmlFor="gap-date">
              {t("gapPage.day")}{" "}
              <input
                id="gap-date"
                type="date"
                min="2000-01-01"
                max="2999-12-31"
                value={date}
                onChange={(event) => {
                  setDateChoice(event.target.value);
                  setShiftId(null);
                }}
              />
            </label>
          </form>
        </Card>
      )}

      {shiftsError && <div className="mt-4"><Notice kind="error" role="alert">{errorText(shiftsError, t)}</Notice></div>}
      {canList && !shifts && !shiftsError && <p className="mt-4">{t("gapPage.loadingShifts")}</p>}
      {shifts && shifts.length === 0 && <p className="mt-4">{t("gapPage.noShifts")}</p>}
      {shifts && shifts.length > 0 && (
        <Card className="mt-4">
          <ScrollX>
            <table aria-label={t("gapPage.shiftsOfDay")}>
              <thead>
                <tr>
                  <th>{t("common.shift")}</th>
                  <th>{t("common.from")}</th>
                  <th>{t("common.until")}</th>
                  <th>{t("gap.required")}</th>
                  <th>{t("gapPage.onRoster")}</th>
                  <th>{t("dash.shortBy")}</th>
                  <th>{t("common.case")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {shifts.map((row) => (
                  <tr key={row.shift_id}>
                    <td>{row.shift_id}</td>
                    <td>{formatDateTime(row.start_at)}</td>
                    <td>{formatDateTime(row.end_at)}</td>
                    <td>{row.required_staff}</td>
                    <td>{row.rostered_count}</td>
                    <td className={row.headcount_gap > 0 ? "font-semibold text-red-700" : "text-green-700"}>
                      {row.headcount_gap > 0 ? row.headcount_gap : t("gap.ok")}
                    </td>
                    <td>
                      {row.case_id === null ? (
                        "—"
                      ) : (
                        <Link className="underline" href={`/cases/${row.case_id}`}>
                          {row.case_id}
                        </Link>
                      )}
                    </td>
                    <td>
                      <Button
                        aria-pressed={shiftId === row.shift_id}
                        onClick={() => setShiftId(row.shift_id)}
                      >
                        {t("gapPage.checkShift", { id: row.shift_id })}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollX>
        </Card>
      )}

      {detailError && <div className="mt-4"><Notice kind="error" role="alert">{errorText(detailError, t)}</Notice></div>}
      {shiftId !== null && !detail && !detailError && <p className="mt-4">{t("gapPage.loadingShift")}</p>}
      {detail && <ShiftDetail detail={detail} />}
    </main>
  );
}

export default function GapCheck() {
  return (
    <Suspense>
      <GapCheckPage />
    </Suspense>
  );
}
