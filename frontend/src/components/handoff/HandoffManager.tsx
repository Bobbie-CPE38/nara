"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Notice } from "@/components/ui/Notice";
import { ApiError, type createDemoApi } from "@/lib/api";
import { SKIP_REASON_KEYS } from "@/lib/constants";
import { describeError } from "@/lib/errors";
import type { MessageKey, Params, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type {
  CloseCaseResult,
  HandoffCandidate,
  HandoffConflict,
  ManualAssignmentResult,
} from "@/lib/types/handoff";

// Same limit as the API (R2-Q20)
const MAX_REASON_LENGTH = 500;

type Api = ReturnType<typeof createDemoApi>;

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
function detailText(cause: ApiError, t: Translate): string {
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
  return describeError(cause, t);
}

/** A text of the page (a key and its values, in the language of the user) or the words of the API. */
export type Message = { key: MessageKey; params?: Params } | { failure: unknown };

export type Outcome = { kind: "ok" | "error" | "info"; message: Message };

function errorText(cause: unknown, t: Translate): string {
  return cause instanceof ApiError ? `${detailText(cause, t)} (HTTP ${cause.status})` : describeError(cause, t);
}

/** The result of an action, in the colour of its kind */
export function OutcomeView({ outcome }: { outcome: Outcome | null }) {
  const t = useT();
  if (outcome === null) return null;
  const text = "failure" in outcome.message ? errorText(outcome.message.failure, t) : t(outcome.message.key, outcome.message.params);
  if (outcome.kind === "ok") return <p className="font-medium text-green-700">{text}</p>;
  return (
    <Notice kind={outcome.kind === "info" ? "warning" : "error"} role={outcome.kind === "info" ? "status" : "alert"}>
      {text}
    </Notice>
  );
}

/**
 * Managing one MANUAL_HANDOFF case in a dialog (round 6 PR EV6, docs/workflow.md 6.36.6):
 * put someone free on the shift with a note, confirm cancelling their other offers, or close
 * the case with a reason. The Handoff page and, since round 6 PR EV8 (6.38.7), the case list
 * open it. The parent keys it by case, so another case starts empty.
 *
 * `onDone` is called with the result once the case left the handoff (staffed or closed): the
 * parent closes the dialog and shows the result on its page. `onChanged` reads the list again.
 */
export function HandoffManager({
  caseId,
  api,
  onClose,
  onDone,
  onChanged,
}: {
  caseId: number;
  api: Api;
  onClose: () => void;
  onDone: (outcome: Outcome) => void;
  onChanged: () => Promise<unknown> | void;
}) {
  const t = useT();
  const [candidates, setCandidates] = useState<HandoffCandidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [note, setNote] = useState("");
  // The assignment waiting for "cancel their other offers" to be confirmed
  const [pendingConfirm, setPendingConfirm] = useState<{ staffId: number; caseIds: number[] } | null>(null);
  const [closeReason, setCloseReason] = useState("");
  // A late answer after the dialog closed is dropped
  const open = useRef(true);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const ruleText = (code: string) => {
    const key = SKIP_REASON_KEYS.get(code);
    return key ? t(key) : code;
  };

  const loadCandidates = useCallback(async () => {
    setCandidates(null);
    try {
      const rows = await api<HandoffCandidate[]>(`/cases/${caseId}/handoff/candidates`);
      if (open.current) setCandidates(rows);
    } catch (cause) {
      if (open.current) setOutcome({ kind: "error", message: { failure: cause } });
    }
  }, [api, caseId]);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates]);

  async function assign(staffId: number, confirmConflicts = false) {
    setBusy(true);
    setOutcome(null);
    try {
      const trimmed = note.trim();
      const result = await api<ManualAssignmentResult>(`/cases/${caseId}/handoff/assignments`, {
        method: "POST",
        json: {
          staff_id: staffId,
          ...(trimmed ? { reason: trimmed } : {}),
          ...(confirmConflicts ? { confirm_conflicts: true } : {}),
        },
      });
      if (!open.current) return;
      setPendingConfirm(null);
      const cancelled = result.cancelled_outreach_ids.length
        ? t("hand.cancelledElsewhere", { ids: result.cancelled_outreach_ids.join(", ") })
        : "";
      const done: Outcome = {
        kind: "ok",
        message: {
          key: "hand.assigned",
          params: { staff: result.staff_id, caseId: result.case_id, caseStatus: result.case_status, cancelled },
        },
      };
      if (result.case_status === "RESOLVED") {
        onDone(done);
      } else {
        setOutcome(done);
        await loadCandidates();
      }
      await onChanged();
    } catch (cause) {
      if (!open.current) return;
      const conflict = conflictOf(cause);
      if (conflict?.code === "CONFLICTING_OFFERS") {
        setPendingConfirm({ staffId, caseIds: conflict.case_ids });
      } else if (conflict?.code === "HARD_RULES_FAILED") {
        setOutcome({
          kind: "error",
          message: {
            key: "hand.cannotTake",
            params: { staff: staffId, rules: conflict.failed_rules.map(ruleText).join("; ") },
          },
        });
      } else {
        setOutcome({ kind: "error", message: { failure: cause } });
      }
    } finally {
      if (open.current) setBusy(false);
    }
  }

  async function close(event: FormEvent) {
    event.preventDefault();
    const trimmed = closeReason.trim();
    if (!trimmed) return;
    setBusy(true);
    setOutcome(null);
    try {
      const result = await api<CloseCaseResult>(`/cases/${caseId}/handoff/close`, {
        method: "POST",
        json: { reason: trimmed },
      });
      if (!open.current) return;
      onDone({ kind: "ok", message: { key: "hand.closed", params: { caseId: result.case_id, caseStatus: result.case_status } } });
      await onChanged();
    } catch (cause) {
      if (open.current) setOutcome({ kind: "error", message: { failure: cause } });
    } finally {
      if (open.current) setBusy(false);
    }
  }

  return (
    <Modal title={t("hand.manageLabel", { id: caseId })} onClose={onClose} closeDisabled={busy}>
      <div className="space-y-3">
        <OutcomeView outcome={outcome} />
      </div>
      <p className="mt-1 text-sm">{t("hand.assignHelp")}</p>

      <label className="mt-4 block" htmlFor="assignment-note">
        {t("hand.noteLabel")}
      </label>
      <input
        id="assignment-note"
        className="mt-1 w-full"
        maxLength={MAX_REASON_LENGTH}
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />

      {pendingConfirm && (
        <div role="alertdialog" className="mt-4 rounded-lg border border-amber-400 bg-amber-50 p-3 text-amber-900">
          <p>
            {t("hand.confirm", {
              staff: pendingConfirm.staffId,
              cases: pendingConfirm.caseIds.join(", "),
            })}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button variant="primary" disabled={busy} onClick={() => assign(pendingConfirm.staffId, true)}>
              {t("hand.assignCancel")}
            </Button>
            <Button disabled={busy} onClick={() => setPendingConfirm(null)}>
              {t("hand.keepOffer")}
            </Button>
          </div>
        </div>
      )}

      {candidates === null && <p className="mt-4">{t("hand.loadingStaff")}</p>}
      {candidates && (
        <ScrollX>
          <table className="mt-4">
            <thead>
              <tr>
                <th>{t("common.staff")}</th>
                <th>{t("common.name")}</th>
                <th>{t("common.role")}</th>
                <th>{t("hand.canTake")}</th>
                <th>{t("offers.col.action")}</th>
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
                      ? t("gapPage.yes")
                      : person.blocking_rules.map(ruleText).join("; ")}
                    {person.other_case_ids.length > 0 &&
                      t("hand.otherCase", { cases: person.other_case_ids.join(", ") })}
                  </td>
                  <td>
                    <Button
                      // No override: a blocked person cannot be assigned (R2-Q14)
                      disabled={busy || pendingConfirm !== null || person.blocking_rules.length > 0}
                      onClick={() => assign(person.staff_id)}
                    >
                      {t("hand.assign")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollX>
      )}

      <form className="mt-6 max-w-xl" onSubmit={close}>
        <label className="block" htmlFor="close-reason">
          {t("hand.closeReasonLabel", { id: caseId })}
        </label>
        <textarea
          id="close-reason"
          className="mt-1 w-full"
          rows={3}
          maxLength={MAX_REASON_LENGTH}
          required
          value={closeReason}
          onChange={(event) => setCloseReason(event.target.value)}
        />
        <p className="text-sm">
          {closeReason.length} / {MAX_REASON_LENGTH}
        </p>
        <Button type="submit" className="mt-2" disabled={busy || !closeReason.trim()}>
          {t("hand.closeButton")}
        </Button>
      </form>
    </Modal>
  );
}
