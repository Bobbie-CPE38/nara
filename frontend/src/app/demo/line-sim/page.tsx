"use client";

import { useMemo, useState } from "react";
import { useSessionUser } from "@/components/AuthProvider";
import { type OfferApi, OfferList } from "@/components/outreach/OfferList";
import { PageHeader } from "@/components/ui/PageHeader";
import { apiRequest } from "@/lib/api";
import { DEMO_STAFF_IDS } from "@/lib/demo";
import { useT } from "@/lib/i18n/LanguageProvider";
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
  const t = useT();
  const me = useSessionUser();
  const [chosenStaffId, setStaffId] = useState(201);
  // With a login the simulator answers only as the person who is logged in (docs/workflow.md 6.33.5)
  const staffId = me ? me.staff_id : chosenStaffId;
  const [responding, setResponding] = useState(false);
  const api = useMemo(() => simulatorApi(staffId), [staffId]);
  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("sim.title")} description={me ? t("sim.sessionIntro") : t("sim.intro")}>
        {!me && (
          <label className="flex flex-wrap items-center gap-2 text-sm font-medium" htmlFor="staff">
            {t("sim.staffMember")}
            <select
              id="staff"
              value={staffId}
              disabled={responding}
              onChange={(event) => {
                if (!responding) setStaffId(Number(event.target.value));
              }}
            >
              {DEMO_STAFF_IDS.map((id) => (
                <option key={id} value={id}>
                  {t("sim.staffOption", { id })}
                </option>
              ))}
            </select>
          </label>
        )}
      </PageHeader>
      <OfferList
        key={staffId}
        staffId={staffId}
        api={api}
        emptyText={t("sim.noOffers")}
        onPendingChange={setResponding}
      />
    </main>
  );
}
