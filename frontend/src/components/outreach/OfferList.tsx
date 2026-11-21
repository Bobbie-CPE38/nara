"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { Pager } from "@/components/ui/Pager";
import { usePolling } from "@/hooks/usePolling";
import { ApiError } from "@/lib/api";
import { formatDemoTime } from "@/lib/demo";
import { describeError } from "@/lib/errors";
import type { MessageKey, Params, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CaseStatus, Offer, OfferResponse, OutreachStatus } from "@/lib/types/outreach";

function offerSnapshot(offer: Offer) {
  return JSON.stringify([
    offer.id,
    offer.case_id,
    offer.candidate_item_id,
    offer.staff_id,
    offer.proposed_shift_id,
    offer.status,
    offer.case_status,
    offer.sent_at,
    offer.response_at,
    offer.expires_at,
    offer.can_accept,
    offer.can_reject,
    offer.blocked_reason,
    offer.final_outcome,
    offer.final_message,
    offer.final_delivery_status,
    offer.is_reserve,
    offer.is_assigned,
  ]);
}

const STOPPED_CASE_STATUSES = new Set([
  "FAILED",
  "RESOLVED",
  "UNRESOLVED",
  "MANUAL_HANDOFF",
]);

/** The status codes among the values of a message become words of the language of the page. */
function statusWords(params: Params | undefined, t: Translate): Params | undefined {
  if (!params) return params;
  const words = { ...params };
  if (typeof words.status === "string") words.status = t(`offerStatus.${words.status as OutreachStatus}`);
  if (typeof words.caseStatus === "string") words.caseStatus = t(`caseStatusShort.${words.caseStatus as CaseStatus}`);
  return words;
}

/** A text of the page (a key and its values, shown in the language of the user) or the words of the server. */
type FeedbackMessage = { key: MessageKey; params?: Params } | { failure: unknown };

type Feedback = {
  message: FeedbackMessage;
  kind: "notice" | "error";
  matches: (offers: Offer[]) => boolean;
  // An older in-flight read may still contain the row from before the POST.
  beforeSnapshot?: string;
};

export type OfferApi = {
  /** Reads the offers shown in the table. Must keep the same identity between renders. */
  load: (signal: AbortSignal) => Promise<Offer[]>;
  respond: (
    offerId: number,
    response: "ACCEPT" | "REJECT",
    signal: AbortSignal,
  ) => Promise<OfferResponse>;
};

/** Offers per page of each list (round 6 PR EV8) */
export const OFFERS_PAGE_SIZE = 10;

type OfferView = "open" | "closed";

/** The newest offer first: by the time it was sent, then by ID (an offer not sent yet goes last) */
function newestFirst(left: Offer, right: Offer): number {
  const sent = (right.sent_at ?? "").localeCompare(left.sent_at ?? "");
  return sent !== 0 ? sent : right.id - left.id;
}

const COLUMNS: readonly MessageKey[] = [
  "offers.col.offer",
  "common.case",
  "offers.col.wardShift",
  "offers.col.offerStatus",
  "offers.col.caseStatus",
  "offers.col.sent",
  "offers.col.responded",
  "offers.col.deadline",
  "offers.col.action",
];

/**
 * Offer history with Accept and Reject, shared by the LINE simulator and the
 * nurse page (docs/workflow.md, section 6.17). The caller decides which API
 * reads and answers; this component never chooses a staff member.
 */
export function OfferList({
  staffId,
  api,
  emptyText,
  onPendingChange,
}: {
  staffId: number;
  api: OfferApi;
  emptyText: string;
  onPendingChange?: (pending: boolean) => void;
}) {
  const t = useT();
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [answeredSnapshot, setAnsweredSnapshot] = useState<string | null>(null);
  const actionController = useRef<AbortController | null>(null);
  useEffect(() => () => actionController.current?.abort(), []);
  const { data, error, isLoading, refresh } = usePolling(api.load);
  useEffect(() => {
    if (!data) return;
    setFeedback((current) => {
      if (!current) return null;
      if (current.matches(data)) {
        // Once the result is confirmed, a later reset must not match the old row.
        return current.beforeSnapshot
          ? { ...current, beforeSnapshot: undefined }
          : current;
      }
      return current.beforeSnapshot &&
        data.some((offer) => offerSnapshot(offer) === current.beforeSnapshot)
        ? current
        : null;
    });
    setAnsweredSnapshot((current) =>
      data.some((offer) => offerSnapshot(offer) === current) ? current : null,
    );
  }, [data]);
  const openOffers =
    data?.filter((offer) => offer.status === "SENT" && offer.can_reject) ?? [];
  // Round 6 PR EV8 (docs/workflow.md 6.38.3): newest first, in two lists, the offers the nurse
  // may still answer and the ones they no longer may, one page at a time. Until the nurse
  // picks one, the list shows what they can answer, or their history when nothing waits
  const [picked, setPicked] = useState<OfferView | null>(null);
  const [page, setPage] = useState(1);
  const lists = useMemo(() => {
    const sorted = [...(data ?? [])].sort(newestFirst);
    // The same test as openOffers: the offers Accept or Reject may still answer
    const answerable = (offer: Offer) => offer.status === "SENT" && offer.can_reject;
    return { open: sorted.filter(answerable), closed: sorted.filter((offer) => !answerable(offer)) };
  }, [data]);
  const view: OfferView = picked ?? (lists.open.length > 0 ? "open" : "closed");
  const rows = lists[view];
  const pages = Math.max(1, Math.ceil(rows.length / OFFERS_PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const shown = rows.slice((currentPage - 1) * OFFERS_PAGE_SIZE, currentPage * OFFERS_PAGE_SIZE);
  function show(next: OfferView) {
    setPicked(next);
    setPage(1);
  }

  async function respond(offerId: number, response: "ACCEPT" | "REJECT") {
    // A ref also prevents a second click before React paints the pending state.
    const selected = openOffers.find((offer) => offer.id === offerId);
    if (
      actionController.current ||
      !selected ||
      (response === "ACCEPT" && !selected.can_accept) ||
      error ||
      offerSnapshot(selected) === answeredSnapshot
    )
      return;
    const previousOpenSnapshots = new Set(openOffers.map(offerSnapshot));
    const controller = new AbortController();
    actionController.current = controller;
    setPending(true);
    onPendingChange?.(true);
    setFeedback(null);
    try {
      const result = await api.respond(offerId, response, controller.signal);
      if (controller.signal.aborted) return;
      // Keep this stale row disabled even if the refresh is slow or fails.
      setAnsweredSnapshot(offerSnapshot(selected));
      const matches = (offers: Offer[]) =>
        offers.some(
          (offer) =>
            offer.id === result.outreach_id &&
            offer.case_id === result.case_id &&
            offer.status === result.outreach_status &&
            offer.case_status === result.case_status,
        );
      if (result.outreach_id !== offerId) {
        setFeedback({
          kind: "error",
          matches,
          beforeSnapshot: offerSnapshot(selected),
          message: {
            key: "offers.changed",
            params: {
              selected: offerId,
              status: result.outreach_status,
              recorded: result.outreach_id,
              caseId: result.case_id,
            },
          },
        });
      } else if (result.case_status === "FAILED") {
        setFeedback({
          kind: "error",
          matches,
          beforeSnapshot: offerSnapshot(selected),
          message: {
            key: "offers.caseFailed",
            params: { offer: result.outreach_id, status: result.outreach_status, caseId: result.case_id },
          },
        });
      } else {
        setFeedback({
          kind: "notice",
          matches,
          beforeSnapshot: offerSnapshot(selected),
          message: {
            key: "offers.result",
            params: {
              offer: result.outreach_id,
              status: result.outreach_status,
              caseId: result.case_id,
              caseStatus: result.case_status,
            },
          },
        });
      }
      await refresh();
    } catch (cause) {
      if (controller.signal.aborted) return;
      setFeedback({
        kind: "error",
        matches: (offers) =>
          offers.some((offer) =>
            cause instanceof ApiError && cause.status === 409
              ? offer.id === selected.id &&
                offer.sent_at === selected.sent_at &&
                !offers.some(
                  (other) =>
                    other.status === "SENT" &&
                    other.can_accept &&
                    other.id !== selected.id &&
                    !previousOpenSnapshots.has(offerSnapshot(other)),
                )
              : offerSnapshot(offer) === offerSnapshot(selected),
          ),
        // The words of the server stay as they are; our own text is in the user's language
        message: cause instanceof Error ? { failure: cause } : { key: "offers.sendFailed" },
      });
      if (cause instanceof ApiError && cause.status === 409) {
        setAnsweredSnapshot(offerSnapshot(selected));
        await refresh();
      }
    } finally {
      if (!controller.signal.aborted) {
        actionController.current = null;
        setPending(false);
        onPendingChange?.(false);
      }
    }
  }

  // The statuses are kept as the API sent them and given their words here, in the language of now
  const feedbackText = feedback
    ? "failure" in feedback.message
      ? describeError(feedback.message.failure, t)
      : t(feedback.message.key, statusWords(feedback.message.params, t))
    : null;

  return (
    <section aria-label={t("offers.label")} className="mt-6 space-y-4">
      {isLoading && <p role="status">{t("offers.loading")}</p>}
      {error && (
        <Notice kind="error" role="alert">
          {t("offers.refreshFailed", { error: describeError(error, t) })}
        </Notice>
      )}
      {feedback?.kind === "notice" && (
        <Notice kind="info" role="status">
          {feedbackText}
        </Notice>
      )}
      {feedback?.kind === "error" && (
        <Notice kind="error" role="alert">
          {feedbackText}
        </Notice>
      )}
      {data?.length === 0 && <p>{emptyText}</p>}
      {data && data.length > 0 && (
        <Card>
          <div role="group" aria-label={t("offers.lists")} className="inline-flex overflow-hidden rounded-lg border border-slate-300">
            {(["open", "closed"] as const).map((key) => (
              <button
                key={key}
                type="button"
                aria-pressed={view === key}
                onClick={() => show(key)}
                className={`rounded-none border-0 px-3 py-1.5 text-sm font-medium shadow-none ${
                  view === key ? "bg-brand-600 text-white" : "bg-white text-slate-700 hover:bg-brand-50"
                } ${key === "closed" ? "border-l border-slate-300" : ""}`}
              >
                {t(key === "open" ? "offers.view.open" : "offers.view.closed", { count: lists[key].length })}
              </button>
            ))}
          </div>
          {rows.length === 0 ? (
            <p className="mt-3">{t(view === "open" ? "offers.view.noneOpen" : "offers.view.noneClosed")}</p>
          ) : (
            <ScrollX>
              <table className="mt-3 text-sm">
                <caption className="sr-only">
                  {t("offers.caption", { id: staffId })}
                </caption>
                <thead>
                  <tr>
                    {COLUMNS.map((label) => (
                      <th key={label} scope="col">
                        {t(label)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((offer) => {
                    const canRespond =
                      openOffers.some((open) => open.id === offer.id) &&
                      offerSnapshot(offer) !== answeredSnapshot &&
                      !pending &&
                      !error;
                    return (
                      <tr key={offer.id}>
                        <td>{offer.id}</td>
                        <td>{offer.case_id}</td>
                        <td>
                          {t("offers.wardShift", { ward: offer.ward_name, shift: offer.proposed_shift_id })}
                          <div>
                            {formatDemoTime(offer.shift_start_at)} –{" "}
                            {formatDemoTime(offer.shift_end_at)}
                          </div>
                        </td>
                        <td>{offer.status}</td>
                        <td>{offer.case_status}</td>
                        <td className="whitespace-nowrap">
                          {formatDemoTime(offer.sent_at)}
                        </td>
                        <td className="whitespace-nowrap">
                          {formatDemoTime(offer.response_at)}
                        </td>
                        <td className="whitespace-nowrap">
                          {formatDemoTime(offer.expires_at)}
                        </td>
                        <td>
                          <div className="flex gap-2">
                            <Button
                              variant="primary"
                              aria-label={t("offers.acceptLabel", { id: offer.id })}
                              disabled={!canRespond || !offer.can_accept}
                              onClick={() => void respond(offer.id, "ACCEPT")}
                            >
                              {t("offers.accept")}
                            </Button>
                            <Button
                              aria-label={t("offers.rejectLabel", { id: offer.id })}
                              disabled={!canRespond}
                              onClick={() => void respond(offer.id, "REJECT")}
                            >
                              {t("offers.reject")}
                            </Button>
                          </div>
                          {(offer.blocked_reason === "OFFER_EXPIRED" ||
                            offer.status === "TIMEOUT") && (
                            <p className="mt-1">{t("offers.expired")}</p>
                          )}
                          {offer.blocked_reason === "AWAITING_OTHER_CASE" && (
                            <p className="mt-1">{t("offers.paused")}</p>
                          )}
                          {offer.cancellation_reason && !offer.final_message && (
                            <p className="mt-1">{t("offers.cancelled", { reason: offer.cancellation_reason })}</p>
                          )}
                          {!offer.is_assigned && offer.final_message && (
                            <p className="mt-1 whitespace-pre-line">{offer.final_message}</p>
                          )}
                          {!offer.is_assigned && offer.final_delivery_status === "FAILED" && (
                            <p className="mt-1 text-amber-800">{t("offers.lineFailed")}</p>
                          )}
                          {offer.is_assigned ? (
                            <p className="mt-1">{t("offers.assigned")}</p>
                          ) : offer.is_reserve ? (
                            <p className="mt-1">{t("offers.reserve")}</p>
                          ) : (
                            offer.status === "ACCEPTED" &&
                            !STOPPED_CASE_STATUSES.has(offer.case_status) && (
                              <p className="mt-1">{t("offers.notConfirmed")}</p>
                            )
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </ScrollX>
          )}
          {rows.length > OFFERS_PAGE_SIZE && (
            <Pager page={currentPage} pageSize={OFFERS_PAGE_SIZE} total={rows.length} onPage={setPage} />
          )}
        </Card>
      )}
      <p className="text-sm text-slate-600">{t("offers.help")}</p>
    </section>
  );
}
