"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import type { ApprovalDecisionResult, PendingApproval } from "@/lib/types/approval";

// The head nurse of the Golden Case (docs/workflow.md, section 10)
const APPROVER_ID = 900;
const api = createDemoApi(APPROVER_ID);

type Outcome = { ok: boolean; message: string };

function formatTime(value: string) {
  return new Date(value).toLocaleString("en-GB", { timeZone: "Asia/Bangkok" });
}

export default function Approvals() {
  const load = useCallback(
    (signal: AbortSignal) =>
      api<PendingApproval[]>("/approvals?pending=true", { signal }),
    [],
  );
  const { data, error, isLoading } = usePolling(load);
  const [busy, setBusy] = useState(false);
  // Hidden until the next poll drops them from the list
  const [decidedIds, setDecidedIds] = useState<number[]>([]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  async function decide(approvalId: number, approved: boolean) {
    setBusy(true);
    setOutcome(null);
    try {
      const result = await api<ApprovalDecisionResult>(
        `/approvals/${approvalId}/decision`,
        { method: "POST", json: { approved } },
      );
      setDecidedIds((ids) => [...ids, approvalId]);
      setOutcome({
        ok: true,
        message: `Approval ${result.approval_id} ${
          result.is_approved ? "approved" : "rejected"
        }. Case ${result.case_id}: ${result.case_status}`,
      });
    } catch (cause) {
      setOutcome({
        ok: false,
        message:
          cause instanceof ApiError
            ? `Approval ${approvalId}: ${cause.message} (HTTP ${cause.status})`
            : "Cannot reach the API. Check that the backend is running.",
      });
    } finally {
      setBusy(false);
    }
  }

  const pending = (data ?? []).filter((row) => !decidedIds.includes(row.id));
  const button = "rounded border px-2 py-1 disabled:opacity-50";

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Pending approvals</h1>
      <p className="mt-1 text-sm">Acting as staff {APPROVER_ID}</p>

      {error && <p className="mt-4 text-red-700">{error.message}</p>}
      {outcome && (
        <p className={`mt-4 ${outcome.ok ? "text-green-700" : "text-red-700"}`}>
          {outcome.message}
        </p>
      )}
      {isLoading && <p className="mt-4">Loading…</p>}
      {data && pending.length === 0 && <p className="mt-4">No pending approvals.</p>}
      {pending.length > 0 && (
        <table className="mt-4 w-full text-left">
          <thead>
            <tr>
              <th>ID</th>
              <th>Case</th>
              <th>Staff</th>
              <th>Shift</th>
              <th>Requested at</th>
              <th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {pending.map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>
                  <Link className="underline" href={`/cases/${row.case_id}`}>
                    {row.case_id}
                  </Link>
                </td>
                <td>{row.staff_id}</td>
                <td>{row.proposed_shift_id}</td>
                <td>{formatTime(row.requested_at)}</td>
                <td className="flex gap-2">
                  <button
                    type="button"
                    className={button}
                    disabled={busy}
                    onClick={() => decide(row.id, true)}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className={button}
                    disabled={busy}
                    onClick={() => decide(row.id, false)}
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
