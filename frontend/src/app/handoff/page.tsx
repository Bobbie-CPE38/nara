"use client";

import Link from "next/link";
import { type FormEvent, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { ActingAs } from "@/components/ActingAs";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { SKIP_REASON_INFO } from "@/lib/constants";
import { formatDateTime } from "@/lib/format";
import type {
  CloseCaseResult,
  HandoffCandidate,
  HandoffCase,
  HandoffConflict,
  ManualAssignmentResult,
} from "@/lib/types/handoff";

// Same limit as the API (R2-Q20)
const MAX_REASON_LENGTH = 500;

function shortByText(row: HandoffCase): string {
  if (row.headcount_gap === null) return "—";
  return String(Math.max(row.headcount_gap - row.assigned_count, 0));
}

function ruleText(code: string): string {
  return SKIP_REASON_INFO.get(code) ?? code;
}

/** The data a 409 carries, or null for any other error. */
function conflictOf(cause: unknown): HandoffConflict | null {
  if (!(cause instanceof ApiError) || cause.status !== 409) return null;
  const body = cause.body;
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const detail = body.detail;
  if (typeof detail !== "object" || detail === null || !("code" in detail)) return null;
  return detail as HandoffConflict;
}

/** The API's own words: a string detail, or the messages of a validation list. */
function detailText(cause: ApiError): string {
  const body = cause.body;
  const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : null;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item === "object" && item !== null && "msg" in item ? item.msg : null))
      .filter((message): message is string => typeof message === "string");
    if (messages.length > 0) return messages.join("; ");
  }
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    const message = detail.message;
    if (typeof message === "string") return message;
  }
  return cause.message;
}

function errorText(cause: unknown): string {
  return cause instanceof ApiError
    ? `${detailText(cause)} (HTTP ${cause.status})`
    : "Cannot reach the API. Check that the backend is running.";
}

type Outcome = { kind: "ok" | "error" | "info"; message: string };

function HandoffPage() {
  // Who acts: the user a link carried here (the Dashboard counts), else the Golden Case head
  // nurse (docs/workflow.md, section 10). The API shows each one their own ward
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  const loadCases = useCallback(
    (signal: AbortSignal) => api<HandoffCase[]>("/cases?status=MANUAL_HANDOFF,FAILED", { signal }),
    [api],
  );
  const { data: cases, error, isLoading, refresh } = usePolling(loadCases);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [candidates, setCandidates] = useState<HandoffCandidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [note, setNote] = useState("");
  // The assignment waiting for "cancel their other offers" to be confirmed
  const [pendingConfirm, setPendingConfirm] = useState<{
    staffId: number;
    caseIds: number[];
  } | null>(null);
  const [closeReason, setCloseReason] = useState("");

  const selected = cases?.find((row) => row.id === selectedId && row.can_manage);
  // The case whose staff list may still be shown. A late answer for another case is dropped
  const listedFor = useRef<number | null>(null);

  const loadCandidates = useCallback(async (caseId: number) => {
    listedFor.current = caseId;
    setCandidates(null);
    try {
      const rows = await api<HandoffCandidate[]>(`/cases/${caseId}/handoff/candidates`);
      if (listedFor.current === caseId) setCandidates(rows);
    } catch (cause) {
      if (listedFor.current === caseId) setOutcome({ kind: "error", message: errorText(cause) });
    }
  }, [api]);

  useEffect(() => {
    if (selectedId === null || !cases) return;
    if (cases.some((row) => row.id === selectedId && row.can_manage)) return;
    // Someone else staffed or closed it, or it left the list: say so instead of a blank panel
    const now = cases.find((row) => row.id === selectedId);
    setOutcome({
      kind: "info",
      message: now
        ? `Case ${selectedId} can no longer be managed: it is now ${now.status}.`
        : `Case ${selectedId} is no longer handed off.`,
    });
    listedFor.current = null;
    setSelectedId(null);
    setCandidates(null);
    setPendingConfirm(null);
  }, [cases, selectedId]);

  useEffect(() => {
    if (selectedId !== null) void loadCandidates(selectedId);
  }, [selectedId, loadCandidates]);

  function changeActor(id: number) {
    // Nothing of the previous user's case may stay open: it belongs to another ward's list
    listedFor.current = null;
    setActorId(id);
    setSelectedId(null);
    setCandidates(null);
    setOutcome(null);
    setNote("");
    setPendingConfirm(null);
    setCloseReason("");
  }

  function open(caseId: number) {
    // Nothing of the previous case may show while the new list loads
    listedFor.current = caseId;
    setCandidates(null);
    setSelectedId(caseId);
    setOutcome(null);
    setNote("");
    setPendingConfirm(null);
    setCloseReason("");
  }

  async function assign(staffId: number, confirmConflicts = false) {
    if (selectedId === null) return;
    setBusy(true);
    setOutcome(null);
    try {
      const trimmed = note.trim();
      const result = await api<ManualAssignmentResult>(
        `/cases/${selectedId}/handoff/assignments`,
        {
          method: "POST",
          json: {
            staff_id: staffId,
            ...(trimmed ? { reason: trimmed } : {}),
            ...(confirmConflicts ? { confirm_conflicts: true } : {}),
          },
        },
      );
      setPendingConfirm(null);
      const cancelled = result.cancelled_outreach_ids.length
        ? ` Offers cancelled elsewhere: ${result.cancelled_outreach_ids.join(", ")}.`
        : "";
      setOutcome({
        kind: "ok",
        message: `Staff ${result.staff_id} assigned. Case ${result.case_id}: ${result.case_status}.${cancelled}`,
      });
      if (result.case_status === "RESOLVED") {
        listedFor.current = null;
        setSelectedId(null);
        setCandidates(null);
      } else {
        await loadCandidates(selectedId);
      }
      await refresh();
    } catch (cause) {
      const conflict = conflictOf(cause);
      if (conflict?.code === "CONFLICTING_OFFERS") {
        setPendingConfirm({ staffId, caseIds: conflict.case_ids });
      } else if (conflict?.code === "HARD_RULES_FAILED") {
        setOutcome({
          kind: "error",
          message: `Staff ${staffId} cannot take this shift: ${conflict.failed_rules
            .map(ruleText)
            .join("; ")}`,
        });
      } else {
        setOutcome({ kind: "error", message: errorText(cause) });
      }
    } finally {
      setBusy(false);
    }
  }

  async function close(event: FormEvent) {
    event.preventDefault();
    const trimmed = closeReason.trim();
    if (selectedId === null || !trimmed) return;
    setBusy(true);
    setOutcome(null);
    try {
      const result = await api<CloseCaseResult>(`/cases/${selectedId}/handoff/close`, {
        method: "POST",
        json: { reason: trimmed },
      });
      setOutcome({ kind: "ok", message: `Case ${result.case_id}: ${result.case_status}` });
      listedFor.current = null;
      setSelectedId(null);
      setCandidates(null);
      await refresh();
    } catch (cause) {
      setOutcome({ kind: "error", message: errorText(cause) });
    } finally {
      setBusy(false);
    }
  }

  const button = "rounded border px-2 py-1 disabled:opacity-50";

  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Handed-off cases</h1>
      <p className="mt-1 text-sm">Cases the system could not staff, from the ward of the user below.</p>
      <div className="mt-1">
        <ActingAs id="handoff-acting-as" value={actorId} onChange={changeActor} />
      </div>

      {error && <p className="mt-4 text-red-700">{error.message}</p>}
      {outcome?.kind === "ok" && <p className="mt-4 text-green-700">{outcome.message}</p>}
      {outcome?.kind === "info" && (
        <p role="status" className="mt-4 text-amber-700">
          {outcome.message}
        </p>
      )}
      {outcome?.kind === "error" && (
        <p role="alert" className="mt-4 text-red-700">
          {outcome.message}
        </p>
      )}
      {isLoading && <p className="mt-4">Loading…</p>}
      {cases && cases.length === 0 && <p className="mt-4">No handed-off cases.</p>}
      {cases && cases.length > 0 && (
        <ScrollX>
          <table className="mt-4 w-full text-left">
            <thead>
              <tr>
                <th>Case</th>
                <th>Status</th>
                <th>Shift</th>
                <th>Still short</th>
                <th>Opened at</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((row) => (
                <tr key={row.id}>
                  <td>
                    <Link className="underline" href={`/cases/${row.id}`}>
                      {row.id}
                    </Link>
                  </td>
                  <td>{row.status}</td>
                  <td>{row.shift_id}</td>
                  <td>{shortByText(row)}</td>
                  <td>{formatDateTime(row.created_at)}</td>
                  <td>
                    {row.can_manage ? (
                      <button
                        type="button"
                        className={button}
                        disabled={busy}
                        onClick={() => open(row.id)}
                      >
                        Manage
                      </button>
                    ) : (
                      // FAILED stays an end point (R2-Q22)
                      <span className="text-sm">Cannot be managed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollX>
      )}

      {selected && (
        <section className="mt-8" aria-label={`Manage case ${selected.id}`}>
          <h2 className="text-xl font-semibold">Case {selected.id}</h2>
          <p className="mt-1 text-sm">
            Assign someone who passes every rule, or close the case without a replacement.
          </p>

          <label className="mt-4 block" htmlFor="assignment-note">
            Note for the assignment (optional)
          </label>
          <input
            id="assignment-note"
            className="mt-1 w-full rounded border p-2"
            maxLength={MAX_REASON_LENGTH}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />

          {pendingConfirm && (
            <div role="alertdialog" className="mt-4 rounded border border-amber-500 p-3">
              <p>
                Staff {pendingConfirm.staffId} has an offer on case{" "}
                {pendingConfirm.caseIds.join(", ")} that this shift rules out. Assigning them
                cancels that offer.
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  className={button}
                  disabled={busy}
                  onClick={() => assign(pendingConfirm.staffId, true)}
                >
                  Assign and cancel the other offer
                </button>
                <button
                  type="button"
                  className={button}
                  disabled={busy}
                  onClick={() => setPendingConfirm(null)}
                >
                  Keep the other offer
                </button>
              </div>
            </div>
          )}

          {candidates === null && <p className="mt-4">Loading staff…</p>}
          {candidates && (
            <ScrollX>
              <table className="mt-4 w-full text-left">
                <thead>
                  <tr>
                    <th>Staff</th>
                    <th>Name</th>
                    <th>Role</th>
                    <th>Can take the shift</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((person) => (
                    <tr key={person.staff_id}>
                      <td>{person.staff_id}</td>
                      <td>
                        {person.first_name} {person.last_name}
                      </td>
                      <td>{person.role_name}</td>
                      <td>
                        {person.blocking_rules.length === 0
                          ? "Yes"
                          : person.blocking_rules.map(ruleText).join("; ")}
                        {person.other_case_ids.length > 0 &&
                          ` (offer on case ${person.other_case_ids.join(", ")})`}
                      </td>
                      <td>
                        <button
                          type="button"
                          className={button}
                          // No override: a blocked person cannot be assigned (R2-Q14)
                          disabled={busy || pendingConfirm !== null || person.blocking_rules.length > 0}
                          onClick={() => assign(person.staff_id)}
                        >
                          Assign
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollX>
          )}

          <form className="mt-6 max-w-xl" onSubmit={close}>
            <label className="block" htmlFor="close-reason">
              Reason for closing case {selected.id} without a replacement
            </label>
            <textarea
              id="close-reason"
              className="mt-1 w-full rounded border p-2"
              rows={3}
              maxLength={MAX_REASON_LENGTH}
              required
              value={closeReason}
              onChange={(event) => setCloseReason(event.target.value)}
            />
            <p className="text-sm">
              {closeReason.length} / {MAX_REASON_LENGTH}
            </p>
            <button
              type="submit"
              className={`${button} mt-2`}
              disabled={busy || !closeReason.trim()}
            >
              Close without a replacement
            </button>
          </form>
        </section>
      )}
    </main>
  );
}

export default function Handoff() {
  return (
    <Suspense>
      <HandoffPage />
    </Suspense>
  );
}
