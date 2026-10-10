"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import type { ApprovalDecisionResult, PendingApproval } from "@/lib/types/approval";

// The head nurse of the Golden Case (docs/workflow.md, section 10)
const APPROVER_ID = 900;
const api = createDemoApi(APPROVER_ID);

type Outcome =
  | { kind: "ok" | "error"; message: string }
  // HTTP 200 with case_status FAILED: the decision was saved, the execution was not (D11)
  | { kind: "failed"; approvalId: number; caseId: number };

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
  // Hidden until a fresh list no longer holds them
  const [decidedIds, setDecidedIds] = useState<number[]>([]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => {
    if (!data) return;
    // Forget an ID once the list confirms it is gone: a demo reset restarts the
    // sequence, so a new request can carry the ID of one decided earlier
    setDecidedIds((ids) => {
      const stillListed = ids.filter((id) => data.some((row) => row.id === id));
      return stillListed.length === ids.length ? ids : stillListed;
    });
  }, [data]);

  async function decide(approvalId: number, approved: boolean) {
    setBusy(true);
    setOutcome(null);
    try {
      const result = await api<ApprovalDecisionResult>(
        `/approvals/${approvalId}/decision`,
        { method: "POST", json: { approved } },
      );
      setDecidedIds((ids) => [...ids, approvalId]);
      setOutcome(
        result.case_status === "FAILED"
          ? { kind: "failed", approvalId: result.approval_id, caseId: result.case_id }
          : {
              kind: "ok",
              message: `Approval ${result.approval_id} ${
                result.is_approved ? "approved" : "rejected"
              }. Case ${result.case_id}: ${result.case_status}`,
            },
      );
    } catch (cause) {
      setOutcome({
        kind: "error",
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
      {outcome?.kind === "ok" && <p className="mt-4 text-green-700">{outcome.message}</p>}
      {outcome?.kind === "error" && (
        <p role="alert" className="mt-4 text-red-700">
          {outcome.message}
        </p>
      )}
      {outcome?.kind === "failed" && (
        <p role="alert" className="mt-4 text-red-700">
          Approval {outcome.approvalId} was saved, but case {outcome.caseId} failed during
          execution. Check the{" "}
          <Link className="underline" href={`/cases/${outcome.caseId}`}>
            case timeline
          </Link>
          .
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
