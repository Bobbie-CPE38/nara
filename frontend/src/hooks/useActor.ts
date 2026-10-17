"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { ACTOR_QUERY, actorFromQuery } from "@/lib/demo";

/**
 * The demo user a page looks or acts as: the one a link carried in the query, else the Golden
 * Case head nurse. The page owns the choice from then on. A page that calls this must sit
 * inside a Suspense boundary (Next.js reads the query on the client).
 */
export function useActor() {
  const params = useSearchParams();
  return useState<number>(() => actorFromQuery(params?.get(ACTOR_QUERY)));
}
