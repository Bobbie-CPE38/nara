"use client";

import { createContext, useCallback, useContext, type ReactNode } from "react";
import { usePolling } from "@/hooks/usePolling";
import { apiRequest } from "@/lib/api";
import type { ClockView } from "@/lib/types/attendance";

type ClockState = { data: ClockView | undefined; error: Error | null };

const ClockContext = createContext<ClockState>({ data: undefined, error: null });

/**
 * The one read of GET /clock for the whole page, every second (round 6 PR UI2). The top bar
 * and the freeze buttons of the control page take the answer from here, so the Backend gets
 * one request a second from a page, not two.
 */
export function ClockProvider({ children }: { children: ReactNode }) {
  const load = useCallback((signal: AbortSignal) => apiRequest<ClockView>("/clock", { signal }), []);
  const { data, error } = usePolling(load, { intervalMs: 1000 });
  return <ClockContext.Provider value={{ data, error }}>{children}</ClockContext.Provider>;
}

export function useBackendClock(): ClockState {
  return useContext(ClockContext);
}
