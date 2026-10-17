import Link from "next/link";
import { CASE_STATUS_INFO, TONE_CLASS } from "@/lib/constants";
import { wardName, withActor } from "@/lib/demo";
import { formatDateTime } from "@/lib/format";
import type { Dashboard, NamedGap } from "@/lib/types/dashboard";

/** Statuses that need a person, shown first and in red or amber (docs/workflow.md, 6.31). */
const ATTENTION_STATUSES: ReadonlySet<string> = new Set(["MANUAL_HANDOFF", "FAILED"]);

/** The page that lists the cases of a status. Only these statuses have one. */
const STATUS_PAGES: ReadonlyMap<string, string> = new Map([
  ["MANUAL_HANDOFF", "/handoff"],
  ["FAILED", "/handoff"],
  ["WAITING_APPROVAL", "/approvals"],
]);

function gapsText(gaps: NamedGap[]): string {
  return gaps.length === 0 ? "—" : gaps.map((gap) => `${gap.gap_count} ${gap.name}`).join(", ");
}

function CaseLink({ caseId }: { caseId: number | null }) {
  if (caseId === null) return <>No case yet</>;
  return (
    <Link className="underline" href={`/cases/${caseId}`}>
      Case {caseId}
    </Link>
  );
}

function Counts({ data, actorId }: { data: Dashboard; actorId: number }) {
  return (
    <section aria-label="Cases by status" className="mt-6">
      <h2 className="text-xl font-semibold">Cases by status</h2>
      <ul className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
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
            <li key={status} className={attention ? `font-semibold ${TONE_CLASS[tone]}` : undefined}>
              {label}: {count}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Shortages({ data, actorId }: { data: Dashboard; actorId: number }) {
  return (
    <section aria-label="Short shifts" className="mt-6">
      <h2 className="text-xl font-semibold">Short shifts</h2>
      <p className="mt-1 text-sm">
        Shifts in progress or starting within 24 hours that need people now. To check any other
        shift, use <Link className="underline" href={withActor("/gap", actorId)}>Gap check</Link>.
      </p>
      {data.shortages.length === 0 ? (
        <p className="mt-2 text-green-700">No shift is short.</p>
      ) : (
        <table aria-label="Short shifts" className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th className="py-1 pr-4">Shift</th>
              <th className="py-1 pr-4">Ward</th>
              <th className="py-1 pr-4">From</th>
              <th className="py-1 pr-4">Until</th>
              <th className="py-1 pr-4">Short by</th>
              <th className="py-1 pr-4">Roles</th>
              <th className="py-1 pr-4">Skills</th>
              <th className="py-1 pr-4">Case</th>
            </tr>
          </thead>
          <tbody>
            {data.shortages.map((row) => (
              <tr key={row.shift_id}>
                <td className="py-1 pr-4">{row.shift_id}</td>
                <td className="py-1 pr-4">{wardName(row.ward_id)}</td>
                <td className="py-1 pr-4">{formatDateTime(row.start_at)}</td>
                <td className="py-1 pr-4">{formatDateTime(row.end_at)}</td>
                <td className="py-1 pr-4 text-red-700">{row.headcount_gap}</td>
                <td className="py-1 pr-4">{gapsText(row.role_gaps)}</td>
                <td className="py-1 pr-4">{gapsText(row.skill_gaps)}</td>
                <td className="py-1 pr-4">
                  <CaseLink caseId={row.case_id} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Waiting({ data, actorId }: { data: Dashboard; actorId: number }) {
  return (
    <section aria-label="Waiting for people" className="mt-6">
      <h2 className="text-xl font-semibold">Waiting for people</h2>
      <p className="mt-2">
        Offers sent and waiting for a reply: {data.open_offers.count}
      </p>
      <h3 className="mt-3 font-semibold">Approvals waiting by ward</h3>
      {data.pending_approvals.length === 0 ? (
        <p className="mt-1">None.</p>
      ) : (
        <ul className="mt-1">
          {data.pending_approvals.map((row) => (
            <li key={row.ward_id}>
              {wardName(row.ward_id)}:{" "}
              <Link className="underline" href={withActor("/approvals", actorId)}>
                {row.count}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NoShows({ data }: { data: Dashboard }) {
  return (
    <section aria-label="Recent no-shows" className="mt-6">
      <h2 className="text-xl font-semibold">Recent no-shows</h2>
      {data.recent_no_show.length === 0 ? (
        <p className="mt-2">None.</p>
      ) : (
        <table aria-label="Recent no-shows" className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th className="py-1 pr-4">Recorded at</th>
              <th className="py-1 pr-4">Staff</th>
              <th className="py-1 pr-4">Shift</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_no_show.map((row) => (
              <tr key={row.event_id}>
                <td className="py-1 pr-4">{formatDateTime(row.created_at)}</td>
                <td className="py-1 pr-4">{row.staff_id}</td>
                <td className="py-1 pr-4">{row.shift_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/** Today's DEMO attempts against the cap and this month's cost against the budget (6.27, 6.28). */
function LlmUsageSection({ data }: { data: Dashboard }) {
  const usage = data.llm_usage;
  if (usage === null) return null;
  const overBudget = Number(usage.month_cost_usd) >= Number(usage.budget_usd);
  return (
    <section aria-label="LLM usage" className="mt-6">
      <h2 className="text-xl font-semibold">LLM usage</h2>
      <p className="mt-2">
        Today ({usage.date}): {usage.used} of {usage.cap} calls
        {usage.used >= usage.cap && <span className="ml-2 text-red-700">Daily limit reached</span>}
      </p>
      <p className="mt-1">
        This month: {usage.month_cost_usd} of {usage.budget_usd} USD
        {overBudget && <span className="ml-2 text-red-700">Budget reached</span>}
      </p>
      {usage.month_calls_without_cost > 0 && (
        <p className="mt-1 text-sm text-amber-700">
          {usage.month_calls_without_cost} calls this month have no known cost, so the real cost
          may be higher.
        </p>
      )}
    </section>
  );
}

/** `actorId` is the user the numbers are for: the links open the next page for the same user. */
export function DashboardView({ data, actorId }: { data: Dashboard; actorId: number }) {
  return (
    <>
      <p className="mt-2 text-sm">
        Backend Clock {formatDateTime(data.now)} · LINE: {data.modes.line_mode} · LLM:{" "}
        {data.modes.llm_enabled ? data.modes.llm_provider : "off"} · Wards:{" "}
        {data.wards.map(wardName).join(", ")}
      </p>
      <Counts data={data} actorId={actorId} />
      <Shortages data={data} actorId={actorId} />
      <Waiting data={data} actorId={actorId} />
      <NoShows data={data} />
      <LlmUsageSection data={data} />
    </>
  );
}
