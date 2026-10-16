"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { DEMO_APPROVER_ID, DEMO_APPROVERS, wardName } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type {
  ApprovalDecisionResult,
  ApprovalSide,
  AutoApprovedApproval,
  PendingApproval,
} from "@/lib/types/approval";
import type { CaseDetail } from "@/lib/types/case";

type Api = ReturnType<typeof createDemoApi>;

// The Supervisor decides for any ward once supervisor_from has passed (workflow.md 6.21)
const SUPERVISOR_ID = 950;

// Same limit as the API (MAX_APPROVAL_REASON_LENGTH)
const MAX_REASON_LENGTH = 500;

/** A pending request with how many people its case still lacks. null: not known */
type Row = PendingApproval & { shortBy: number | null };

/** The list, plus one read per case for the people it still lacks. */
async function loadRows(api: Api, signal: AbortSignal): Promise<Row[]> {
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

/** The sides still waiting for a decision. */
function pendingSides(row: PendingApproval): ApprovalSide[] {
  return (row.wards ?? []).filter((ward) => ward.status === "PENDING").map((ward) => ward.side);
}

function wardsText(row: PendingApproval): string {
  return (row.wards ?? [])
    .map(
      (ward) =>
        `${wardName(ward.ward_id)} (${ward.side === "SOURCE" ? "source" : "destination"}): ${
          ward.status === "APPROVED" ? "approved" : "waiting"
        }`,
    )
    .join("; ");
}

function shortByText(shortBy: number | null): string {
  if (shortBy === null) return "—";
  return shortBy === 0 ? "Headcount covered" : `Short by ${shortBy}`;
}

type Outcome =
  | { kind: "ok" | "error"; message: string }
  // HTTP 200 with case_status FAILED: the decision was saved, the execution was not (D11)
  | { kind: "failed"; approvalId: number; caseId: number };

/** What the API answered, in words. Approved is not the same as assigned (workflow.md 9.6) */
function decisionMessage(result: ApprovalDecisionResult): string {
  const head = `Approval ${result.approval_id}`;
  const failed = result.failed_rules ?? [];
  const rules = failed.length > 0 ? `: ${failed.join(", ")}` : "";
  switch (result.outcome) {
    case "WAITING_OTHER_WARD":
      return `${head}: ward approved; waiting for the other ward.`;
    case "TRANSFER_CANCELLED":
      return `${head}: approved, but the transfer was cancelled (${
        result.reason ?? "unknown reason"
      }${rules}). Case ${result.case_id}: ${result.case_status}.`;
    case "REJECTED":
    case "ASSIGNED":
    case undefined:
      return `${head} ${result.is_approved ? "approved" : "rejected"}. Case ${result.case_id}: ${
        result.case_status
      }`;
    default:
      // An outcome this page does not know is shown as it is
      return `${head}: ${result.outcome}. Case ${result.case_id}: ${result.case_status}`;
  }
}

/** An auto-approved request with the current status of its case. null: not known */
type AutoRow = AutoApprovedApproval & { caseStatus: string | null };

/** The history, plus one read per case: approved is not assigned (workflow.md 9.6, D11). */
async function loadAutoRows(api: Api, signal: AbortSignal): Promise<AutoRow[]> {
  const history = await api<AutoApprovedApproval[]>("/approvals/auto", { signal });
  const caseIds = [...new Set(history.map((row) => row.case_id))];
  const statuses = new Map<number, string | null>(
    await Promise.all(
      caseIds.map(async (caseId): Promise<[number, string | null]> => {
        try {
          return [caseId, (await api<CaseDetail>(`/cases/${caseId}`, { signal })).status];
        } catch (cause) {
          if (signal.aborted) throw cause;
          // The history is still worth showing without this column
          return [caseId, null];
        }
      }),
    ),
  );
  return history.map((row) => ({ ...row, caseStatus: statuses.get(row.case_id) ?? null }));
}

/** Requests the system approved for the caller's wards, newest first (GET /approvals/auto). */
function AutoHistory({ api, actorId }: { api: Api; actorId: number }) {
  const load = useCallback((signal: AbortSignal) => loadAutoRows(api, signal), [api]);
  const { data, error } = usePolling(load);
  return (
    <section aria-label="Approved by the system" className="mt-8">
      <h2 className="text-xl font-semibold">Approved by the system</h2>
      <p className="mt-1 text-sm">
        Auto-approval runs when a ward&apos;s queue is too long. Approved does not mean assigned:
        check the case status.
      </p>
      {error && <p className="mt-2 text-red-700">{error.message}</p>}
      {data && data.length === 0 && <p className="mt-2">None for staff {actorId}.</p>}
      {data && data.length > 0 && (
        <table aria-label="Approved by the system" className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th>ID</th>
              <th>Case</th>
              <th>Staff</th>
              <th>Wards</th>
              <th>Decided at</th>
              <th>Case status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>
                  <Link className="underline" href={`/cases/${row.case_id}`}>
                    {row.case_id}
                  </Link>
                </td>
                <td>{row.staff_id}</td>
                <td>{wardsText(row) || "—"}</td>
                <td>{formatDateTime(row.decided_at)}</td>
                <td className={row.caseStatus === "FAILED" ? "text-red-700" : undefined}>
                  {row.caseStatus === null
                    ? "—"
                    : row.caseStatus === "FAILED"
                      ? "FAILED: approved, but the assignment was not made"
                      : row.caseStatus}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default function Approvals() {
  const [actorId, setActorId] = useState<number>(DEMO_APPROVER_ID);
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  const load = useCallback((signal: AbortSignal) => loadRows(api, signal), [api]);
  const { data, error, isLoading } = usePolling(load);
  // The side the Supervisor picked, per request key, when more than one ward waits
  const [sides, setSides] = useState<Record<string, ApprovalSide>>({});
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

  async function decide(
    approvalId: number,
    approved: boolean,
    rejectionReason?: string,
    side?: ApprovalSide,
  ) {
    setBusy(true);
    setOutcome(null);
    try {
      const result = await api<ApprovalDecisionResult>(
        `/approvals/${approvalId}/decision`,
        {
          method: "POST",
          json: {
            approved,
            ...(approved ? {} : { reason: rejectionReason }),
            ...(side ? { side } : {}),
          },
        },
      );
      // A partly approved request stays listed: the other ward still decides
      if (result.outcome !== "WAITING_OTHER_WARD") setDecidedIds((ids) => [...ids, approvalId]);
      if (!approved) closeRejection();
      setOutcome(
        result.outcome === "EXECUTION_FAILED" || result.case_status === "FAILED"
          ? { kind: "failed", approvalId: result.approval_id, caseId: result.case_id }
          : { kind: "ok", message: decisionMessage(result) },
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
    void decide(rejecting.id, false, trimmed, sideFor(rejecting));
  }

  /** The side to send: only the Supervisor with more than one waiting ward picks one */
  function sideFor(row: PendingApproval): ApprovalSide | undefined {
    const open = pendingSides(row);
    if (actorId !== SUPERVISOR_ID || open.length < 2) return undefined;
    // A side another approver decided since the pick is no longer offered
    const picked = sides[requestKey(row)];
    return picked && open.includes(picked) ? picked : open[0];
  }

  /**
   * A head nurse decides only a side of their own ward that still waits. The list
   * holds every ward's requests, so the others show without buttons. The page does
   * not know the backend clock, so the Supervisor's buttons stay enabled and the API
   * answers 403 before supervisor_from (workflow.md 6.21).
   */
  function canDecide(row: PendingApproval): boolean {
    const wardId = DEMO_APPROVERS.find((approver) => approver.id === actorId)?.wardId ?? null;
    if (wardId === null || row.wards === undefined) return true;
    return row.wards.some((ward) => ward.status === "PENDING" && ward.ward_id === wardId);
  }

  function changeActor(id: number) {
    setActorId(id);
    setDecidedIds([]);
    setSides({});
    setDraft(null);
    setOutcome(null);
  }

  const pending = (data ?? []).filter((row) => !decidedIds.includes(row.id));
  // By key, not by ID: the form never shows for a different request
  const rejecting = draft ? pending.find((row) => requestKey(row) === draft.key) : undefined;
  const reason = draft?.reason ?? "";
  const button = "rounded border px-2 py-1 disabled:opacity-50";

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Pending approvals</h1>
      <label className="mt-1 block text-sm" htmlFor="acting-as">
        Acting as{" "}
        <select
          id="acting-as"
          className="rounded border px-1"
          value={actorId}
          disabled={busy}
          onChange={(event) => changeActor(Number(event.target.value))}
        >
          {DEMO_APPROVERS.map((approver) => (
            <option key={approver.id} value={approver.id}>
              {approver.label}
            </option>
          ))}
        </select>
      </label>

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
              <th>Home ward</th>
              <th>Moved from</th>
              <th>Wards</th>
              <th>Requested at</th>
              <th>Decide by</th>
              <th>Supervisor from</th>
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
                <td>{row.home_ward_id == null ? "—" : wardName(row.home_ward_id)}</td>
                <td>{row.source_ward_id == null ? "—" : wardName(row.source_ward_id)}</td>
                <td>{wardsText(row) || "—"}</td>
                <td>{formatDateTime(row.requested_at)}</td>
                <td>{formatDateTime(row.expires_at)}</td>
                <td>{row.supervisor_from ? formatDateTime(row.supervisor_from) : "—"}</td>
                <td className="flex gap-2">
                  {sideFor(row) && (
                    <select
                      aria-label={`Side for approval ${row.id}`}
                      className="rounded border px-1"
                      disabled={busy}
                      value={sideFor(row)}
                      onChange={(event) =>
                        setSides((current) => ({
                          ...current,
                          [requestKey(row)]: event.target.value as ApprovalSide,
                        }))
                      }
                    >
                      {pendingSides(row).map((side) => (
                        <option key={side} value={side}>
                          {side === "SOURCE" ? "Source ward" : "Destination ward"}
                        </option>
                      ))}
                    </select>
                  )}
                  <button
                    type="button"
                    className={button}
                    disabled={busy || !canDecide(row)}
                    onClick={() => decide(row.id, true, undefined, sideFor(row))}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className={button}
                    // One reason at a time: Cancel first, so a typed reason is never lost
                    disabled={busy || rejecting !== undefined || !canDecide(row)}
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
      <AutoHistory key={actorId} api={api} actorId={actorId} />
    </main>
  );
}
