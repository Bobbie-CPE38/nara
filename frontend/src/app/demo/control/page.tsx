"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, apiRequest, createDemoApi } from "@/lib/api";
import { TERMINAL_CASE_STATUSES } from "@/lib/constants";
import { DEMO_WARDS } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type { CheckInResult } from "@/lib/types/attendance";
import type { ClockAdvanceResult, EventResult } from "@/lib/types/event";

// Golden Case IDs (docs/workflow.md, section 10). 900 is the head nurse, the
// only one who may report the last three event types (section 3.4)
const EVENTS = [
  {
    label: "105 reports leave (shift 1)",
    staffId: 105,
    json: { event_type: "STAFF_UNAVAILABLE", shift_id: 1 },
  },
  {
    label: "203 reports leave (shift 2, no gap)",
    staffId: 203,
    json: { event_type: "STAFF_UNAVAILABLE", shift_id: 2 },
  },
  {
    label: "900 cancels the assignment of 104 (shift 1)",
    staffId: 900,
    json: {
      event_type: "ASSIGNMENT_CANCELLED",
      shift_id: 1,
      staff_id: 104,
      reason: "Cancelled from demo control",
    },
  },
  {
    label: "900 reports 12 patients (shift 1)",
    staffId: 900,
    json: { event_type: "PATIENT_SURGE", shift_id: 1, patient_count: 12 },
  },
  {
    label: "900 requires 3 ICU nurses (shift 1)",
    staffId: 900,
    json: {
      event_type: "REQUIREMENT_CHANGED",
      shift_id: 1,
      skills: [{ skill_id: 1, required_count: 3 }],
    },
  },
];

// Moving the frozen demo clock also runs what became due, like the job does with
// real time (section 3.8): offers time out after 300 seconds, waiting cases are
// rechecked and merge windows close
const ADVANCE = { label: "Advance clock 10 minutes", seconds: 600 };

type Outcome =
  | { kind: "reset"; clock: string }
  | { kind: "clock"; result: ClockAdvanceResult }
  | { kind: "event"; label: string; result: EventResult }
  | { kind: "checkIn"; label: string; result: CheckInResult }
  | { kind: "error"; label: string; message: string };

function errorMessage(cause: unknown) {
  return cause instanceof ApiError
    ? `${cause.message} (HTTP ${cause.status})`
    : "Cannot reach the API. Check that the backend is running.";
}

function CaseLink({ id, status }: { id: number; status: string | null }) {
  const load = useCallback(
    async (signal: AbortSignal) => {
      const result = await apiRequest<{ id: number; status: string }>(
        `/cases/${id}`,
        { signal },
      );
      if (!result || result.id !== id || typeof result.status !== "string") {
        throw new Error("Invalid case status response");
      }
      return result;
    },
    [id],
  );
  const { data, error, isLoading, refresh } = usePolling(load, {
    stopOnData: (result) => TERMINAL_CASE_STATUSES.has(result.status),
    stopOnError: (cause) => cause instanceof ApiError && cause.status === 404,
  });
  const missing = error instanceof ApiError && error.status === 404;
  const latest = data?.status ?? status;
  return (
    <span>
      <Link className="underline" href={`/cases/${id}`}>
        {id}
        {!missing && latest !== null ? ` (${latest})` : ""}
      </Link>
      {missing ? (
        <span role="status"> — Case no longer exists. It may have been reset.</span>
      ) : error ? (
        <span role="status"> — Status may be outdated: {errorMessage(error)}</span>
      ) : (
        <span className="text-sm text-gray-500">
          {isLoading
            ? " — Checking current status…"
            : latest !== null && TERMINAL_CASE_STATUSES.has(latest)
              ? " — Final status. Updates stopped."
              : " — Updating every 2 seconds."}
        </span>
      )}
      {!missing && (
        <button type="button" className="ml-2 underline" onClick={() => void refresh()}>
          Refresh case {id}
        </button>
      )}
    </span>
  );
}

export default function DemoControl() {
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // A leave on any seeded ward and shift (docs/workflow.md 9.6, round 4 PR U)
  const [wardId, setWardId] = useState<number>(DEMO_WARDS[0].id);
  const ward = DEMO_WARDS.find((item) => item.id === wardId) ?? DEMO_WARDS[0];
  const [shiftId, setShiftId] = useState<number>(ward.shifts[0].id);
  const shift = ward.shifts.find((item) => item.id === shiftId) ?? ward.shifts[0];
  const [staffId, setStaffId] = useState<number>(shift.staffIds[0]);
  const leaveStaffId = shift.staffIds.includes(staffId) ? staffId : shift.staffIds[0];

  function pickWard(id: number) {
    const next = DEMO_WARDS.find((item) => item.id === id) ?? DEMO_WARDS[0];
    setWardId(next.id);
    setShiftId(next.shifts[0].id);
    setStaffId(next.shifts[0].staffIds[0]);
  }

  function pickShift(id: number) {
    const next = ward.shifts.find((item) => item.id === id) ?? ward.shifts[0];
    setShiftId(next.id);
    setStaffId(next.staffIds[0]);
  }

  async function run(label: string, action: () => Promise<Outcome>) {
    setBusy(true);
    setOutcome(null);
    try {
      setOutcome(await action());
    } catch (cause) {
      setOutcome({ kind: "error", label, message: errorMessage(cause) });
    } finally {
      setBusy(false);
    }
  }

  const reset = () =>
    run("Reset demo", async () => {
      const { clock } = await apiRequest<{ status: string; clock: string }>(
        "/demo/reset",
        { method: "POST" },
      );
      return { kind: "reset", clock };
    });

  const advanceClock = () =>
    run(ADVANCE.label, async () => {
      const result = await apiRequest<ClockAdvanceResult>("/demo/clock/advance", {
        method: "POST",
        json: { seconds: ADVANCE.seconds },
      });
      return { kind: "clock", result };
    });

  const reportEvent = ({ label, staffId, json }: (typeof EVENTS)[number]) =>
    run(label, async () => {
      const result = await createDemoApi(staffId)<EventResult>("/events", {
        method: "POST",
        json,
      });
      return { kind: "event", label, result };
    });

  const reportLeave = () =>
    reportEvent({
      label: `${leaveStaffId} reports leave (${ward.name}, shift ${shift.id})`,
      staffId: leaveStaffId,
      json: { event_type: "STAFF_UNAVAILABLE", shift_id: shift.id },
    });

  // Not the nurse's own check-in: the demo plays a character arriving (R5-Q23)
  const simulateCheckIn = () => {
    const label = `Simulated check-in of ${leaveStaffId} (${ward.name}, shift ${shift.id})`;
    return run(label, async () => {
      const result = await apiRequest<CheckInResult>("/demo/attendance/check-in", {
        method: "POST",
        json: { staff_id: leaveStaffId, shift_id: shift.id },
      });
      return { kind: "checkIn", label, result };
    });
  };

  const button = "rounded border px-3 py-2 text-left disabled:opacity-50";
  const select = "rounded border px-1";

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-2xl font-semibold">Demo control</h1>
      <div className="mt-4 flex flex-col gap-2">
        <button type="button" className={button} disabled={busy} onClick={reset}>
          Reset demo
        </button>
        <button type="button" className={button} disabled={busy} onClick={advanceClock}>
          {ADVANCE.label}
        </button>
        {EVENTS.map((event) => (
          <button
            key={event.label}
            type="button"
            className={button}
            disabled={busy}
            onClick={() => reportEvent(event)}
          >
            {event.label}
          </button>
        ))}
      </div>

      <fieldset className="mt-6 flex flex-col gap-2 rounded border p-3">
        <legend className="px-1">Report leave or simulate a check-in on any ward</legend>
        <label htmlFor="leave-ward">
          Ward{" "}
          <select
            id="leave-ward"
            className={select}
            value={ward.id}
            disabled={busy}
            onChange={(event) => pickWard(Number(event.target.value))}
          >
            {DEMO_WARDS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="leave-shift">
          Shift{" "}
          <select
            id="leave-shift"
            className={select}
            value={shift.id}
            disabled={busy}
            onChange={(event) => pickShift(Number(event.target.value))}
          >
            {ward.shifts.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="leave-staff">
          Staff on the shift{" "}
          <select
            id="leave-staff"
            className={select}
            value={leaveStaffId}
            disabled={busy}
            onChange={(event) => setStaffId(Number(event.target.value))}
          >
            {shift.staffIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={button} disabled={busy} onClick={reportLeave}>
          Report leave
        </button>
        <button type="button" className={button} disabled={busy} onClick={simulateCheckIn}>
          Simulate check-in (demo)
        </button>
      </fieldset>

      {busy && <p className="mt-4">Working…</p>}
      {outcome?.kind === "reset" && (
        <p className="mt-4 text-green-700">Demo reset. Clock: {outcome.clock}</p>
      )}
      {outcome?.kind === "error" && (
        <p className="mt-4 text-red-700">
          {outcome.label}: {outcome.message}
        </p>
      )}
      {outcome?.kind === "clock" && (
        <div className="mt-4">
          <p className="text-green-700">Clock: {outcome.result.clock}</p>
          {outcome.result.closed_windows.length === 0 ? (
            <p>No merge window was due.</p>
          ) : (
            <ul className="list-disc pl-5">
              {outcome.result.closed_windows.map((window) => (
                <li key={window.shift_id}>
                  Shift {window.shift_id}, events {window.event_ids.join(", ")}:{" "}
                  {window.case_id === null ? (
                    "no case opened"
                  ) : (
                    <CaseLink
                      key={window.case_id}
                      id={window.case_id}
                      status={window.case_status}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
          {outcome.result.timed_out_approval_request_ids.length > 0 && (
            <p>Approvals timed out: {outcome.result.timed_out_approval_request_ids.join(", ")}</p>
          )}
          {outcome.result.timed_out_outreach_ids.length > 0 && (
            <p>Offers timed out: {outcome.result.timed_out_outreach_ids.join(", ")}</p>
          )}
          {(outcome.result.no_show_event_ids ?? []).length > 0 && (
            <p>No-show events recorded: {outcome.result.no_show_event_ids.join(", ")}</p>
          )}
          {outcome.result.recovered_case_ids.length > 0 && (
            <p>
              Waiting cases rechecked:{" "}
              {outcome.result.recovered_case_ids.map((id, index) => (
                <span key={id}>
                  {index > 0 && ", "}
                  <CaseLink id={id} status={null} />
                </span>
              ))}
            </p>
          )}
        </div>
      )}
      {outcome?.kind === "checkIn" && (
        <p className={outcome.result.on_time ? "mt-4 text-green-700" : "mt-4 text-amber-700"}>
          {outcome.label}: {outcome.result.on_time ? "on time" : "late"} at{" "}
          {formatDateTime(outcome.result.check_in_at)} (deadline{" "}
          {formatDateTime(outcome.result.deadline)})
        </p>
      )}
      {outcome?.kind === "event" && (
        <dl className="mt-4 grid grid-cols-2 gap-2">
          <dt>Action</dt>
          <dd>{outcome.label}</dd>
          <dt>Event</dt>
          <dd>
            {outcome.result.event_id} ({outcome.result.event_status})
          </dd>
          <dt>Case status at event response</dt>
          <dd>{outcome.result.case_status ?? "No case yet"}</dd>
          <dt>Case (current status)</dt>
          <dd>
            {outcome.result.case_id !== null ? (
              <CaseLink
                key={outcome.result.case_id}
                id={outcome.result.case_id}
                status={outcome.result.case_status}
              />
            ) : outcome.result.event_status === "RECEIVED" ? (
              // Its shift has an open merge window, or a case that is still running
              "Not decided yet. The event is waiting."
            ) : (
              "No case opened"
            )}
          </dd>
        </dl>
      )}
    </main>
  );
}
