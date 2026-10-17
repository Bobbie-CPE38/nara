"use client";

import { useEffect, useRef, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError } from "@/lib/api";
import { formatDemoTime } from "@/lib/demo";
import type { Offer, OfferResponse } from "@/lib/types/outreach";

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

type Feedback = {
  message: string;
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
          message: `The offer changed before your response arrived. You selected offer ${offerId}, but the server recorded ${result.outreach_status} for offer ${result.outreach_id} on case ${result.case_id}. Check the refreshed history.`,
        });
      } else if (result.case_status === "FAILED") {
        setFeedback({
          kind: "error",
          matches,
          beforeSnapshot: offerSnapshot(selected),
          message: `Offer ${result.outreach_id}: ${result.outreach_status}. Case ${result.case_id} failed after this response. Check its timeline.`,
        });
      } else {
        setFeedback({
          kind: "notice",
          matches,
          beforeSnapshot: offerSnapshot(selected),
          message: `Offer ${result.outreach_id}: ${result.outreach_status}. Case ${result.case_id}: ${result.case_status}.`,
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
        message:
          cause instanceof Error
            ? cause.message
            : "Could not send your response.",
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

  return (
    <section aria-label="Offers" className="mt-6 space-y-4">
      {isLoading && <p role="status">Loading offers…</p>}
      {error && (
        <p role="alert" className="text-red-700">
          Could not refresh offers: {error.message}
        </p>
      )}
      {feedback?.kind === "notice" && (
        <p role="status" className="text-green-800">
          {feedback.message}
        </p>
      )}
      {feedback?.kind === "error" && (
        <p role="alert" className="text-red-700">
          {feedback.message}
        </p>
      )}
      {data?.length === 0 && <p>{emptyText}</p>}
      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded border border-slate-300">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">
              Offer history for staff {staffId}
            </caption>
            <thead className="bg-slate-100">
              <tr>
                {[
                  "Offer",
                  "Case",
                  "Ward / Shift",
                  "Offer status",
                  "Case status",
                  "Sent (Bangkok)",
                  "Responded (Bangkok)",
                  "Deadline (Bangkok)",
                  "Action",
                ].map((label) => (
                  <th key={label} scope="col" className="p-3">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((offer) => {
                const canRespond =
                  openOffers.some((open) => open.id === offer.id) &&
                  offerSnapshot(offer) !== answeredSnapshot &&
                  !pending &&
                  !error;
                return (
                  <tr key={offer.id} className="border-t border-slate-200">
                    <td className="p-3">{offer.id}</td>
                    <td className="p-3">{offer.case_id}</td>
                    <td className="p-3">
                      {offer.ward_name} · Shift {offer.proposed_shift_id}
                      <div>
                        {formatDemoTime(offer.shift_start_at)} –{" "}
                        {formatDemoTime(offer.shift_end_at)}
                      </div>
                    </td>
                    <td className="p-3">{offer.status}</td>
                    <td className="p-3">{offer.case_status}</td>
                    <td className="whitespace-nowrap p-3">
                      {formatDemoTime(offer.sent_at)}
                    </td>
                    <td className="whitespace-nowrap p-3">
                      {formatDemoTime(offer.response_at)}
                    </td>
                    <td className="whitespace-nowrap p-3">
                      {formatDemoTime(offer.expires_at)}
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <button
                          aria-label={`Accept offer ${offer.id}`}
                          disabled={!canRespond || !offer.can_accept}
                          onClick={() => void respond(offer.id, "ACCEPT")}
                          className="rounded bg-blue-700 px-3 py-2 text-white disabled:opacity-40"
                        >
                          Accept
                        </button>
                        <button
                          aria-label={`Reject offer ${offer.id}`}
                          disabled={!canRespond}
                          onClick={() => void respond(offer.id, "REJECT")}
                          className="rounded border border-slate-400 px-3 py-2 disabled:opacity-40"
                        >
                          Reject
                        </button>
                      </div>
                      {(offer.blocked_reason === "OFFER_EXPIRED" ||
                        offer.status === "TIMEOUT") && (
                        <p>
                          This offer has expired. You can no longer accept or
                          reject it.
                        </p>
                      )}
                      {offer.blocked_reason === "AWAITING_OTHER_CASE" && (
                        <p>
                          Accept is paused while another case reviews your
                          acceptance. You may still reject this offer.
                        </p>
                      )}
                      {offer.cancellation_reason && !offer.final_message && (
                        <p>Cancelled: {offer.cancellation_reason}</p>
                      )}
                      {!offer.is_assigned && offer.final_message && (
                        <p className="whitespace-pre-line">{offer.final_message}</p>
                      )}
                      {!offer.is_assigned && offer.final_delivery_status === "FAILED" && (
                        <p className="text-amber-800">
                          The LINE notification could not be delivered. Your latest result is shown here.
                        </p>
                      )}
                      {offer.is_assigned ? (
                        <p>Assignment confirmed for this shift.</p>
                      ) : offer.is_reserve ? (
                        <p>
                          Accepted as a reserve. Do not come to the shift unless
                          selected and approved.
                        </p>
                      ) : (
                        offer.status === "ACCEPTED" &&
                        !STOPPED_CASE_STATUSES.has(offer.case_status) && (
                          <p>
                            Acceptance is not a confirmed assignment. Wait for
                            head-nurse approval.
                          </p>
                        )
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-sm text-slate-600">
        Choose an offer to accept or reject. Accepting pauses acceptance of your
        other offers until the outcome is known.
      </p>
    </section>
  );
}
