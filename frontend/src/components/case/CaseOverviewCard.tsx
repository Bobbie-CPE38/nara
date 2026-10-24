"use client";

import { Card } from "@/components/ui/Card";
import { SKIP_REASON_KEYS } from "@/lib/constants";
import { formatDateTime } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CaseOverview, OverviewPerson } from "@/lib/types/case";

const HOW: Record<CaseOverview["replacements"][number]["how"], MessageKey> = {
  APPROVED: "overview.how.APPROVED",
  TRANSFERRED: "overview.how.TRANSFERRED",
  MANUAL: "overview.how.MANUAL",
};

const KIND: Record<CaseOverview["decisions"][number]["kind"], MessageKey> = {
  APPROVED: "overview.kind.APPROVED",
  REJECTED: "overview.kind.REJECTED",
  AUTO_APPROVED: "overview.kind.AUTO_APPROVED",
  APPROVAL_TIMEOUT: "overview.kind.APPROVAL_TIMEOUT",
  MANUAL_ASSIGNMENT: "overview.kind.MANUAL_ASSIGNMENT",
  CLOSED_UNRESOLVED: "overview.kind.CLOSED_UNRESOLVED",
};

const OUTCOME: Record<NonNullable<CaseOverview["outcome"]>["kind"], MessageKey> = {
  MANUAL_HANDOFF: "overview.outcome.MANUAL_HANDOFF",
  CLOSED_UNRESOLVED: "overview.outcome.CLOSED_UNRESOLVED",
  FAILED: "overview.outcome.FAILED",
};

/** The handoff reasons of the workflow, said in words; any other reason as written */
const HANDOFF_REASON: Record<string, MessageKey> = {
  NO_CANDIDATE_LEFT: "overview.reason.NO_CANDIDATE_LEFT",
  NO_FEASIBLE_PLAN: "overview.reason.NO_FEASIBLE_PLAN",
  SOLVER_TIMEOUT: "overview.reason.SOLVER_TIMEOUT",
  WAVE_LIMIT_REACHED: "overview.reason.WAVE_LIMIT_REACHED",
  OUTREACH_DEADLINE_REACHED: "overview.reason.OUTREACH_DEADLINE_REACHED",
};

function Person({ person }: { person: OverviewPerson }) {
  const t = useT();
  if (person.staff_id === null) return <span>{t("overview.system")}</span>;
  return (
    <span>
      <strong>{person.staff_id}</strong> {person.name}
      {(person.role || person.ward_name) && (
        <span className="text-slate-500"> · {[person.role, person.ward_name].filter(Boolean).join(", ")}</span>
      )}
    </span>
  );
}

/**
 * The top of the case page (round 6 PR EV7, docs/workflow.md 6.37.2): what happened, who came
 * instead, who decided (each ward of a cross-ward move on its own line) and why the case
 * stopped. Before, these were only in the timeline at the bottom.
 */
export function CaseOverviewCard({ overview }: { overview: CaseOverview }) {
  const t = useT();
  const reason = (code: string | null) => {
    if (code === null) return "—";
    const key = HANDOFF_REASON[code] ?? SKIP_REASON_KEYS.get(code);
    return key ? t(key) : code;
  };
  return (
    <Card label={t("overview.title")} title={t("overview.title")}>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-[max-content_1fr]">
        <dt className="font-medium">{t("overview.what")}</dt>
        <dd>
          {overview.events.length === 0
            ? "—"
            : overview.events.map((event) => (
                <p key={event.event_id}>
                  {event.event_type}
                  {event.staff && (
                    <>
                      {" · "}
                      <Person person={event.staff} />
                    </>
                  )}
                  <span className="text-sm text-slate-500"> · {formatDateTime(event.occurred_at)}</span>
                </p>
              ))}
        </dd>
        <dt className="font-medium">{t("overview.replacements")}</dt>
        <dd>
          {overview.replacements.length === 0
            ? t("overview.nobodyYet")
            : overview.replacements.map((row) => (
                <p key={`${row.staff.staff_id}-${row.at}`}>
                  <Person person={row.staff} /> · {t(HOW[row.how])}
                </p>
              ))}
        </dd>
        <dt className="font-medium">{t("overview.decisions")}</dt>
        <dd>
          {overview.decisions.length === 0 ? (
            "—"
          ) : (
            <ul className="space-y-1">
              {overview.decisions.map((row, index) => (
                <li key={index}>
                  <span className="font-medium">{t(KIND[row.kind])}</span>
                  {row.ward_name && (
                    <span>
                      {" "}
                      {t(row.side === "SOURCE" ? "overview.forSource" : "overview.forWard", { ward: row.ward_name })}
                    </span>
                  )}
                  {" · "}
                  {t("overview.by")} <Person person={row.by} />
                  {row.candidate && (
                    <>
                      {" · "}
                      {t("overview.candidate")} <Person person={row.candidate} />
                    </>
                  )}
                  {row.reason && <span className="text-slate-600"> · “{row.reason}”</span>}
                  <span className="text-sm text-slate-500"> · {formatDateTime(row.at)}</span>
                </li>
              ))}
            </ul>
          )}
        </dd>
        {overview.outcome && (
          <>
            <dt className="font-medium">{t("overview.why")}</dt>
            <dd className={overview.outcome.kind === "FAILED" ? "text-red-700" : "text-amber-800"}>
              {t(OUTCOME[overview.outcome.kind])}: {reason(overview.outcome.reason)}
              {overview.outcome.by && overview.outcome.by.staff_id !== null && (
                <>
                  {" · "}
                  {t("overview.by")} <Person person={overview.outcome.by} />
                </>
              )}
              <span className="text-sm text-slate-500"> · {formatDateTime(overview.outcome.at)}</span>
            </dd>
          </>
        )}
      </dl>
    </Card>
  );
}
