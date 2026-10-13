"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { DEMO_APPROVER_ID } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type { ApprovalDecisionResult, PendingApproval } from "@/lib/types/approval";
import type { CaseDetail } from "@/lib/types/case";

// The head nurse of the Golden Case (docs/workflow.md, section 10)
const api = createDemoApi(DEMO_APPROVER_ID);

// Same limit as the API (MAX_APPROVAL_REASON_LENGTH)
const MAX_REASON_LENGTH = 500;

/** A pending request with how many people its case still lacks. null: not known */
type Row = PendingApproval & { shortBy: number | null };

/** The list, plus one read per case for the people it still lacks. */
async function loadRows(signal: AbortSignal): Promise<Row[]> {
  const pending = await api<PendingApproval[]>("/approvals?pending=true", { signal });
  const caseIds = [...new Set(pending.map((row) => row.case_id))];
  const shortBy = new Map<number, number | null>(
    await Promise.all(
      caseIds.map(async (caseId): Promise<[number, number | null]> => {
        try {
          const detail = await api<CaseDetail>(`/cases/${caseId}`, { signal });
          return [
            caseId,
            detail.gap ? Math.max(detail.gap.headcount_gap - detail.assigned_count, 0) : null,
          ];
        } catch (cause) {
          if (signal.aborted) throw cause;
          // The list is still worth showing without this column
          return [caseId, null];
        }
      }),
    ),
  );
  return pending.map((row) => ({ ...row, shortBy: shortBy.get(row.case_id) ?? null }));
}

/** What makes a request the same one. An ID alone is reused after a demo reset */
function requestKey(row: PendingApproval): string {
  return [row.id, row.case_id, row.candidate_item_id, row.staff_id].join(":");
}

function shortByText(shortBy: number | null): string {
  if (shortBy === null) return "—";
  return shortBy === 0 ? "Headcount covered" : `Short by ${shortBy}`;
}

type Outcome =
  | { kind: "ok" | "error"; message: string }
  // HTTP 200 with case_status FAILED: the decision was saved, the execution was not (D11)
  | { kind: "failed"; approvalId: number; caseId: number };

export default function Approvals() {
  const load = useCallback((signal: AbortSignal) => loadRows(signal), []);
  const { data, error, isLoading } = usePolling(load);
  const [busy, setBusy] = useState(false);
  // Hidden until a fresh list no longer holds them
  const [decidedIds, setDecidedIds] = useState<number[]>([]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // The rejection reason being typed, tied to the request it was opened for
  const [draft, setDraft] = useState<{ key: string; reason: string } | null>(null);

  useEffect(() => {
    if (!data) return;
    // Forget an ID once the list confirms it is gone: a demo reset restarts the
    // sequence, so a new request can carry the ID of one decided earlier
    setDecidedIds((ids) => {
      const stillListed = ids.filter((id) => data.some((row) => row.id === id));
      return stillListed.length === ids.length ? ids : stillListed;
    });
  }, [data]);

  useEffect(() => {
    if (!data) return;
    // Drop the draft once a list no longer holds its request. A request that
    // took over the ID after a demo reset must not inherit the reason
    setDraft((current) =>
      current && !data.some((row) => requestKey(row) === current.key) ? null : current,
    );
  }, [data]);

  async function decide(approvalId: number, approved: boolean, rejectionReason?: string) {
    setBusy(true);
    setOutcome(null);
    try {
      const result = await api<ApprovalDecisionResult>(
        `/approvals/${approvalId}/decision`,
        {
          method: "POST",
          json: approved ? { approved } : { approved, reason: rejectionReason },
        },
      );
      setDecidedIds((ids) => [...ids, approvalId]);
      if (!approved) closeRejection();
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

  function closeRejection() {
    setDraft(null);
  }

  function submitRejection(event: FormEvent) {
    event.preventDefault();
    const trimmed = reason.trim();
    if (!rejecting || !trimmed) return;
    void decide(rejecting.id, false, trimmed);
  }

  const pending = (data ?? []).filter((row) => !decidedIds.includes(row.id));
  // By key, not by ID: the form never shows for a different request
  const rejecting = draft ? pending.find((row) => requestKey(row) === draft.key) : undefined;
  const reason = draft?.reason ?? "";
  const button = "rounded border px-2 py-1 disabled:opacity-50";

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Pending approvals</h1>
      <p className="mt-1 text-sm">Acting as staff {DEMO_APPROVER_ID}</p>

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
              <th>Case still needs</th>
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
                <td>{shortByText(row.shortBy)}</td>
                <td>{row.staff_id}</td>
                <td>{row.proposed_shift_id}</td>
                <td>{formatDateTime(row.requested_at)}</td>
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
                    // One reason at a time: Cancel first, so a typed reason is never lost
                    disabled={busy || rejecting !== undefined}
                    onClick={() => setDraft({ key: requestKey(row), reason: "" })}
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rejecting && (
        <form className="mt-4 max-w-xl" onSubmit={submitRejection}>
          <label className="block" htmlFor="rejection-reason">
            Reason for rejecting approval {rejecting.id} (staff {rejecting.staff_id}, case{" "}
            {rejecting.case_id})
          </label>
          <textarea
            id="rejection-reason"
            className="mt-1 w-full rounded border p-2"
            rows={3}
            maxLength={MAX_REASON_LENGTH}
            required
            value={reason}
            onChange={(event) =>
              setDraft((current) => current && { ...current, reason: event.target.value })
            }
          />
          <p className="text-sm">
            {reason.length} / {MAX_REASON_LENGTH}. The candidate sees this reason.
          </p>
          <div className="mt-2 flex gap-2">
            <button type="submit" className={button} disabled={busy || !reason.trim()}>
              Confirm rejection
            </button>
            <button type="button" className={button} disabled={busy} onClick={closeRejection}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </main>
  );
}
