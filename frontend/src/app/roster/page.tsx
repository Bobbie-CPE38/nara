"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import { ActingAs } from "@/components/ActingAs";
import { ScrollX } from "@/components/ScrollX";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { POLL_INTERVAL_MS } from "@/lib/constants";
import { formatDemoTime, wardName } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { Dashboard, GapShiftSummary } from "@/lib/types/dashboard";
import type { ShiftRoster } from "@/lib/types/roster";

type Api = ReturnType<typeof createDemoApi>;

const COLUMNS: readonly MessageKey[] = [
  "roster.col.assignment",
  "common.staff",
  "common.role",
  "cand.homeWard",
  "roster.col.staffStatus",
  "roster.col.rosterStatus",
  "roster.col.type",
  "cand.source",
  "roster.col.interval",
  "roster.col.transferred",
];

function Roster({ api, shiftId }: { api: Api; shiftId: number }) {
  const t = useT();
  const load = useCallback(
    (signal: AbortSignal) =>
      api<ShiftRoster>(`/roster?shift_id=${shiftId}`, { signal }),
    [api, shiftId],
  );
  const { data, error, isLoading } = usePolling(load);
  return (
    <section className="mt-6 space-y-4" aria-label={t("roster.title")}>
      {isLoading && <p role="status">{t("roster.loading")}</p>}
      {error && (
        <Notice kind="error" role="alert">
          {t("roster.refreshFailed", { error: describeError(error, t) })}
        </Notice>
      )}
      {data && (
        <Card>
          <h2 className="text-lg font-semibold text-brand-800">
            {t("roster.heading", {
              ward: data.shift.ward_name,
              id: data.shift.id,
              type: data.shift.shift_type,
            })}
            {!data.shift.is_active && t("roster.inactive")}
          </h2>
          <p className="mt-1">
            {formatDemoTime(data.shift.start_at)} –{" "}
            {formatDemoTime(data.shift.end_at)} {t("roster.bangkok")}
          </p>
          {data.assignments.length === 0 ? (
            <p className="mt-3">{t("roster.none")}</p>
          ) : (
            <ScrollX>
              <table className="mt-3 text-sm">
                <caption className="sr-only">
                  {t("roster.caption", { id: shiftId })}
                </caption>
                <thead>
                  <tr>
                    {COLUMNS.map((label) => (
                      <th key={label} scope="col">
                        {t(label)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.assignments.map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td>
                      <td>
                        {row.staff_id} — {row.first_name} {row.last_name}
                      </td>
                      <td>{row.role_name}</td>
                      <td>
                        {row.home_ward_name}
                        {row.home_ward_id !== data.shift.ward_id &&
                          t("roster.crossWard")}
                      </td>
                      <td>{row.staff_status}</td>
                      <td className="font-medium">
                        {row.status}
                        {row.is_unavailable && (
                          <span className="ml-2">
                            <Badge tone="waiting">{t("roster.onLeave")}</Badge>
                          </span>
                        )}
                      </td>
                      <td>{row.assignment_type}</td>
                      <td>{row.candidate_source ?? "—"}</td>
                      <td>
                        {formatDemoTime(row.actual_start_at ?? data.shift.start_at)} –{" "}
                        {formatDemoTime(row.actual_end_at ?? data.shift.end_at)}
                      </td>
                      <td>{row.transferred_from_assignment_id ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollX>
          )}
          <p className="mt-3 text-sm text-slate-600">{t("roster.note")}</p>
        </Card>
      )}
    </section>
  );
}

/**
 * The roster of one shift (round 6 PR EV6, docs/workflow.md 6.36.4): the wards and the shifts
 * to pick from are only the ones the user may see, read from the Dashboard and the gap list,
 * as the user who is logged in or the demo user picked, never a fixed head nurse.
 */
function RosterPage() {
  const t = useT();
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);

  // One read: the wards this user sees and the day of the Backend Clock
  const loadWards = useCallback((signal: AbortSignal) => api<Dashboard>("/dashboard", { signal }), [api]);
  const stopAfterFirstRead = useCallback(() => true, []);
  const { data: dashboard, error: wardsError } = usePolling(loadWards, { stopOnData: stopAfterFirstRead });

  const [wardChoice, setWardChoice] = useState<number | null>(null);
  const [dateChoice, setDateChoice] = useState<string | null>(null);
  const [shiftChoice, setShiftChoice] = useState<number | null>(null);

  const wards = dashboard?.ward_options ?? (dashboard?.wards ?? []).map((id) => ({ id, name: wardName(id) }));
  const wardId = wardChoice !== null && wards.some((ward) => ward.id === wardChoice) ? wardChoice : (wards[0]?.id ?? null);
  const clockDate = dashboard ? formatDateTime(dashboard.now).slice(0, 10) : "";
  const date = dateChoice ?? clockDate;
  const canList = wardId !== null && date !== "";

  const loadShifts = useCallback(
    (signal: AbortSignal) =>
      api<GapShiftSummary[]>(`/gap/shifts?ward_id=${wardId}&date=${encodeURIComponent(date)}`, { signal }),
    [api, wardId, date],
  );
  const { data: shifts, error: shiftsError } = usePolling(loadShifts, { enabled: canList });
  const shiftId =
    shiftChoice !== null && shifts?.some((shift) => shift.shift_id === shiftChoice)
      ? shiftChoice
      : (shifts?.[0]?.shift_id ?? null);

  function changeActor(id: number) {
    setActorId(id);
    setWardChoice(null);
    setShiftChoice(null);
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("roster.title")} description={t("roster.intro", { seconds: POLL_INTERVAL_MS / 1000 })}>
        <ActingAs id="roster-viewing-as" value={actorId} onChange={changeActor} />
      </PageHeader>
      {wardsError && <Notice kind="error" role="alert">{describeError(wardsError, t)}</Notice>}
      {!dashboard && !wardsError && <p>{t("common.loading")}</p>}
      {dashboard && (
        <Card>
          <form className="flex flex-wrap items-end gap-4" onSubmit={(event) => event.preventDefault()}>
            <label className="block text-sm font-medium" htmlFor="roster-ward">
              {t("common.ward")}{" "}
              <select
                id="roster-ward"
                value={wardId ?? ""}
                onChange={(event) => {
                  setWardChoice(Number(event.target.value));
                  setShiftChoice(null);
                }}
              >
                {wards.map((ward) => (
                  <option key={ward.id} value={ward.id}>
                    {ward.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm font-medium" htmlFor="roster-date">
              {t("gapPage.day")}{" "}
              <input
                id="roster-date"
                type="date"
                min="2000-01-01"
                max="2999-12-31"
                value={date}
                onChange={(event) => {
                  setDateChoice(event.target.value);
                  setShiftChoice(null);
                }}
              />
            </label>
            <label className="block text-sm font-medium" htmlFor="shift">
              {t("common.shift")}{" "}
              <select
                id="shift"
                value={shiftId ?? ""}
                disabled={!shifts || shifts.length === 0}
                onChange={(event) => setShiftChoice(Number(event.target.value))}
              >
                {(shifts ?? []).map((shift) => (
                  <option key={shift.shift_id} value={shift.shift_id}>
                    {t("roster.shiftOptionTime", {
                      id: shift.shift_id,
                      from: formatDateTime(shift.start_at).slice(11, 16),
                      until: formatDateTime(shift.end_at).slice(11, 16),
                    })}
                  </option>
                ))}
              </select>
            </label>
          </form>
        </Card>
      )}
      {shiftsError && (
        <div className="mt-4">
          <Notice kind="error" role="alert">{describeError(shiftsError, t)}</Notice>
        </div>
      )}
      {shifts && shifts.length === 0 && <p className="mt-4">{t("gapPage.noShifts")}</p>}
      {shiftId !== null && <Roster key={`${actorId}-${shiftId}`} api={api} shiftId={shiftId} />}
    </main>
  );
}

export default function RosterRoute() {
  return (
    <Suspense>
      <RosterPage />
    </Suspense>
  );
}
