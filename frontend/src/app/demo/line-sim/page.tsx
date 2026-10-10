"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, apiRequest } from "@/lib/api";
import { DEMO_STAFF, formatDemoTime } from "@/lib/demo";
import type { Offer, OfferResponse } from "@/lib/types/outreach";

function StaffOffers({ staffId }: { staffId: number }) {
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const actionController = useRef<AbortController | null>(null);
  useEffect(() => () => actionController.current?.abort(), []);
  const load = useCallback(
    (signal: AbortSignal) => {
      void revision;
      return apiRequest<Offer[]>(`/demo/line-sim/offers?staff_id=${staffId}`, {
        demoUser: staffId,
        signal,
      });
    },
    [staffId, revision],
  );
  const { data, error, isLoading } = usePolling(load);
  const openOffers =
    data?.filter(
      (offer) =>
        offer.status === "SENT" && offer.case_status === "WAITING_RESPONSE",
    ) ?? [];

  async function respond(response: "ACCEPT" | "REJECT") {
    // A ref also prevents a second click before React paints the pending state.
    if (actionController.current || openOffers.length !== 1 || error) return;
    const controller = new AbortController();
    actionController.current = controller;
    setPending(true);
    setNotice(null);
    setActionError(null);
    try {
      const result = await apiRequest<OfferResponse>("/demo/line-sim/respond", {
        method: "POST",
        demoUser: staffId,
        json: { response },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (result.case_status === "FAILED") {
        setActionError(
          `Case ${result.case_id} failed after acceptance. Check its timeline.`,
        );
      } else {
        setNotice(
          `Offer accepted. Case ${result.case_id}: ${result.case_status}.`,
        );
      }
      setRevision((value) => value + 1);
    } catch (cause) {
      if (controller.signal.aborted) return;
      setActionError(
        cause instanceof ApiError &&
          cause.status === 422 &&
          response === "REJECT"
          ? "Rejection is not supported in this demo yet. The offer remains unchanged."
          : cause instanceof Error
            ? cause.message
            : "Could not send your response.",
      );
      if (cause instanceof ApiError && cause.status === 409)
        setRevision((value) => value + 1);
    } finally {
      if (!controller.signal.aborted) {
        actionController.current = null;
        setPending(false);
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
      {notice && (
        <p role="status" className="text-green-800">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="text-red-700">
          {actionError}
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
                  offer.status === "SENT" &&
                  offer.case_status === "WAITING_RESPONSE" &&
                  openOffers.length === 1 &&
                  !pending &&
                  !error;
                return (
                  <tr key={offer.id} className="border-t border-slate-200">
                    <td className="p-3">{offer.id}</td>
                    <td className="p-3">
                      <Link
                        className="text-blue-700 underline"
                        href={`/cases/${offer.case_id}`}
                      >
                        {offer.case_id}
                      </Link>
                    </td>
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
                          disabled={!canRespond}
                          onClick={() => void respond("ACCEPT")}
                          className="rounded bg-blue-700 px-3 py-2 text-white disabled:opacity-40"
                        >
                          Accept
                        </button>
                        <button
                          disabled={!canRespond}
                          onClick={() => void respond("REJECT")}
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
        onChange={(event) => setStaffId(Number(event.target.value))}
      >
        {DEMO_STAFF.map(([id, name]) => (
          <option key={id} value={id}>
            {id} — {name}
          </option>
        ))}
      </select>
      <StaffOffers key={staffId} staffId={staffId} />
    </main>
  );
}
