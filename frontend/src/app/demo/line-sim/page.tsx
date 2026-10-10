"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, apiRequest } from "@/lib/api";
import { DEMO_STAFF_IDS, formatDemoTime } from "@/lib/demo";
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
  ]);
}

type Feedback = {
  message: string;
  kind: "notice" | "error";
  matches: (offers: Offer[]) => boolean;
  // An older in-flight read may still contain the row from before the POST.
  beforeSnapshot?: string;
};

function StaffOffers({
  staffId,
  onPendingChange,
}: {
  staffId: number;
  onPendingChange: (pending: boolean) => void;
}) {
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [answeredSnapshot, setAnsweredSnapshot] = useState<string | null>(null);
  const actionController = useRef<AbortController | null>(null);
  useEffect(() => () => actionController.current?.abort(), []);
  const load = useCallback(
    (signal: AbortSignal) => {
      return apiRequest<Offer[]>(`/demo/line-sim/offers?staff_id=${staffId}`, {
        demoUser: staffId,
        signal,
      });
    },
    [staffId],
  );
  const { data, error, isLoading, refresh } = usePolling(load);
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
    data?.filter(
      (offer) =>
        offer.status === "SENT" && offer.case_status === "WAITING_RESPONSE",
    ) ?? [];

  async function respond(offerId: number, response: "ACCEPT" | "REJECT") {
    // A ref also prevents a second click before React paints the pending state.
    const selected = openOffers.length === 1 ? openOffers[0] : undefined;
    if (
      actionController.current ||
      selected?.id !== offerId ||
      error ||
      offerSnapshot(selected) === answeredSnapshot
    )
      return;
    const controller = new AbortController();
    actionController.current = controller;
    setPending(true);
    onPendingChange(true);
    setFeedback(null);
    try {
      const result = await apiRequest<OfferResponse>("/demo/line-sim/respond", {
        method: "POST",
        demoUser: staffId,
        json: { response },
        signal: controller.signal,
      });
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
      refresh();
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
                    other.case_status === "WAITING_RESPONSE" &&
                    (other.id !== selected.id ||
                      other.sent_at !== selected.sent_at),
                )
              : offerSnapshot(offer) === offerSnapshot(selected),
          ),
        message:
          cause instanceof ApiError &&
          cause.status === 422 &&
          response === "REJECT"
            ? "Rejection is not supported in this demo yet. The offer remains unchanged."
            : cause instanceof Error
              ? cause.message
              : "Could not send your response.",
      });
      if (cause instanceof ApiError && cause.status === 409) {
        setAnsweredSnapshot(offerSnapshot(selected));
        refresh();
      }
    } finally {
      if (!controller.signal.aborted) {
        actionController.current = null;
        setPending(false);
        onPendingChange(false);
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
      {data?.length === 0 && <p>No offers for this staff member.</p>}
      {openOffers.length > 1 && (
        <p role="alert">
          More than one open offer was found. Check the case timelines before
          responding.
        </p>
      )}
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
                  "Shift",
                  "Offer status",
                  "Case status",
                  "Sent (Bangkok)",
                  "Responded (Bangkok)",
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
                  openOffers.length === 1 &&
                  openOffers[0].id === offer.id &&
                  offerSnapshot(offer) !== answeredSnapshot &&
                  !pending &&
                  !error;
                return (
                  <tr key={offer.id} className="border-t border-slate-200">
                    <td className="p-3">{offer.id}</td>
                    <td className="p-3">{offer.case_id}</td>
                    <td className="p-3">{offer.proposed_shift_id}</td>
                    <td className="p-3">{offer.status}</td>
                    <td className="p-3">{offer.case_status}</td>
                    <td className="whitespace-nowrap p-3">
                      {formatDemoTime(offer.sent_at)}
                    </td>
                    <td className="whitespace-nowrap p-3">
                      {formatDemoTime(offer.response_at)}
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <button
                          aria-label={`Accept offer ${offer.id}`}
                          disabled={!canRespond}
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
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-sm text-slate-600">
        Only a SENT offer on a WAITING_RESPONSE case can be answered. Rejection
        is not supported in this demo yet.
      </p>
    </section>
  );
}

export default function LineSimulatorPage() {
  const [staffId, setStaffId] = useState(201);
  const [responding, setResponding] = useState(false);
  return (
    <main className="mx-auto max-w-7xl p-6 text-slate-900">
      <h1 className="text-2xl font-semibold">Demo LINE simulator</h1>
      <p className="mt-2 text-slate-600">
        View offers and respond as the selected staff member. Updates every 2
        seconds.
      </p>
      <label className="mt-6 block" htmlFor="staff">
        Staff member
      </label>
      <select
        id="staff"
        className="mt-2 rounded border border-slate-400 p-2"
        value={staffId}
        disabled={responding}
        onChange={(event) => {
          if (!responding) setStaffId(Number(event.target.value));
        }}
      >
        {DEMO_STAFF_IDS.map((id) => (
          <option key={id} value={id}>
            Staff {id}
          </option>
        ))}
      </select>
      <StaffOffers
        key={staffId}
        staffId={staffId}
        onPendingChange={setResponding}
      />
    </main>
  );
}
