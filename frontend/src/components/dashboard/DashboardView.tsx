"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ScrollX } from "@/components/ScrollX";
import { WardFilter } from "@/components/dashboard/WardFilter";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { CASE_STATUS_INFO, type StatusTone } from "@/lib/constants";
import { wardName, withActor } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type { MessageKey, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type {
  Dashboard,
  DashboardSummary,
  NamedGap,
  PendingApprovalCount,
  WardShortage,
} from "@/lib/types/dashboard";

/** The window of the shortages when an older Backend does not say (DASHBOARD_SHORTAGE_WINDOW_HOURS) */
const DEFAULT_WINDOW_HOURS = 24;
const URGENT_ID = "urgent-shifts";
const BY_WARD_ID = "shortage-by-ward";

/** The page that lists the cases of a status. Only these statuses have one. */
const STATUS_PAGES: ReadonlyMap<string, string> = new Map([
  ["MANUAL_HANDOFF", "/handoff"],
  ["FAILED", "/handoff"],
  ["WAITING_APPROVAL", "/approvals"],
]);

type GroupKey = "running" | "resolved" | "handoff" | "unresolved" | "failed";

/**
 * The five groups of the case chart (round 6 PR EV8, docs/workflow.md 6.38.4). The colour is a
 * state, from the status set of the charts guide; the icon and the label carry it as well, so
 * no group is told by its colour alone.
 */
const GROUPS: readonly { key: GroupKey; statuses: readonly string[]; color: string; icon: ReactNode }[] = [
  {
    key: "running",
    statuses: ["OPEN", "ASSESSING", "OPTIMIZING", "OUTREACH", "WAITING_RESPONSE", "SAFETY_VALIDATION", "WAITING_APPROVAL", "EXECUTING"],
    color: "#3475ea",
    icon: <path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4" />,
  },
  { key: "resolved", statuses: ["RESOLVED"], color: "#0ca30c", icon: <path d="M5 12.5l4.5 4.5L19 7.5" /> },
  { key: "handoff", statuses: ["MANUAL_HANDOFF"], color: "#fab219", icon: <path d="M12 4l9 16H3zM12 10v4M12 17v.5" /> },
  { key: "unresolved", statuses: ["UNRESOLVED"], color: "#ec835a", icon: <path d="M6 12h12" /> },
  { key: "failed", statuses: ["FAILED"], color: "#d03b3b", icon: <path d="M7 7l10 10M17 7L7 17" /> },
];

const GROUP_LABEL: Record<GroupKey, MessageKey> = {
  running: "dash.group.running",
  resolved: "dash.group.resolved",
  handoff: "dash.group.handoff",
  unresolved: "dash.group.unresolved",
  failed: "dash.group.failed",
};

/** The ward's name from the Dashboard's own list; the seed's table for an older Backend. */
function nameOf(data: Dashboard, wardId: number): string {
  return data.ward_options?.find((option) => option.id === wardId)?.name ?? wardName(wardId);
}

/** Minutes are enough on a dashboard: the seconds of the API time are left out */
function minutes(iso: string): string {
  return formatDateTime(iso).slice(0, 16);
}

function gapsText(gaps: NamedGap[]): string {
  return gaps.length === 0 ? "—" : gaps.map((gap) => `${gap.gap_count} ${gap.name}`).join(", ");
}

function windowHours(data: Dashboard): number {
  return data.window_hours ?? DEFAULT_WINDOW_HOURS;
}

/** The end of the window of the shortages, as a Backend Clock time */
function windowEnd(data: Dashboard): string {
  const end = new Date(new Date(data.now).getTime() + windowHours(data) * 3_600_000);
  return Number.isNaN(end.getTime()) ? data.now : end.toISOString();
}

/** The cards from an older Backend that sends no summary: the same numbers from the lists */
function summaryOf(data: Dashboard): DashboardSummary {
  if (data.summary) return data.summary;
  return {
    short_shifts: data.shortages.length,
    missing_positions: data.shortages.reduce((sum, row) => sum + row.headcount_gap, 0),
    pending_approvals: data.pending_approvals.reduce((sum, row) => sum + row.count, 0),
    handoff_cases: data.cases_by_status.find((row) => row.status === "MANUAL_HANDOFF")?.count ?? 0,
  };
}

function byWardOf(data: Dashboard): WardShortage[] {
  if (data.shortage_by_ward) return data.shortage_by_ward;
  const totals = new Map<number, WardShortage>();
  for (const row of data.shortages) {
    const total = totals.get(row.ward_id) ?? { ward_id: row.ward_id, missing_positions: 0, short_shifts: 0 };
    totals.set(row.ward_id, {
      ...total,
      missing_positions: total.missing_positions + row.headcount_gap,
      short_shifts: total.short_shifts + 1,
    });
  }
  return [...totals.values()].sort((a, b) => b.missing_positions - a.missing_positions || a.ward_id - b.ward_id);
}

/** A section's heading with the time its numbers cover, so no number is read for another period */
function Range({ children }: { children: ReactNode }) {
  return <p className="mt-0.5 text-xs text-slate-500">{children}</p>;
}

function CaseLink({ caseId }: { caseId: number | null }) {
  const t = useT();
  if (caseId === null) return <>{t("dash.noCaseYet")}</>;
  return (
    <Link className="underline" href={`/cases/${caseId}`}>
      {t("dash.caseLink", { id: caseId })}
    </Link>
  );
}

const TILE_TONE: Record<StatusTone, string> = {
  bad: "border-l-red-500",
  waiting: "border-l-amber-500",
  ok: "border-l-green-600",
  neutral: "border-l-brand-400",
};

/** One card of the top row: a number, what it counts and for when, and the list it opens */
function SummaryTile({
  label,
  value,
  note,
  href,
  tone,
}: {
  label: string;
  value: number;
  note: string;
  href: string;
  tone: StatusTone;
}) {
  const body = (
    <>
      <span className="block text-sm font-medium text-slate-700">{label}</span>
      <span className="mt-1 block text-3xl font-semibold text-ink">{value}</span>
      <span className="mt-1 block text-xs text-slate-500">{note}</span>
    </>
  );
  const className = `block h-full rounded-xl border border-l-4 border-slate-200 bg-white p-3 no-underline shadow-sm transition-colors hover:bg-brand-50 sm:p-4 ${
    value > 0 ? TILE_TONE[tone] : TILE_TONE.neutral
  }`;
  // An in-page list is an anchor; another page is a link of the app
  return href.startsWith("#") ? (
    <a className={className} href={href}>
      {body}
    </a>
  ) : (
    <Link className={className} href={href}>
      {body}
    </Link>
  );
}

function SummaryCards({ data, actorId }: { data: Dashboard; actorId: number }) {
  const t = useT();
  const summary = summaryOf(data);
  const hours = windowHours(data);
  return (
    <section aria-label={t("dash.summary")}>
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <li>
          <SummaryTile
            label={t("dash.card.shortShifts", { hours })}
            value={summary.short_shifts}
            note={t("dash.card.shortShiftsNote", { hours })}
            href={`#${URGENT_ID}`}
            tone="bad"
          />
        </li>
        <li>
          <SummaryTile
            label={t("dash.card.positions")}
            value={summary.missing_positions}
            note={t("dash.card.positionsNote", { hours })}
            href={`#${BY_WARD_ID}`}
            tone="bad"
          />
        </li>
        <li>
          <SummaryTile
            label={t("dash.card.approvals")}
            value={summary.pending_approvals}
            note={t("dash.card.now")}
            href={withActor("/approvals", actorId)}
            tone="waiting"
          />
        </li>
        <li>
          <SummaryTile
            label={t("dash.card.handoff")}
            value={summary.handoff_cases}
            note={t("dash.card.now")}
            href={withActor("/handoff", actorId)}
            tone="waiting"
          />
        </li>
      </ul>
    </section>
  );
}

/**
 * Positions still missing by ward, the most first (round 6 PR EV8): one series, so one colour
 * and no legend; the value sits at the tip of each bar. A bar picks its ward for the whole page.
 */
function WardChart({ data, onPick }: { data: Dashboard; onPick: (wardId: number) => void }) {
  const t = useT();
  const rows = byWardOf(data);
  const most = Math.max(1, ...rows.map((row) => row.missing_positions));
  return (
    <Card label={t("dash.chart.byWard")} title={t("dash.chart.byWard")}>
      <div id={BY_WARD_ID} className="scroll-mt-28">
        <Range>{t("dash.range.window", { until: minutes(windowEnd(data)), hours: windowHours(data) })}</Range>
        {rows.length === 0 ? (
          <p className="mt-3 font-medium text-green-700">{t("dash.chart.byWardEmpty")}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {rows.map((row) => {
              const name = nameOf(data, row.ward_id);
              const label = t("dash.chart.wardBar", {
                ward: name,
                positions: row.missing_positions,
                shifts: row.short_shifts,
              });
              return (
                <li key={row.ward_id}>
                  <button
                    type="button"
                    aria-label={label}
                    title={label}
                    onClick={() => onPick(row.ward_id)}
                    className="grid w-full grid-cols-[minmax(4.5rem,8rem)_1fr_auto] items-center gap-x-2 rounded-md border-0 bg-transparent px-1 py-1 text-left shadow-none hover:bg-brand-50"
                  >
                    <span className="break-words text-sm text-slate-700">{name}</span>
                    <span className="block border-l border-slate-300">
                      <span
                        className="block h-4 rounded-r bg-brand-600"
                        style={{ width: `${(row.missing_positions / most) * 100}%` }}
                      />
                    </span>
                    <span className="min-w-6 text-right text-sm font-semibold tabular-nums text-ink">
                      {row.missing_positions}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <p className="mt-3 text-xs text-slate-500">{t("dash.unitNote")}</p>
        {rows.length > 0 && <p className="mt-1 text-xs text-slate-500">{t("dash.chart.byWardHint")}</p>}
      </div>
    </Card>
  );
}

function GroupIcon({ group }: { group: (typeof GROUPS)[number] }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke={group.color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      {group.icon}
    </svg>
  );
}

/** Cases by group of status (round 6 PR EV8), with every status of a group in a part that opens */
function StatusChart({ data, actorId }: { data: Dashboard; actorId: number }) {
  const t = useT();
  const count = new Map(data.cases_by_status.map((row) => [row.status, row.count]));
  const groups = GROUPS.map((group) => ({
    group,
    total: group.statuses.reduce((sum, status) => sum + (count.get(status) ?? 0), 0),
  }));
  const most = Math.max(1, ...groups.map((row) => row.total));
  const none = groups.every((row) => row.total === 0);
  return (
    <Card label={t("dash.casesByStatus")} title={t("dash.casesByStatus")}>
      <Range>{t("dash.range.allCases")}</Range>
      {none ? (
        <p className="mt-3">{t("dash.chart.noCases")}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {groups.map(({ group, total }) => (
            <li
              key={group.key}
              className="grid grid-cols-[minmax(7rem,11rem)_1fr_auto] items-center gap-x-2 px-1 py-1"
              title={`${t(GROUP_LABEL[group.key])}: ${total}`}
            >
              <span className="flex items-center gap-1.5 text-sm text-slate-700">
                <GroupIcon group={group} />
                {t(GROUP_LABEL[group.key])}
              </span>
              <span className="block border-l border-slate-300">
                {total > 0 && (
                  <span className="block h-4 rounded-r" style={{ width: `${(total / most) * 100}%`, backgroundColor: group.color }} />
                )}
              </span>
              <span className="min-w-6 text-right text-sm font-semibold tabular-nums text-ink">{total}</span>
            </li>
          ))}
        </ul>
      )}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer font-medium text-brand-700">{t("dash.statusDetails")}</summary>
        <ul className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
          {data.cases_by_status.map(({ status, count: value }) => {
            const page = STATUS_PAGES.get(status);
            const info = CASE_STATUS_INFO.get(status);
            return (
              <li key={status} className="flex min-w-0 flex-wrap items-baseline gap-x-2 rounded-lg border border-slate-200 px-3 py-1.5">
                {page ? (
                  <Link className="font-mono text-xs underline" href={withActor(page, actorId)}>
                    {status}
                  </Link>
                ) : (
                  <span className="font-mono text-xs">{status}</span>
                )}
                {info && <span className="text-xs text-slate-500">{t(info.messageKey)}</span>}
                <span className="ml-auto font-semibold tabular-nums">{value}</span>
              </li>
            );
          })}
        </ul>
      </details>
    </Card>
  );
}

function UrgentShifts({ data, actorId }: { data: Dashboard; actorId: number }) {
  const t = useT();
  const total = summaryOf(data).short_shifts;
  return (
    <Card label={t("dash.shortShifts")} title={t("dash.shortShifts")}>
      <div id={URGENT_ID} className="scroll-mt-28">
        <Range>{t("dash.range.urgent", { until: minutes(windowEnd(data)), hours: windowHours(data) })}</Range>
        <p className="mt-1 text-sm text-slate-600">
          {t("dash.shortShiftsHelpBefore")}
          <Link className="underline" href={withActor("/gap", actorId)}>{t("nav.gap")}</Link>
          {t("dash.shortShiftsHelpAfter")}
        </p>
        {data.shortages.length === 0 ? (
          <p className="mt-3 font-medium text-green-700">{t("dash.noShortShift")}</p>
        ) : (
          <>
            <ScrollX>
              <table aria-label={t("dash.shortShifts")} className="mt-3">
                <thead>
                  <tr>
                    <th>{t("common.ward")}</th>
                    <th>{t("dash.when")}</th>
                    <th>{t("dash.shortBy")}</th>
                    <th>{t("dash.roles")}</th>
                    <th>{t("dash.skills")}</th>
                    <th>{t("common.case")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.shortages.map((row) => (
                    <tr key={row.shift_id}>
                      <td>{nameOf(data, row.ward_id)}</td>
                      <td className="whitespace-nowrap">
                        {minutes(row.start_at)} – {minutes(row.end_at).slice(11)}
                        <span className="block text-xs text-slate-500">
                          {t("roster.shiftOption", { id: row.shift_id })}
                          {row.in_progress && (
                            <span className="ml-2">
                              <Badge tone="bad">{t("dash.inProgress")}</Badge>
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="font-semibold text-red-700">{row.headcount_gap}</td>
                      <td>{gapsText(row.role_gaps)}</td>
                      <td>{gapsText(row.skill_gaps)}</td>
                      <td>
                        <CaseLink caseId={row.case_id} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollX>
            {total > data.shortages.length && (
              <p className="mt-2 text-sm text-slate-600">
                {t("dash.firstShortages", { shown: data.shortages.length, total })}
              </p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

/**
 * Who a ward's requests wait for (round 6 PR EV8): its head nurses by ID, and the Supervisor
 * once they may decide too. The Supervisor is one role for every ward, so no ID.
 */
export function waitingForText(row: PendingApprovalCount, t: Translate): string | null {
  const heads = row.head_nurses;
  if (heads === undefined) return null;
  const head = heads.length > 0 ? t("dash.headNurseIds", { ids: heads.map((person) => person.staff_id).join(", ") }) : null;
  if (head === null) return t(row.supervisor ? "dash.waitingForSupervisor" : "dash.waitingForNobody");
  return t("dash.waitingFor", { who: row.supervisor ? t("dash.orSupervisor", { who: head }) : head });
}

function Waiting({ data, actorId }: { data: Dashboard; actorId: number }) {
  const t = useT();
  return (
    <Card label={t("dash.waiting")} title={t("dash.waiting")}>
      <Range>{t("dash.card.now")}</Range>
      <p className="mt-2">{t("dash.openOffers", { count: data.open_offers.count })}</p>
      <h3 className="mt-3">{t("dash.approvalsByWard")}</h3>
      {data.pending_approvals.length === 0 ? (
        <p className="mt-1">{t("common.none")}</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {data.pending_approvals.map((row) => {
            const who = waitingForText(row, t);
            return (
              <li key={`${row.ward_id}-${row.supervisor === true}`}>
                {nameOf(data, row.ward_id)}:{" "}
                <Link className="underline" href={withActor("/approvals", actorId)}>
                  {row.count}
                </Link>
                {who && <span className="text-slate-600"> ({who})</span>}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function NoShows({ data }: { data: Dashboard }) {
  const t = useT();
  return (
    <Card label={t("dash.noShows")} title={t("dash.noShows")}>
      <Range>{t("dash.range.noShows")}</Range>
      {data.recent_no_show.length === 0 ? (
        <p className="mt-2">{t("common.none")}</p>
      ) : (
        <ScrollX>
          <table aria-label={t("dash.noShows")} className="mt-3">
            <thead>
              <tr>
                <th>{t("dash.recordedAt")}</th>
                <th>{t("common.staff")}</th>
                <th>{t("common.shift")}</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_no_show.map((row) => (
                <tr key={row.event_id}>
                  <td>{formatDateTime(row.created_at)}</td>
                  <td>{row.staff_id}</td>
                  <td>{row.shift_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollX>
      )}
    </Card>
  );
}

/** Today's DEMO attempts against the cap and this month's cost against the budget (6.27, 6.28). */
function LlmUsageSection({ data }: { data: Dashboard }) {
  const t = useT();
  const usage = data.llm_usage;
  if (usage === null) return null;
  const overBudget = Number(usage.month_cost_usd) >= Number(usage.budget_usd);
  return (
    <Card label={t("llm.title")} title={t("llm.title")}>
      <p className="mt-2">
        {t("llm.today", { date: usage.date, used: usage.used, cap: usage.cap })}
        {usage.used >= usage.cap && <span className="ml-2 font-semibold text-red-700">{t("llm.dailyLimit")}</span>}
      </p>
      <p className="mt-1">
        {t("llm.month", { cost: usage.month_cost_usd, budget: usage.budget_usd })}
        {overBudget && <span className="ml-2 font-semibold text-red-700">{t("llm.budgetReached")}</span>}
      </p>
      {usage.month_calls_without_cost > 0 && (
        <p className="mt-1 text-sm text-amber-700">
          {t("llm.noCost", { count: usage.month_calls_without_cost })}
        </p>
      )}
    </Card>
  );
}

/**
 * `actorId` is the user the numbers are for: the links open the next page for the same user.
 * `wardId` is the ward the numbers are narrowed to, null for every ward (round 6 PR EV6). The
 * ward filter scopes every card, chart and list below it (round 6 PR EV8, 6.38.4); the Backend
 * already limits all of them to the wards the user may see.
 * The clock is in the top bar and the modes are no business of a nurse: neither shows here.
 */
export function DashboardView({
  data,
  actorId,
  wardId = null,
  onWardChange,
}: {
  data: Dashboard;
  actorId: number;
  wardId?: number | null;
  onWardChange?: (wardId: number | null) => void;
}) {
  const t = useT();
  function pickWard(id: number) {
    onWardChange?.(id);
    // The shifts of the ward are in the urgent list; a browser without scrollIntoView stays put
    document.getElementById(URGENT_ID)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <WardFilter
          options={data.ward_options ?? data.wards.map((id) => ({ id, name: wardName(id) }))}
          value={wardId}
          onChange={(id) => onWardChange?.(id)}
        />
        {data.demo_data && (
          <span title={t("dash.demoDataNote")}>
            <Badge tone="waiting">{t("dash.demoData")}</Badge>
          </span>
        )}
      </div>
      <SummaryCards data={data} actorId={actorId} />
      <div className="grid gap-4 lg:grid-cols-2">
        <WardChart data={data} onPick={pickWard} />
        <StatusChart data={data} actorId={actorId} />
      </div>
      <UrgentShifts data={data} actorId={actorId} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Waiting data={data} actorId={actorId} />
        <NoShows data={data} />
      </div>
      <LlmUsageSection data={data} />
    </div>
  );
}
