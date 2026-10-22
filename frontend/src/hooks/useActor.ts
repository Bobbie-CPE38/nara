"use client";

import { useSearchParams } from "next/navigation";
import { type Dispatch, type SetStateAction, useState } from "react";
import { useSessionUser } from "@/components/AuthProvider";
import { ACTOR_QUERY, actorFromQuery } from "@/lib/demo";

const NO_CHANGE: Dispatch<SetStateAction<number>> = () => {};

/**
 * The demo user a page looks or acts as: the one a link carried in the query, else the Golden
 * Case head nurse. The page owns the choice from then on. A page that calls this must sit
 * inside a Suspense boundary (Next.js reads the query on the client).
 */
export function useActor(): [number, Dispatch<SetStateAction<number>>] {
  const params = useSearchParams();
  const chosen = useState<number>(() => actorFromQuery(params?.get(ACTOR_QUERY)));
  // With a login the person is the one logged in: there is nobody to switch to (docs/workflow.md 6.33)
  const me = useSessionUser();
  return me ? [me.staff_id, NO_CHANGE] : chosen;
}
