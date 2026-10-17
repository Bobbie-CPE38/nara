"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { HandoverList, isHandover } from "@/components/handover/HandoverList";
import { type OfferApi, OfferList } from "@/components/outreach/OfferList";
import { DEFAULT_POLL_INTERVAL_MS } from "@/hooks/usePolling";
import { ApiError, createDemoApi } from "@/lib/api";
import { useHandoverHistory } from "@/hooks/useHandoverHistory";
import {
  DEMO_APPROVERS,
  DEMO_SIGNED_IN_STORAGE_KEY as SIGNED_IN_STORAGE_KEY,
  DEMO_STAFF_IDS,
  DEMO_WARDS,
} from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
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

function checkInError(cause: unknown): string {
  if (!(cause instanceof ApiError)) return "Cannot reach the API. Check that the backend is running.";
  if (cause.status === 404) return "You have no roster row on this shift.";
  if (cause.status === 409) return "The shift is busy. Try again in a moment.";
  return cause.message;
}

/** Check in for yourself (section 6.24). The backend clock decides the time, not this browser. */
function CheckIn({ staffId, handovers }: { staffId: number; handovers: readonly HandoverView[] }) {
  const shifts = shiftsOf(staffId, handovers);
  const [shiftId, setShiftId] = useState<number | null>(null);
  const chosen = shiftId !== null && shifts.includes(shiftId) ? shiftId : (shifts[0] ?? null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CheckInResult | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      setError(checkInError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-6">
      <h2 className="text-xl font-semibold">Check in</h2>
      {chosen === null ? (
        <p className="mt-2">You have no shift to check in to.</p>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label htmlFor="check-in-shift">Shift</label>
          <select
            id="check-in-shift"
            className="rounded border border-slate-400 p-1"
            value={chosen}
            disabled={busy}
            onChange={(event) => setShiftId(Number(event.target.value))}
          >
            {shifts.map((id) => (
              <option key={id} value={id}>
                Shift {id}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rounded bg-blue-700 px-3 py-1 text-white disabled:opacity-40"
            disabled={busy}
            onClick={() => void checkIn()}
          >
            Check in
          </button>
        </div>
      )}
      {result && (
        <p role="status" className={result.on_time ? "mt-2 text-green-700" : "mt-2 text-amber-700"}>
          Checked in to shift {result.shift_id} at {formatDateTime(result.check_in_at)}:{" "}
          {result.on_time ? "on time" : "late"} (deadline {formatDateTime(result.deadline)}).
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-red-700">
          Check-in failed: {error}
        </p>
      )}
    </section>
  );
}

function DemoSignIn({ onSignIn }: { onSignIn: (staffId: number) => void }) {
  const [choice, setChoice] = useState<number>(NURSE_IDS[0]);
  function submit(event: FormEvent) {
    event.preventDefault();
    onSignIn(choice);
  }
  return (
    <form onSubmit={submit} className="mt-6 max-w-md space-y-3 rounded border border-slate-300 p-4">
      <p>
        Demo sign-in: choose who you are. This is not a real login, and anyone
        can choose any staff member.
      </p>
      <label className="block" htmlFor="demo-staff">
        Staff member
      </label>
      <select
        id="demo-staff"
        className="rounded border border-slate-400 p-2"
        value={choice}
        onChange={(event) => setChoice(Number(event.target.value))}
      >
        {NURSE_IDS.map((id) => (
          <option key={id} value={id}>
            Staff {id}
          </option>
        ))}
      </select>
      <div>
        <button type="submit" className="rounded bg-blue-700 px-3 py-2 text-white">
          Sign in (demo)
        </button>
      </div>
    </form>
  );
}

function SignedIn({ staffId, onSignOut }: { staffId: number; onSignOut: () => void }) {
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
        className="mt-4 flex flex-wrap items-center gap-3 rounded border border-amber-400 bg-amber-50 p-3"
      >
        <span>
          Demo mode: signed in as staff {staffId}. There is no real login.
        </span>
        <button
          type="button"
          className="rounded border border-slate-400 px-3 py-1 disabled:opacity-40"
          disabled={responding}
          onClick={onSignOut}
        >
          Sign out
        </button>
      </div>
      <p className="mt-4">
        Accepting an offer does not put you on the shift. You are assigned only
        after the head nurse approves and the system confirms the assignment.
        Updates every {DEFAULT_POLL_INTERVAL_MS / 1000} seconds.
      </p>
      <OfferList
        staffId={staffId}
        api={api}
        emptyText="You have no shift offers."
        onPendingChange={setResponding}
      />
      <CheckIn staffId={staffId} handovers={handoverRows} />
      <section className="mt-6">
        <h2 className="text-xl font-semibold">My handovers</h2>
        {handovers.error && handovers.data === undefined ? (
          <p role="alert" className="mt-2 text-red-700">
            Cannot load your handovers. Retrying…
          </p>
        ) : (
          <>
            {handovers.error && (
              <p role="alert" className="mt-2 text-sm text-amber-700">
                Could not refresh your handovers. Showing the last loaded list, which may be
                outdated. Retrying…
              </p>
            )}
            {handovers.isLoading ? (
              <p className="mt-2">Loading your handovers…</p>
            ) : <HandoverList handovers={handoverRows} emptyText="You have no handovers." />}
            {handovers.data?.next_cursor && (
              <button
                type="button"
                disabled={handovers.loadingMore}
                onClick={() => void handovers.loadMore()}
                className="mt-3 rounded border border-slate-400 px-3 py-2 disabled:opacity-40"
              >
                {handovers.loadingMore ? "Loading history…" : "Load more history"}
              </button>
            )}
          </>
        )}
      </section>
    </>
  );
}

export default function MyOffersPage() {
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
    <main className="mx-auto max-w-7xl p-6 text-slate-900">
      <h1 className="text-2xl font-semibold">My shift offers</h1>
      {staffId === null && <DemoSignIn onSignIn={signIn} />}
      {typeof staffId === "number" && (
        <SignedIn key={staffId} staffId={staffId} onSignOut={signOut} />
      )}
    </main>
  );
}
