"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, apiRequest, createDemoApi } from "@/lib/api";
import type { EventResult } from "@/lib/types/event";

// Golden Case IDs (docs/workflow.md, section 10)
const LEAVES = [
  { label: "105 reports leave (shift 1)", staffId: 105, shiftId: 1 },
  { label: "203 reports leave (shift 2, no gap)", staffId: 203, shiftId: 2 },
];

type Outcome =
  | { kind: "reset"; clock: string }
  | { kind: "event"; label: string; result: EventResult }
  | { kind: "error"; label: string; message: string };

function errorMessage(cause: unknown) {
  return cause instanceof ApiError
    ? `${cause.message} (HTTP ${cause.status})`
    : "Cannot reach the API. Check that the backend is running.";
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

  const reportLeave = ({ label, staffId, shiftId }: (typeof LEAVES)[number]) =>
    run(label, async () => {
      const result = await createDemoApi(staffId)<EventResult>("/events", {
        method: "POST",
        json: { event_type: "STAFF_UNAVAILABLE", shift_id: shiftId },
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
        {LEAVES.map((leave) => (
          <button
            key={leave.staffId}
            type="button"
            className={button}
            disabled={busy}
            onClick={() => reportLeave(leave)}
          >
            {leave.label}
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
            {outcome.result.case_id === null ? (
              "No case opened"
            ) : (
              <Link className="underline" href={`/cases/${outcome.result.case_id}`}>
                {outcome.result.case_id} ({outcome.result.case_status})
              </Link>
            )}
          </dd>
        </dl>
      )}
    </main>
  );
}
