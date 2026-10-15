"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { type OfferApi, OfferList } from "@/components/outreach/OfferList";
import { DEFAULT_POLL_INTERVAL_MS } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import {
  DEMO_APPROVERS,
  DEMO_SIGNED_IN_STORAGE_KEY as SIGNED_IN_STORAGE_KEY,
  DEMO_STAFF_IDS,
} from "@/lib/demo";
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
