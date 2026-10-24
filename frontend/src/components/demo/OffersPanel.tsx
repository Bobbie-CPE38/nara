"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, apiRequest } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { DemoOffer } from "@/lib/types/demo";

type Answer = "ACCEPT" | "REJECT";
type Outcome = { kind: "done"; offer: DemoOffer; answer: Answer; caseStatus: string } | { kind: "error"; cause: unknown };

/**
 * The offers still open, answered from the Demo control in the candidate's place (round 6 PR
 * EV7, docs/workflow.md 6.37.8): no LINE needed to play the candidates. The Backend records
 * the answer in the candidate's name with source SIMULATED, like a scripted nurse.
 */
export function OffersPanel({ blocked = false }: { blocked?: boolean }) {
  const t = useT();
  const load = useCallback((signal: AbortSignal) => apiRequest<DemoOffer[]>("/demo/offers", { signal }), []);
  const offers = usePolling(load);
  const [busy, setBusy] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const rows = Array.isArray(offers.data) ? offers.data : [];

  async function answer(offer: DemoOffer, response: Answer) {
    setBusy(offer.id);
    setOutcome(null);
    try {
      const result = await apiRequest<{ case_status: string }>(`/demo/offers/${offer.id}/response`, {
        method: "POST",
        json: { response },
      });
      setOutcome({ kind: "done", offer, answer: response, caseStatus: result.case_status });
    } catch (cause) {
      setOutcome({ kind: "error", cause });
    } finally {
      setBusy(null);
      void offers.refresh();
    }
  }

  return (
    <fieldset className="mt-4 flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 shadow-md">
      <legend className="px-1 font-semibold text-brand-800">{t("ctl.offers.title")}</legend>
      <p className="text-sm text-slate-600">{t("ctl.offers.intro")}</p>
      {offers.error && (
        <Notice kind="warning" role="status">
          {describeError(offers.error, t)}
        </Notice>
      )}
      {offers.data !== undefined && rows.length === 0 && <p>{t("ctl.offers.none")}</p>}
      {rows.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {rows.map((offer) => (
            <li key={offer.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>
                <strong>{offer.staff_id}</strong> {offer.first_name} {offer.last_name} ·{" "}
                <Link className="underline" href={`/cases/${offer.case_id}`}>
                  {t("ctl.offers.case", { id: offer.case_id })}
                </Link>{" "}
                · {offer.ward_name} · {formatDateTime(offer.shift_start_at).slice(0, 16)}
              </span>
              <span className="flex gap-2">
                <Button
                  variant="primary"
                  disabled={blocked || busy !== null || !offer.can_accept}
                  onClick={() => void answer(offer, "ACCEPT")}
                  aria-label={t("ctl.offers.acceptFor", { staff: offer.staff_id, id: offer.case_id })}
                >
                  {t("ctl.offers.accept")}
                </Button>
                <Button
                  disabled={blocked || busy !== null || !offer.can_reject}
                  onClick={() => void answer(offer, "REJECT")}
                  aria-label={t("ctl.offers.rejectFor", { staff: offer.staff_id, id: offer.case_id })}
                >
                  {t("ctl.offers.reject")}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {outcome?.kind === "done" && (
        <p role="status" className="font-medium text-green-700">
          {t(outcome.answer === "ACCEPT" ? "ctl.offers.accepted" : "ctl.offers.rejected", {
            staff: outcome.offer.staff_id,
            id: outcome.offer.case_id,
            status: outcome.caseStatus,
          })}
        </p>
      )}
      {outcome?.kind === "error" && (
        <p role="alert" className="text-red-700">
          {describeError(outcome.cause, t)}
          {outcome.cause instanceof ApiError ? ` (HTTP ${outcome.cause.status})` : ""}
        </p>
      )}
    </fieldset>
  );
}
