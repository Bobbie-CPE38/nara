"use client";

import Link from "next/link";
import { type FormEvent, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ActingAs } from "@/components/ActingAs";
import { useSessionUser } from "@/components/AuthProvider";
import { ScrollX } from "@/components/ScrollX";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { DEMO_APPROVERS, wardName } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type { MessageKey, Params, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
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

function wardsText(row: PendingApproval, t: Translate): string {
  return (row.wards ?? [])
    .map((ward) =>
      t("appr.wardLine", {
        ward: wardName(ward.ward_id),
        side: t(ward.side === "SOURCE" ? "appr.side.SOURCE" : "appr.side.DESTINATION"),
        status: t(ward.status === "APPROVED" ? "appr.status.APPROVED" : "appr.status.WAITING"),
      }),
    )
    .join("; ");
}

function shortByText(shortBy: number | null, t: Translate): string {
  if (shortBy === null) return "—";
  return shortBy === 0 ? t("appr.covered") : t("gap.shortBy", { count: shortBy });
}

/** A text of the page (a key and its values, in the language of the user) or the words of the API. */
type Message =
  | { key: MessageKey; params?: Params }
  | { failure: unknown }
  | { apiFailure: ApiError; id: number };

type Outcome =
  | { kind: "ok" | "error"; message: Message }
  // HTTP 200 with case_status FAILED: the decision was saved, the execution was not (D11)
  | { kind: "failed"; approvalId: number; caseId: number };

/** What the API answered, in words. Approved is not the same as assigned (workflow.md 9.6) */
function decisionMessage(result: ApprovalDecisionResult, t: Translate): Message {
  const failed = result.failed_rules ?? [];
  const rules = failed.length > 0 ? `: ${failed.join(", ")}` : "";
  const base = { id: result.approval_id, caseId: result.case_id, caseStatus: result.case_status };
  switch (result.outcome) {
    case "WAITING_OTHER_WARD":
      return { key: "appr.msg.waitingOther", params: { id: result.approval_id } };
    case "TRANSFER_CANCELLED":
      return {
        key: "appr.msg.transferCancelled",
        params: { ...base, reason: result.reason ?? t("appr.unknownReason"), rules },
      };
    case "REJECTED":
    case "ASSIGNED":
    case undefined:
      return {
        key: "appr.msg.decided",
        params: { ...base, verdict: t(result.is_approved ? "appr.approved" : "appr.rejected") },
      };
    default:
      // An outcome this page does not know is shown as it is
      return { key: "appr.msg.other", params: { ...base, outcome: result.outcome } };
  }
}

const AUTO_HISTORY_POLL_MS = 10_000;

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
  const t = useT();
  const load = useCallback((signal: AbortSignal) => loadAutoRows(api, signal), [api]);
  // History changes slowly, and each poll reads every case of up to 50 rows
  const { data, error } = usePolling(load, { intervalMs: AUTO_HISTORY_POLL_MS });
  return (
    <Card label={t("appr.auto.title")} title={t("appr.auto.title")} className="mt-6">
      <p className="mt-1 text-sm">{t("appr.auto.help")}</p>
      {error && <p className="mt-2 text-red-700">{describeError(error, t)}</p>}
      {data && data.length === 0 && <p className="mt-2">{t("appr.auto.none", { id: actorId })}</p>}
      {data && data.length > 0 && (
        <ScrollX>
          <table aria-label={t("appr.auto.title")} className="mt-2">
            <thead>
              <tr>
                <th>{t("common.id")}</th>
                <th>{t("common.case")}</th>
                <th>{t("common.staff")}</th>
                <th>{t("appr.col.wards")}</th>
                <th>{t("appr.auto.decidedAt")}</th>
                <th>{t("offers.col.caseStatus")}</th>
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
                  <td>{wardsText(row, t) || "—"}</td>
                  <td>{formatDateTime(row.decided_at)}</td>
                  <td className={row.caseStatus === "FAILED" ? "text-red-700" : undefined}>
                    {row.caseStatus === null
                      ? "—"
                      : row.caseStatus === "FAILED"
                        ? t("appr.auto.failed")
                        : row.caseStatus}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollX>
      )}
    </Card>
  );
}

function ApprovalsPage() {
  const t = useT();
  const [actorId, setActorId] = useActor();
  const me = useSessionUser();
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
          : { kind: "ok", message: decisionMessage(result, t) },
      );
    } catch (cause) {
      setOutcome({
        kind: "error",
        message: cause instanceof ApiError ? { apiFailure: cause, id: approvalId } : { failure: cause },
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
    // With a login the role says who the Supervisor is; the seeded ID is only the demo's way
    const isSupervisor = me ? me.role === "supervisor" : actorId === SUPERVISOR_ID;
    if (!isSupervisor || open.length < 2) return undefined;
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
    // A nurse who opens the page by its address is offered nothing (the Backend refuses as well)
    if (me && me.role === "staff") return false;
    const wardId = me
      ? me.role === "supervisor"
        ? null
        : me.home_ward_id
      : (DEMO_APPROVERS.find((approver) => approver.id === actorId)?.wardId ?? null);
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

  const text = (message: Message) => {
    if ("failure" in message) return describeError(message.failure, t);
    if ("apiFailure" in message) {
      const { apiFailure, id } = message;
      return t("appr.msg.apiError", { id, message: describeError(apiFailure, t), status: apiFailure.status });
    }
    return t(message.key, message.params);
  };
  const pending = (data ?? []).filter((row) => !decidedIds.includes(row.id));
  // By key, not by ID: the form never shows for a different request
  const rejecting = draft ? pending.find((row) => requestKey(row) === draft.key) : undefined;
  const reason = draft?.reason ?? "";

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("appr.title")}>
        <ActingAs
          id="acting-as"
          label="appr.actingAs"
          value={actorId}
          disabled={busy}
          onChange={changeActor}
        />
      </PageHeader>

      <div className="space-y-3">
        {error && <p className="text-red-700">{describeError(error, t)}</p>}
        {outcome?.kind === "ok" && <p className="font-medium text-green-700">{text(outcome.message)}</p>}
        {outcome?.kind === "error" && (
          <Notice kind="error" role="alert">
            {text(outcome.message)}
          </Notice>
        )}
        {outcome?.kind === "failed" && (
          <Notice kind="error" role="alert">
            {t("appr.failedBefore", { approval: outcome.approvalId, caseId: outcome.caseId })}{" "}
            <Link className="underline" href={`/cases/${outcome.caseId}`}>
              {t("appr.failedLink")}
            </Link>
            {t("appr.failedAfter")}
          </Notice>
        )}
      </div>
      {isLoading && <p className="mt-4">{t("common.loading")}</p>}
      {data && pending.length === 0 && <p className="mt-4">{t("appr.noPending")}</p>}
      {pending.length > 0 && (
        <Card className="mt-4">
          <ScrollX>
            <table>
              <thead>
                <tr>
                  <th>{t("common.id")}</th>
                  <th>{t("common.case")}</th>
                  <th>{t("appr.col.stillNeeds")}</th>
                  <th>{t("common.staff")}</th>
                  <th>{t("common.shift")}</th>
                  <th>{t("cand.homeWard")}</th>
                  <th>{t("cand.movedFrom")}</th>
                  <th>{t("appr.col.wards")}</th>
                  <th>{t("appr.col.requestedAt")}</th>
                  <th>{t("appr.col.decideBy")}</th>
                  <th>{t("appr.col.supervisorFrom")}</th>
                  <th>{t("appr.col.decision")}</th>
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
                    <td>{shortByText(row.shortBy, t)}</td>
                    <td>{row.staff_id}</td>
                    <td>{row.proposed_shift_id}</td>
                    <td>{row.home_ward_id == null ? "—" : wardName(row.home_ward_id)}</td>
                    <td>{row.source_ward_id == null ? "—" : wardName(row.source_ward_id)}</td>
                    <td>{wardsText(row, t) || "—"}</td>
                    <td>{formatDateTime(row.requested_at)}</td>
                    <td>{formatDateTime(row.expires_at)}</td>
                    <td>{row.supervisor_from ? formatDateTime(row.supervisor_from) : "—"}</td>
                    <td className="flex gap-2">
                      {sideFor(row) && (
                        <select
                          aria-label={t("appr.sideFor", { id: row.id })}
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
                              {side === "SOURCE" ? t("appr.sourceWard") : t("appr.destWard")}
                            </option>
                          ))}
                        </select>
                      )}
                      <Button
                        variant="primary"
                        disabled={busy || !canDecide(row)}
                        onClick={() => decide(row.id, true, undefined, sideFor(row))}
                      >
                        {t("appr.approve")}
                      </Button>
                      <Button
                        // One reason at a time: Cancel first, so a typed reason is never lost
                        disabled={busy || rejecting !== undefined || !canDecide(row)}
                        onClick={() => setDraft({ key: requestKey(row), reason: "" })}
                      >
                        {t("appr.reject")}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollX>
        </Card>
      )}
      {rejecting && (
        <Card className="mt-4">
          <form className="max-w-xl" onSubmit={submitRejection}>
            <label className="block" htmlFor="rejection-reason">
              {t("appr.rejectReason", { id: rejecting.id, staff: rejecting.staff_id, caseId: rejecting.case_id })}
            </label>
            <textarea
              id="rejection-reason"
              className="mt-1 w-full"
              rows={3}
              maxLength={MAX_REASON_LENGTH}
              required
              value={reason}
              onChange={(event) =>
                setDraft((current) => current && { ...current, reason: event.target.value })
              }
            />
            <p className="text-sm">
              {t("appr.counterNote", { count: reason.length, max: MAX_REASON_LENGTH })}
            </p>
            <div className="mt-2 flex gap-2">
              <Button type="submit" variant="primary" disabled={busy || !reason.trim()}>
                {t("appr.confirmReject")}
              </Button>
              <Button disabled={busy} onClick={closeRejection}>
                {t("common.cancel")}
              </Button>
            </div>
          </form>
        </Card>
      )}
      <AutoHistory key={actorId} api={api} actorId={actorId} />
    </main>
  );
}

export default function Approvals() {
  return (
    <Suspense>
      <ApprovalsPage />
    </Suspense>
  );
}
