"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { HandoverList, isHandover } from "@/components/handover/HandoverList";
import { type OfferApi, OfferList } from "@/components/outreach/OfferList";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useHandoverHistory } from "@/hooks/useHandoverHistory";
import { DEFAULT_POLL_INTERVAL_MS } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import {
  DEMO_APPROVERS,
  DEMO_SIGNED_IN_STORAGE_KEY as SIGNED_IN_STORAGE_KEY,
  DEMO_STAFF_IDS,
  DEMO_WARDS,
} from "@/lib/demo";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type { MessageKey, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CheckInResult } from "@/lib/types/attendance";
import type { HandoverView } from "@/lib/types/case";
import type { Offer, OfferResponse } from "@/lib/types/outreach";

// Head nurses and the Supervisor approve; nurses are everyone else on the demo list
const APPROVER_IDS: readonly number[] = DEMO_APPROVERS.map((approver) => approver.id);
const NURSE_IDS = DEMO_STAFF_IDS.filter((id) => !APPROVER_IDS.includes(id));

function readSignedIn(): number | null {
  try {
    const stored = Number(window.localStorage.getItem(SIGNED_IN_STORAGE_KEY));
    return NURSE_IDS.some((id) => id === stored) ? stored : null;
  } catch {
    return null;
  }
}

function writeSignedIn(staffId: number | null): void {
  try {
    if (staffId === null) window.localStorage.removeItem(SIGNED_IN_STORAGE_KEY);
    else window.localStorage.setItem(SIGNED_IN_STORAGE_KEY, String(staffId));
  } catch {
    // Without storage the sign-in lasts until the page is reloaded.
  }
}

/** The header is the only identity: these routes take no staff_id. */
function myOffersApi(staffId: number): OfferApi {
  const api = createDemoApi(staffId);
  return {
    load: (signal) => api<Offer[]>("/me/offers", { signal }),
    respond: (offerId, response, signal) =>
      api<OfferResponse>(`/me/offers/${offerId}/response`, {
        method: "POST",
        json: { response },
        signal,
      }),
  };
}

/** Seeded shifts that list this person, plus the shifts of their handovers. */
function shiftsOf(staffId: number, handovers: readonly HandoverView[]): number[] {
  const seeded = DEMO_WARDS.flatMap((ward) =>
    ward.shifts.filter((shift) => shift.staffIds.includes(staffId)).map((shift) => shift.id),
  );
  const handed = handovers.flatMap((handover) => {
    const shift = handover.content.shift;
    return typeof shift === "object" && shift !== null && "id" in shift && typeof shift.id === "number"
      ? [shift.id]
      : [];
  });
  return [...new Set([...seeded, ...handed])].sort((a, b) => a - b);
}

/** Our text (a key, in the language of the user) or the words the API sent. */
type Failure = { key: MessageKey } | { text: string };

function checkInError(cause: unknown, t: Translate): Failure {
  if (!(cause instanceof ApiError)) return { key: "common.apiUnreachable" };
  if (cause.status === 404) return { key: "me.noRosterRow" };
  if (cause.status === 409) return { key: "me.shiftBusy" };
  return { text: describeError(cause, t) };
}

/** Check in for yourself (section 6.24). The backend clock decides the time, not this browser. */
function CheckIn({ staffId, handovers }: { staffId: number; handovers: readonly HandoverView[] }) {
  const t = useT();
  const shifts = shiftsOf(staffId, handovers);
  const [shiftId, setShiftId] = useState<number | null>(null);
  const chosen = shiftId !== null && shifts.includes(shiftId) ? shiftId : (shifts[0] ?? null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CheckInResult | null>(null);
  const [error, setError] = useState<Failure | null>(null);

  async function checkIn() {
    if (chosen === null) return;
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      setResult(
        await createDemoApi(staffId)<CheckInResult>("/me/attendance/check-in", {
          method: "POST",
          json: { shift_id: chosen },
        }),
      );
    } catch (cause) {
      setError(checkInError(cause, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={t("me.checkIn")} className="mt-4">
      {chosen === null ? (
        <p className="mt-2">{t("me.noShift")}</p>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label htmlFor="check-in-shift">{t("common.shift")}</label>
          <select
            id="check-in-shift"
            value={chosen}
            disabled={busy}
            onChange={(event) => setShiftId(Number(event.target.value))}
          >
            {shifts.map((id) => (
              <option key={id} value={id}>
                {t("roster.shiftOption", { id })}
              </option>
            ))}
          </select>
          <Button variant="primary" disabled={busy} onClick={() => void checkIn()}>
            {t("me.checkIn")}
          </Button>
        </div>
      )}
      {result && (
        <p role="status" className={result.on_time ? "mt-2 text-green-700" : "mt-2 text-amber-700"}>
          {t("me.checkedIn", {
            shift: result.shift_id,
            time: formatDateTime(result.check_in_at),
            when: t(result.on_time ? "me.onTime" : "me.late"),
            deadline: formatDateTime(result.deadline),
          })}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-red-700">
          {t("me.checkInFailed", { error: "text" in error ? error.text : t(error.key) })}
        </p>
      )}
    </Card>
  );
}

function DemoSignIn({ onSignIn }: { onSignIn: (staffId: number) => void }) {
  const t = useT();
  const [choice, setChoice] = useState<number>(NURSE_IDS[0]);
  function submit(event: FormEvent) {
    event.preventDefault();
    onSignIn(choice);
  }
  return (
    <form onSubmit={submit} className="max-w-md space-y-3 rounded-xl border border-t-4 border-slate-200 border-t-brand-500 bg-white p-4 shadow-md">
      <p>{t("me.demoSignIn")}</p>
      <label className="block" htmlFor="demo-staff">
        {t("sim.staffMember")}
      </label>
      <select
        id="demo-staff"
        value={choice}
        onChange={(event) => setChoice(Number(event.target.value))}
      >
        {NURSE_IDS.map((id) => (
          <option key={id} value={id}>
            {t("sim.staffOption", { id })}
          </option>
        ))}
      </select>
      <div>
        <Button type="submit" variant="primary">
          {t("me.signInButton")}
        </Button>
      </div>
    </form>
  );
}

function SignedIn({ staffId, onSignOut }: { staffId: number; onSignOut: () => void }) {
  const t = useT();
  const [responding, setResponding] = useState(false);
  const api = useMemo(() => myOffersApi(staffId), [staffId]);
  const handovers = useHandoverHistory(staffId);
  const handoverRows = handovers.data
    ? [...handovers.data.active, ...handovers.data.history].filter(isHandover)
    : [];
  return (
    <>
      <div
        role="note"
        className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-900"
      >
        <span>{t("me.demoMode", { id: staffId })}</span>
        <Button disabled={responding} onClick={onSignOut}>
          {t("me.signOut")}
        </Button>
      </div>
      <p className="mt-4">
        {t("me.acceptNote", { seconds: DEFAULT_POLL_INTERVAL_MS / 1000 })}
      </p>
      <OfferList
        staffId={staffId}
        api={api}
        emptyText={t("me.noOffers")}
        onPendingChange={setResponding}
      />
      <CheckIn staffId={staffId} handovers={handoverRows} />
      <Card title={t("me.handovers")} className="mt-4">
        {handovers.error && handovers.data === undefined ? (
          <p role="alert" className="mt-2 text-red-700">
            {t("me.handoverLoadFailed")}
          </p>
        ) : (
          <>
            {handovers.error && (
              <p role="alert" className="mt-2 text-sm text-amber-700">
                {handovers.loadMoreError
                  ? t("me.handoverMoreFailed")
                  : t("me.handoverRefreshFailed")}
              </p>
            )}
            {handovers.isLoading ? (
              <p className="mt-2">{t("me.handoverLoading")}</p>
            ) : (
              <HandoverList handovers={handoverRows} emptyText={t("me.noHandovers")} />
            )}
            {handovers.data?.next_cursor && (
              <Button
                className="mt-3"
                disabled={handovers.loadingMore}
                onClick={() => void handovers.loadMore()}
              >
                {handovers.loadingMore ? t("me.loadingMore") : t("me.loadMore")}
              </Button>
            )}
          </>
        )}
      </Card>
    </>
  );
}

export default function MyOffersPage() {
  const t = useT();
  // undefined until storage is read in the browser, so the server render matches.
  const [staffId, setStaffId] = useState<number | null | undefined>(undefined);
  useEffect(() => setStaffId(readSignedIn()), []);

  function signIn(id: number) {
    writeSignedIn(id);
    setStaffId(id);
  }

  function signOut() {
    writeSignedIn(null);
    setStaffId(null);
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("me.title")} />
      {staffId === null && <DemoSignIn onSignIn={signIn} />}
      {typeof staffId === "number" && (
        <SignedIn key={staffId} staffId={staffId} onSignOut={signOut} />
      )}
    </main>
  );
}
