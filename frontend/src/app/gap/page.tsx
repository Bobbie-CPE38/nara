"use client";

import Link from "next/link";
import { Suspense, useCallback, useMemo, useState } from "react";
import { ActingAs } from "@/components/ActingAs";
import { GapIntervals } from "@/components/case/GapTable";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { wardName } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type { Dashboard, GapShiftDetail, GapShiftSummary } from "@/lib/types/dashboard";

/** The API's own words for a refused read (403 ward, 404 shift, 409 not set up). */
function errorText(cause: Error): string {
  return cause instanceof ApiError ? `${cause.message} (HTTP ${cause.status})` : cause.message;
}

/** Read-only: this page never creates an event or a case; that stays in Demo control (R6-Q17). */
function ShiftDetail({ detail }: { detail: GapShiftDetail }) {
  return (
    <section aria-label="Shift gap" className="mt-6">
      <h2 className="text-xl font-semibold">
        Shift {detail.shift_id}, {wardName(detail.ward_id)}
      </h2>
      <p className="mt-1 text-sm">
        {formatDateTime(detail.start_at)} to {formatDateTime(detail.end_at)}
        {detail.evaluated_from && detail.evaluated_from !== detail.start_at && (
          <> · Measured from {formatDateTime(detail.evaluated_from)}, the part still to come</>
        )}
      </p>
      <p className="mt-1">
        {detail.case_id === null ? (
          "No running case on this shift."
        ) : (
          <Link className="underline" href={`/cases/${detail.case_id}`}>
            Open case {detail.case_id}
          </Link>
        )}
      </p>
      <GapIntervals intervals={detail.intervals} />
      <h3 className="mt-4 font-semibold">Roster</h3>
      {detail.roster.length === 0 ? (
        <p className="mt-1">Nobody is on this shift&apos;s roster.</p>
      ) : (
        <table aria-label="Roster" className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th className="py-1 pr-4">Staff</th>
              <th className="py-1 pr-4">Name</th>
              <th className="py-1 pr-4">Status</th>
              <th className="py-1 pr-4">From</th>
              <th className="py-1 pr-4">Until</th>
              <th className="py-1 pr-4">On leave</th>
              <th className="py-1 pr-4">Checked in</th>
            </tr>
          </thead>
          <tbody>
            {detail.roster.map((row) => (
              <tr key={row.roster_assignment_id}>
                <td className="py-1 pr-4">{row.staff_id}</td>
                <td className="py-1 pr-4">{row.name}</td>
                <td className={`py-1 pr-4 ${row.status === "CANCELLED" ? "text-gray-500" : ""}`}>
                  {row.status}
                </td>
                <td className="py-1 pr-4">{formatDateTime(row.effective_start_at)}</td>
                <td className="py-1 pr-4">{formatDateTime(row.effective_end_at)}</td>
                <td className={`py-1 pr-4 ${row.on_leave ? "text-amber-700" : ""}`}>
                  {row.on_leave ? "Yes" : "No"}
                </td>
                <td className="py-1 pr-4">{row.checked_in ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function GapCheckPage() {
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
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Gap check</h1>
      <p className="mt-1 text-sm">
        Look at the gap of any shift, with or without a case. This page only reads: it creates no
        event and no case. Use Demo control for that.
      </p>
      <div className="mt-2">
        <ActingAs id="gap-viewing-as" value={actorId} onChange={changeActor} />
      </div>

      {wardsError && <p role="alert" className="mt-4 text-red-700">{errorText(wardsError)}</p>}
      {!dashboard && !wardsError && <p className="mt-4">Loading…</p>}
      {dashboard && (
        <form className="mt-4 flex flex-wrap items-end gap-4" onSubmit={(event) => event.preventDefault()}>
          <label className="block text-sm" htmlFor="gap-ward">
            Ward{" "}
            <select
              id="gap-ward"
              className="rounded border px-1"
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
          <label className="block text-sm" htmlFor="gap-date">
            Day the shift starts{" "}
            <input
              id="gap-date"
              type="date"
              className="rounded border px-1"
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
      )}

      {shiftsError && <p role="alert" className="mt-4 text-red-700">{errorText(shiftsError)}</p>}
      {canList && !shifts && !shiftsError && <p className="mt-4">Loading shifts…</p>}
      {shifts && shifts.length === 0 && <p className="mt-4">No shift starts on this day in this ward.</p>}
      {shifts && shifts.length > 0 && (
        <table aria-label="Shifts of the day" className="mt-4 w-full text-left">
          <thead>
            <tr>
              <th className="py-1 pr-4">Shift</th>
              <th className="py-1 pr-4">From</th>
              <th className="py-1 pr-4">Until</th>
              <th className="py-1 pr-4">Required</th>
              <th className="py-1 pr-4">On roster</th>
              <th className="py-1 pr-4">Short by</th>
              <th className="py-1 pr-4">Case</th>
              <th className="py-1 pr-4" />
            </tr>
          </thead>
          <tbody>
            {shifts.map((row) => (
              <tr key={row.shift_id}>
                <td className="py-1 pr-4">{row.shift_id}</td>
                <td className="py-1 pr-4">{formatDateTime(row.start_at)}</td>
                <td className="py-1 pr-4">{formatDateTime(row.end_at)}</td>
                <td className="py-1 pr-4">{row.required_staff}</td>
                <td className="py-1 pr-4">{row.rostered_count}</td>
                <td className={`py-1 pr-4 ${row.headcount_gap > 0 ? "text-red-700" : "text-green-700"}`}>
                  {row.headcount_gap > 0 ? row.headcount_gap : "OK"}
                </td>
                <td className="py-1 pr-4">
                  {row.case_id === null ? (
                    "—"
                  ) : (
                    <Link className="underline" href={`/cases/${row.case_id}`}>
                      {row.case_id}
                    </Link>
                  )}
                </td>
                <td className="py-1 pr-4">
                  <button
                    type="button"
                    className="rounded border px-2 py-1"
                    aria-pressed={shiftId === row.shift_id}
                    onClick={() => setShiftId(row.shift_id)}
                  >
                    Check shift {row.shift_id}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {detailError && <p role="alert" className="mt-4 text-red-700">{errorText(detailError)}</p>}
      {shiftId !== null && !detail && !detailError && <p className="mt-4">Loading shift…</p>}
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
