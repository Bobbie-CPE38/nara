"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { PendingApproval } from "@/lib/types/approval";
import type { CasePage } from "@/lib/types/handoff";

/** How often the bell reads the work that waits; fast enough to notice, light on the API */
export const ALERT_POLL_MS = 15000;
const TOAST_MS = 10000;
const SEEN_KEY = "nara.alerts.seen";
// Moved by every demo reset of this browser, in every tab: see newAlertGeneration
const GENERATION_KEY = "nara.alerts.generation";
// In demo mode there is no login: the bell reads as the Supervisor, who sees every ward
const DEMO_READER = 950;
// The newest handed-off cases, so a new one is always in the list; the rest are on /handoff
const HANDOFF_URL = "/cases/search?page=1&page_size=20&sort=newest&status=MANUAL_HANDOFF";

type Alert = { key: string; kind: "handoff" | "approval"; caseId: number; staffId?: number };
type Seen = { generation: string; keys: string[] };

function generation(): string {
  try {
    return window.localStorage.getItem(GENERATION_KEY) ?? "";
  } catch {
    return "";
  }
}

/**
 * A demo reset starts the case and approval IDs again, so a new alert can have the key of one
 * this tab already showed. The Demo control calls this after a reset or the start of a test run:
 * every tab of the browser then forgets what it showed.
 */
export function newAlertGeneration(): void {
  try {
    window.localStorage.setItem(GENERATION_KEY, String(Date.now()));
  } catch {
    // Without storage the keys still hold the time each case or request was made
  }
}

/** What this tab showed to this account, since the last reset */
function readSeen(account: string): Set<string> {
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(`${SEEN_KEY}.${account}`) ?? "null") as Seen | null;
    return new Set(stored && stored.generation === generation() ? stored.keys : []);
  } catch {
    return new Set();
  }
}

function writeSeen(account: string, seen: Set<string>): void {
  try {
    const stored: Seen = { generation: generation(), keys: [...seen].slice(-200) };
    window.sessionStorage.setItem(`${SEEN_KEY}.${account}`, JSON.stringify(stored));
  } catch {
    // A private window without storage only shows the toasts again on the next page
  }
}

/**
 * The work that waits for a head nurse or a supervisor, like the badge of a chat app (round 6 PR
 * EV7, docs/workflow.md 6.37.5): a bell with the number of handed-off cases and approval
 * requests, its list, and a toast that pops up when a new one arrives. A toast is shown once
 * per browser tab and account. The lists are the same reads as the Handoff and Approvals pages,
 * so the Backend decides what each user may see (a Supervisor's approvals only once they may
 * decide).
 *
 * Another account, or none, is a new bell: its toasts, timers and lists start empty, so nothing
 * of the account before is left on the screen.
 */
export function Alerts() {
  const { state } = useAuth();
  const account =
    state.status === "demo"
      ? "demo"
      : state.status === "authenticated" &&
          !state.me.must_change_password &&
          (state.me.role === "head_nurse" || state.me.role === "supervisor")
        ? String(state.me.staff_id)
        : null;
  if (account === null) return null;
  return <AlertsOf key={account} account={account} />;
}

function AlertsOf({ account }: { account: string }) {
  const t = useT();
  const api = useMemo(() => createDemoApi(DEMO_READER), []);

  const loadHandoffs = useCallback((signal: AbortSignal) => api<CasePage>(HANDOFF_URL, { signal }), [api]);
  const loadApprovals = useCallback(
    (signal: AbortSignal) => api<PendingApproval[]>("/approvals?pending=true", { signal }),
    [api],
  );
  const handoffs = usePolling(loadHandoffs, { intervalMs: ALERT_POLL_MS });
  const approvals = usePolling(loadApprovals, { intervalMs: ALERT_POLL_MS });

  const alerts: Alert[] = useMemo(
    () => [
      // The time each was made is in the key too, so a reused ID is still a new alert
      ...(handoffs.data?.items ?? []).map((row) => ({
        key: `handoff:${row.id}:${row.created_at}`,
        kind: "handoff" as const,
        caseId: row.id,
      })),
      ...(Array.isArray(approvals.data) ? approvals.data : []).map((row) => ({
        key: `approval:${row.id}:${row.requested_at}`,
        kind: "approval" as const,
        caseId: row.case_id,
        staffId: row.staff_id,
      })),
    ],
    [handoffs.data, approvals.data],
  );
  const handoffTotal = handoffs.data?.total ?? 0;
  const approvalTotal = Array.isArray(approvals.data) ? approvals.data.length : 0;
  const count = handoffTotal + approvalTotal;

  const [open, setOpen] = useState(false);
  const [toasts, setToasts] = useState<Alert[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((key: string) => {
    setToasts((current) => current.filter((toast) => toast.key !== key));
    clearTimeout(timers.current.get(key));
    timers.current.delete(key);
  }, []);

  // A new alert pops up once; the ones this tab already showed stay in the bell only
  useEffect(() => {
    if (alerts.length === 0) return;
    const seen = readSeen(account);
    const fresh = alerts.filter((alert) => !seen.has(alert.key));
    if (fresh.length === 0) return;
    fresh.forEach((alert) => seen.add(alert.key));
    writeSeen(account, seen);
    setToasts((current) => [...current, ...fresh].slice(-3));
    for (const alert of fresh) {
      timers.current.set(alert.key, setTimeout(() => dismiss(alert.key), TOAST_MS));
    }
  }, [account, alerts, dismiss]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => clearTimeout(timer));
  }, []);

  const text = (alert: Alert) =>
    alert.kind === "handoff"
      ? t("alerts.handoff", { id: alert.caseId })
      : t("alerts.approval", { staff: alert.staffId ?? "", id: alert.caseId });
  const href = (alert: Alert) => (alert.kind === "handoff" ? `/cases/${alert.caseId}` : "/approvals");

  return (
    <div className="relative">
      <button
        type="button"
        className="relative rounded-lg px-2 py-1 text-slate-700 hover:bg-brand-50"
        aria-label={t("alerts.label", { count })}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {count > 0 && (
          <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-red-600 px-1 text-center text-xs font-bold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 max-w-[90vw] rounded-xl border border-slate-200 bg-white p-2 shadow-xl">
          <p className="px-2 py-1 text-sm font-semibold text-brand-800">{t("alerts.title")}</p>
          {alerts.length === 0 ? (
            <p className="px-2 py-2 text-sm text-slate-600">{t("alerts.none")}</p>
          ) : (
            <ul className="max-h-72 overflow-y-auto">
              {alerts.map((alert) => (
                <li key={alert.key}>
                  <Link
                    href={href(alert)}
                    className="block rounded-lg px-2 py-2 text-sm hover:bg-brand-50"
                    onClick={() => setOpen(false)}
                  >
                    {text(alert)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {/* The bell lists the newest 20 handed-off cases; the full lists are their pages */}
          <div className="mt-1 flex flex-wrap gap-x-4 border-t border-slate-100 px-2 pt-2 text-sm">
            <Link href="/handoff" className="text-brand-700 underline" onClick={() => setOpen(false)}>
              {t("alerts.allHandoffs", { count: handoffTotal })}
            </Link>
            <Link href="/approvals" className="text-brand-700 underline" onClick={() => setOpen(false)}>
              {t("alerts.allApprovals", { count: approvalTotal })}
            </Link>
          </div>
        </div>
      )}
      <div className="fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.key}
            role="status"
            className="flex items-start gap-3 rounded-xl border border-red-200 bg-white p-3 shadow-xl ring-1 ring-red-100"
          >
            <span aria-hidden="true" className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-red-600" />
            <Link href={href(toast)} className="flex-1 text-sm font-medium text-ink" onClick={() => dismiss(toast.key)}>
              {text(toast)}
            </Link>
            <button
              type="button"
              className="rounded px-1 text-slate-500 hover:bg-slate-100"
              aria-label={t("common.close")}
              onClick={() => dismiss(toast.key)}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
