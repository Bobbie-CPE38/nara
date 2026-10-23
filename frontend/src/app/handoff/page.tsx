"use client";

import Link from "next/link";
import { type FormEvent, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { ActingAs } from "@/components/ActingAs";
import { CaseFilters, type CaseQuery, searchPath } from "@/components/case/CaseFilters";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pager } from "@/components/ui/Pager";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { SKIP_REASON_KEYS } from "@/lib/constants";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type { MessageKey, Params, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type {
  CasePage,
  CloseCaseResult,
  HandoffCandidate,
  HandoffCase,
  HandoffConflict,
  ManualAssignmentResult,
} from "@/lib/types/handoff";

// Same limit as the API (R2-Q20)
const MAX_REASON_LENGTH = 500;
const PAGE_SIZE = 10;

/** Handed off and failed cases, or one of the two (round 6 PR EV6, docs/workflow.md 6.36.6) */
const HANDOFF_STATUS_FILTERS = [
  { value: "MANUAL_HANDOFF,FAILED", label: "cases.filter.attention" },
  { value: "MANUAL_HANDOFF", label: "hand.filter.manual" },
  { value: "FAILED", label: "hand.filter.failed" },
] as const;

function shortByText(row: HandoffCase): string {
  if (row.headcount_gap === null) return "—";
  return String(Math.max(row.headcount_gap - row.assigned_count, 0));
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
type Message = { key: MessageKey; params?: Params } | { failure: unknown };

function errorText(cause: unknown, t: Translate): string {
  return cause instanceof ApiError ? `${detailText(cause, t)} (HTTP ${cause.status})` : describeError(cause, t);
}

type Outcome = { kind: "ok" | "error" | "info"; message: Message };

function HandoffPage() {
  const t = useT();
  // Who acts: the user a link carried here (the Dashboard counts), else the Golden Case head
  // nurse (docs/workflow.md, section 10). The API shows each one their own ward
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  // Search, filter and pages of round 6 PR EV6; the oldest case first, as it waits the longest
  const [query, setQuery] = useState<CaseQuery>({ q: "", status: HANDOFF_STATUS_FILTERS[0].value, page: 1 });
  const loadCases = useCallback(
    (signal: AbortSignal) => api<CasePage>(searchPath(query, PAGE_SIZE, "oldest"), { signal }),
    [api, query],
  );
  const { data: page, error, isLoading, refresh } = usePolling(loadCases);
  const cases = page?.items;
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

  const text = (message: Message) => ("failure" in message ? errorText(message.failure, t) : t(message.key, message.params));
  const ruleText = (code: string) => {
    const key = SKIP_REASON_KEYS.get(code);
    return key ? t(key) : code;
  };

  const loadCandidates = useCallback(async (caseId: number) => {
    listedFor.current = caseId;
    setCandidates(null);
    try {
      const rows = await api<HandoffCandidate[]>(`/cases/${caseId}/handoff/candidates`);
      if (listedFor.current === caseId) setCandidates(rows);
    } catch (cause) {
      if (listedFor.current === caseId) setOutcome({ kind: "error", message: { failure: cause } });
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
        ? { key: "hand.noLonger", params: { id: selectedId, status: now.status } }
        : { key: "hand.noLongerHanded", params: { id: selectedId } },
    });
    listedFor.current = null;
    setSelectedId(null);
    setCandidates(null);
    setPendingConfirm(null);
  }, [cases, selectedId]);

  useEffect(() => {
    if (selectedId !== null) void loadCandidates(selectedId);
  }, [selectedId, loadCandidates]);

  function closeModal() {
    listedFor.current = null;
    setSelectedId(null);
    setCandidates(null);
    setPendingConfirm(null);
    setNote("");
    setCloseReason("");
  }

  function changeActor(id: number) {
    // Nothing of the previous user's case may stay open: it belongs to another ward's list
    listedFor.current = null;
    setActorId(id);
    setQuery((value) => ({ ...value, page: 1 }));
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
        ? t("hand.cancelledElsewhere", { ids: result.cancelled_outreach_ids.join(", ") })
        : "";
      setOutcome({
        kind: "ok",
        message: {
          key: "hand.assigned",
          params: {
            staff: result.staff_id,
            caseId: result.case_id,
            caseStatus: result.case_status,
            cancelled,
          },
        },
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
          message: {
            key: "hand.cannotTake",
            params: { staff: staffId, rules: conflict.failed_rules.map(ruleText).join("; ") },
          },
        });
      } else {
        setOutcome({ kind: "error", message: { failure: cause } });
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
      setOutcome({
        kind: "ok",
        message: { key: "hand.closed", params: { caseId: result.case_id, caseStatus: result.case_status } },
      });
      listedFor.current = null;
      setSelectedId(null);
      setCandidates(null);
      await refresh();
    } catch (cause) {
      setOutcome({ kind: "error", message: { failure: cause } });
    } finally {
      setBusy(false);
    }
  }

  const outcomeView = (
    <>
      {outcome?.kind === "ok" && <p className="font-medium text-green-700">{text(outcome.message)}</p>}
      {outcome?.kind === "info" && (
        <Notice kind="warning" role="status">
          {text(outcome.message)}
        </Notice>
      )}
      {outcome?.kind === "error" && (
        <Notice kind="error" role="alert">
          {text(outcome.message)}
        </Notice>
      )}
    </>
  );

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("hand.title")} description={t("hand.intro")}>
        <ActingAs id="handoff-acting-as" value={actorId} onChange={changeActor} />
      </PageHeader>

      <Card>
        <CaseFilters
          query={query}
          statuses={HANDOFF_STATUS_FILTERS}
          disabled={busy}
          onChange={setQuery}
        />
      </Card>
      <div className="mt-4 space-y-3">
        {error && <p className="text-red-700">{describeError(error, t)}</p>}
        {/* With the dialog open its own answers show in it */}
        {!selected && outcomeView}
      </div>
      {isLoading && <p className="mt-4">{t("common.loading")}</p>}
      {cases && cases.length === 0 && <p className="mt-4">{t("hand.noCases")}</p>}
      {page && cases && cases.length > 0 && (
        <Card className="mt-4">
          <ScrollX>
            <table>
              <thead>
                <tr>
                  <th>{t("common.case")}</th>
                  <th>{t("cand.status")}</th>
                  <th>{t("common.ward")}</th>
                  <th>{t("common.shift")}</th>
                  <th>{t("hand.stillShort")}</th>
                  <th>{t("hand.openedAt")}</th>
                  <th>{t("offers.col.action")}</th>
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
                    <td>{row.ward_name}</td>
                    <td>{row.shift_id}</td>
                    <td>{shortByText(row)}</td>
                    <td>{formatDateTime(row.created_at)}</td>
                    <td>
                      {row.can_manage ? (
                        <Button disabled={busy} onClick={() => open(row.id)}>
                          {t("hand.manage")}
                        </Button>
                      ) : (
                        // FAILED stays an end point (R2-Q22)
                        <span className="text-sm">{t("hand.cannotManage")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollX>
          <Pager
            page={page.page}
            pageSize={page.page_size}
            total={page.total}
            disabled={busy}
            onPage={(next) => setQuery((value) => ({ ...value, page: next }))}
          />
        </Card>
      )}

      {/* Managing a case is a dialog over the list (round 6 PR EV6): the list stays put */}
      {selected && (
        <Modal title={t("hand.manageLabel", { id: selected.id })} onClose={closeModal} closeDisabled={busy}>
          <div className="space-y-3">{outcomeView}</div>
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
                <Button
                  variant="primary"
                  disabled={busy}
                  onClick={() => assign(pendingConfirm.staffId, true)}
                >
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
              {t("hand.closeReasonLabel", { id: selected.id })}
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
