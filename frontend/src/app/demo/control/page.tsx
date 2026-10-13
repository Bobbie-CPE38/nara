"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, apiRequest, createDemoApi } from "@/lib/api";
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
  | { kind: "error"; label: string; message: string };

function errorMessage(cause: unknown) {
  return cause instanceof ApiError
    ? `${cause.message} (HTTP ${cause.status})`
    : "Cannot reach the API. Check that the backend is running.";
}

function CaseLink({ id, status }: { id: number; status: string | null }) {
  return (
    <Link className="underline" href={`/cases/${id}`}>
      {id} ({status})
    </Link>
  );
}

export default function DemoControl() {
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

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

  const button = "rounded border px-3 py-2 text-left disabled:opacity-50";

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
                    <CaseLink id={window.case_id} status={window.case_status} />
                  )}
                </li>
              ))}
            </ul>
          )}
          {outcome.result.timed_out_outreach_ids.length > 0 && (
            <p>Offers timed out: {outcome.result.timed_out_outreach_ids.join(", ")}</p>
          )}
          {outcome.result.recovered_case_ids.length > 0 && (
            <p>
              Waiting cases rechecked:{" "}
              {outcome.result.recovered_case_ids.map((id, index) => (
                <span key={id}>
                  {index > 0 && ", "}
                  <Link className="underline" href={`/cases/${id}`}>
                    {id}
                  </Link>
                </span>
              ))}
            </p>
          )}
        </div>
      )}
      {outcome?.kind === "event" && (
        <dl className="mt-4 grid grid-cols-2 gap-2">
          <dt>Action</dt>
          <dd>{outcome.label}</dd>
          <dt>Event</dt>
          <dd>
            {outcome.result.event_id} ({outcome.result.event_status})
          </dd>
          <dt>Case</dt>
          <dd>
            {outcome.result.case_id !== null ? (
              <CaseLink id={outcome.result.case_id} status={outcome.result.case_status} />
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
