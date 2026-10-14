"use client";

import { useMemo, useState } from "react";
import { type OfferApi, OfferList } from "@/components/outreach/OfferList";
import { apiRequest } from "@/lib/api";
import { DEMO_STAFF_IDS } from "@/lib/demo";
import type { Offer, OfferResponse } from "@/lib/types/outreach";

/** Any staff member's offers: the simulator reads by staff_id and answers as that person. */
function simulatorApi(staffId: number): OfferApi {
  return {
    load: (signal) =>
      apiRequest<Offer[]>(`/demo/line-sim/offers?staff_id=${staffId}`, {
        demoUser: staffId,
        signal,
      }),
    respond: (offerId, response, signal) =>
      apiRequest<OfferResponse>("/demo/line-sim/respond", {
        method: "POST",
        demoUser: staffId,
        json: { outreach_id: offerId, response },
        signal,
      }),
  };
}

export default function LineSimulatorPage() {
  const [staffId, setStaffId] = useState(201);
  const [responding, setResponding] = useState(false);
  const api = useMemo(() => simulatorApi(staffId), [staffId]);
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
      <OfferList
        key={staffId}
        staffId={staffId}
        api={api}
        emptyText="No offers for this staff member."
        onPendingChange={setResponding}
      />
    </main>
  );
}
