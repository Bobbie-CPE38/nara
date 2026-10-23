"use client";

import Link from "next/link";
import { ScrollX } from "@/components/ScrollX";
import { WardFilter } from "@/components/dashboard/WardFilter";
import { Card } from "@/components/ui/Card";
import { CASE_STATUS_INFO, TONE_CLASS } from "@/lib/constants";
import { wardName, withActor } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { Dashboard, NamedGap } from "@/lib/types/dashboard";

/** Statuses that need a person, shown first and in red or amber (docs/workflow.md, 6.31). */
const ATTENTION_STATUSES: ReadonlySet<string> = new Set(["MANUAL_HANDOFF", "FAILED"]);

/** The page that lists the cases of a status. Only these statuses have one. */
const STATUS_PAGES: ReadonlyMap<string, string> = new Map([
  ["MANUAL_HANDOFF", "/handoff"],
  ["FAILED", "/handoff"],
  ["WAITING_APPROVAL", "/approvals"],
]);

/** The tile of a status that needs a person while it has cases: the tone of the status */
const ATTENTION_TILE: Record<string, string> = {
  bad: "border-red-200 bg-red-50",
  waiting: "border-amber-200 bg-amber-50",
  ok: "border-green-200 bg-green-50",
  neutral: "border-slate-200 bg-white",
};

/** The ward's name from the Dashboard's own list; the seed's table for an older Backend. */
function nameOf(data: Dashboard, wardId: number): string {
  return data.ward_options?.find((option) => option.id === wardId)?.name ?? wardName(wardId);
}

function gapsText(gaps: NamedGap[]): string {
  return gaps.length === 0 ? "—" : gaps.map((gap) => `${gap.gap_count} ${gap.name}`).join(", ");
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

function Counts({ data, actorId }: { data: Dashboard; actorId: number }) {
  const t = useT();
  return (
    <Card label={t("dash.casesByStatus")} title={t("dash.casesByStatus")}>
      <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {data.cases_by_status.map(({ status, count }) => {
          const tone = CASE_STATUS_INFO.get(status)?.tone ?? "neutral";
          const attention = ATTENTION_STATUSES.has(status) && count > 0;
          const page = STATUS_PAGES.get(status);
          const label = page ? (
            <Link className="underline" href={withActor(page, actorId)}>
              {status}
            </Link>
          ) : (
            status
          );
          return (
            <li
              key={status}
              className={`min-w-0 break-words rounded-lg border px-3 py-2 text-sm ${
                attention ? `font-semibold ${TONE_CLASS[tone]} ${ATTENTION_TILE[tone]}` : "border-slate-200 bg-white"
              }`}
            >
              {label}: {count}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Shortages({ data, actorId }: { data: Dashboard; actorId: number }) {
  const t = useT();
  return (
    <Card label={t("dash.shortShifts")} title={t("dash.shortShifts")}>
      <p className="mt-1 text-sm text-slate-600">
        {t("dash.shortShiftsHelpBefore")}
        <Link className="underline" href={withActor("/gap", actorId)}>{t("nav.gap")}</Link>
        {t("dash.shortShiftsHelpAfter")}
      </p>
      {data.shortages.length === 0 ? (
        <p className="mt-3 font-medium text-green-700">{t("dash.noShortShift")}</p>
      ) : (
        <ScrollX>
          <table aria-label={t("dash.shortShifts")} className="mt-3">
            <thead>
              <tr>
                <th>{t("common.shift")}</th>
                <th>{t("common.ward")}</th>
                <th>{t("common.from")}</th>
                <th>{t("common.until")}</th>
                <th>{t("dash.shortBy")}</th>
                <th>{t("dash.roles")}</th>
                <th>{t("dash.skills")}</th>
                <th>{t("common.case")}</th>
              </tr>
            </thead>
            <tbody>
              {data.shortages.map((row) => (
                <tr key={row.shift_id}>
                  <td>{row.shift_id}</td>
                  <td>{nameOf(data, row.ward_id)}</td>
                  <td>{formatDateTime(row.start_at)}</td>
                  <td>{formatDateTime(row.end_at)}</td>
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
      )}
    </Card>
  );
}

function Waiting({ data, actorId }: { data: Dashboard; actorId: number }) {
  const t = useT();
  return (
    <Card label={t("dash.waiting")} title={t("dash.waiting")}>
      <p className="mt-2">{t("dash.openOffers", { count: data.open_offers.count })}</p>
      <h3 className="mt-3">{t("dash.approvalsByWard")}</h3>
      {data.pending_approvals.length === 0 ? (
        <p className="mt-1">{t("common.none")}</p>
      ) : (
        <ul className="mt-1">
          {data.pending_approvals.map((row) => (
            <li key={row.ward_id}>
              {nameOf(data, row.ward_id)}:{" "}
              <Link className="underline" href={withActor("/approvals", actorId)}>
                {row.count}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function NoShows({ data }: { data: Dashboard }) {
  const t = useT();
  return (
    <Card label={t("dash.noShows")} title={t("dash.noShows")}>
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
 * `wardId` is the ward the numbers are narrowed to, null for every ward (round 6 PR EV6).
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
  return (
    <div className="space-y-4">
      <WardFilter
        options={data.ward_options ?? data.wards.map((id) => ({ id, name: wardName(id) }))}
        value={wardId}
        onChange={(id) => onWardChange?.(id)}
      />
      <Counts data={data} actorId={actorId} />
      <Shortages data={data} actorId={actorId} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Waiting data={data} actorId={actorId} />
        <NoShows data={data} />
      </div>
      <LlmUsageSection data={data} />
    </div>
  );
}
