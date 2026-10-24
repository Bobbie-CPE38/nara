"use client";

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { SKIP_REASON_KEYS, type StatusTone } from "@/lib/constants";
import { formatDateTime } from "@/lib/format";
import type { MessageKey, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CaseOverview, OverviewPerson, OverviewRequest, OverviewSide } from "@/lib/types/case";

/** The id of the candidates' card on the case page: "See the candidates" jumps there */
export const CANDIDATES_ID = "candidates";

/** The handoff reasons of the workflow, said in words; any other reason as written */
const HANDOFF_REASON: Record<string, MessageKey> = {
  NO_CANDIDATE_LEFT: "overview.reason.NO_CANDIDATE_LEFT",
  NO_FEASIBLE_PLAN: "overview.reason.NO_FEASIBLE_PLAN",
  SOLVER_TIMEOUT: "overview.reason.SOLVER_TIMEOUT",
  WAVE_LIMIT_REACHED: "overview.reason.WAVE_LIMIT_REACHED",
  OUTREACH_DEADLINE_REACHED: "overview.reason.OUTREACH_DEADLINE_REACHED",
};

const OUTCOME: Record<NonNullable<CaseOverview["outcome"]>["kind"], MessageKey> = {
  MANUAL_HANDOFF: "overview.outcome.MANUAL_HANDOFF",
  CLOSED_UNRESOLVED: "overview.outcome.CLOSED_UNRESOLVED",
  FAILED: "overview.outcome.FAILED",
};

/** Role codes of the Backend (ROLE.name), said in words; any other code as written */
const ROLE_WORDS: Record<string, MessageKey> = {
  RN: "summary.role.RN",
  HEAD_NURSE: "role.headNurse",
  SUPERVISOR: "summary.role.SUPERVISOR",
};

const SHIFT_WORDS: Record<string, MessageKey> = {
  DAY: "summary.shift.DAY",
  EVENING: "summary.shift.EVENING",
  NIGHT: "summary.shift.NIGHT",
};

const SIDE_STATUS: Record<OverviewSide["status"], { key: MessageKey; tone: StatusTone }> = {
  PENDING: { key: "summary.side.PENDING", tone: "waiting" },
  APPROVED: { key: "summary.side.APPROVED", tone: "ok" },
  REJECTED: { key: "summary.side.REJECTED", tone: "bad" },
  AUTO_APPROVED: { key: "summary.side.AUTO_APPROVED", tone: "ok" },
  TIMED_OUT: { key: "summary.side.TIMED_OUT", tone: "bad" },
  NOT_NEEDED: { key: "summary.side.NOT_NEEDED", tone: "neutral" },
};

/** What the case is doing while nobody has come yet, by its status */
const STEP: Record<string, MessageKey> = {
  OPEN: "summary.step.assessing",
  ASSESSING: "summary.step.assessing",
  OPTIMIZING: "summary.step.assessing",
  OUTREACH: "summary.step.sending",
  WAITING_RESPONSE: "summary.step.waitingAnswers",
  SAFETY_VALIDATION: "summary.step.checking",
  WAITING_APPROVAL: "summary.step.waitingApproval",
  EXECUTING: "summary.step.checking",
  MANUAL_HANDOFF: "summary.step.handoff",
  UNRESOLVED: "summary.step.closed",
  FAILED: "summary.step.failed",
  RESOLVED: "summary.step.noNeed",
};

/** Statuses in which the candidates are still worth a look */
const LOOKING: ReadonlySet<string> = new Set([
  "OUTREACH",
  "WAITING_RESPONSE",
  "SAFETY_VALIDATION",
  "WAITING_APPROVAL",
  "EXECUTING",
  "MANUAL_HANDOFF",
]);

function minutes(iso: string): string {
  return formatDateTime(iso).slice(0, 16);
}

function roleWords(role: string | null, t: Translate): string | null {
  if (role === null) return null;
  const key = ROLE_WORDS[role];
  return key ? t(key) : role;
}

/** The name first, the staff ID after it in grey, and the role and home ward as badges */
function Person({ person, showRole = false, showWard = true }: { person: OverviewPerson; showRole?: boolean; showWard?: boolean }) {
  const t = useT();
  if (person.staff_id === null) return <span className="font-medium">{t("overview.system")}</span>;
  const role = showRole ? roleWords(person.role, t) : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1">
      <span className="font-semibold text-ink">{person.name}</span>
      <span className="text-sm text-slate-500">{t("summary.staffId", { id: person.staff_id })}</span>
      {role && <Badge>{role}</Badge>}
      {showWard && person.ward_name && <Badge>{t("summary.homeWard", { ward: person.ward_name })}</Badge>}
    </span>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="mt-4 first:mt-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-brand-800">{title}</h3>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  );
}

/** One short row of the summary: a bordered box that wraps on a phone */
function Row({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2">{children}</div>;
}

function eventWords(event: CaseOverview["events"][number], ward: string | null, t: Translate): string {
  if (event.event_type === "STAFF_UNAVAILABLE") {
    return t(event.reason === "NO_SHOW" ? "summary.event.NO_SHOW" : "summary.event.STAFF_UNAVAILABLE");
  }
  if (event.event_type === "PATIENT_SURGE") {
    return event.patient_count != null
      ? t("summary.event.PATIENT_SURGE_COUNT", { ward: ward ?? "", count: event.patient_count })
      : t("summary.event.PATIENT_SURGE", { ward: ward ?? "" });
  }
  if (event.event_type === "REQUIREMENT_CHANGED") return t("summary.event.REQUIREMENT_CHANGED");
  if (event.event_type === "ASSIGNMENT_CANCELLED") return t("summary.event.ASSIGNMENT_CANCELLED");
  return event.event_type;
}

function WhatHappened({ overview }: { overview: CaseOverview }) {
  const t = useT();
  const shift = overview.shift;
  return (
    <Section title={t("overview.what")}>
      {overview.events.length === 0 && <Row>—</Row>}
      {overview.events.map((event) => (
        <Row key={event.event_id}>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {event.staff && <Person person={event.staff} />}
            <span>{eventWords(event, shift?.ward_name ?? null, t)}</span>
          </p>
          {event.event_type === "ASSIGNMENT_CANCELLED" && event.reason && (
            <p className="mt-1 text-sm text-slate-600">“{event.reason}”</p>
          )}
          <p className="mt-1 text-xs text-slate-500">{t("summary.reportedAt", { at: minutes(event.occurred_at) })}</p>
        </Row>
      ))}
      {shift && (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-600">{t("summary.affectedShift")}</span>
          <Badge>{shift.ward_name}</Badge>
          <span className="font-medium">
            {SHIFT_WORDS[shift.shift_type] ? t(SHIFT_WORDS[shift.shift_type]) : shift.shift_type}
          </span>
          <span>
            {minutes(shift.start_at)} – {minutes(shift.end_at).slice(11)}
          </span>
          <span className="text-slate-500">{t("roster.shiftOption", { id: shift.shift_id })}</span>
        </p>
      )}
    </Section>
  );
}

type Arrival = {
  key: string;
  person: OverviewPerson;
  destination: string | null;
  request: OverviewRequest | null;
  result: MessageKey;
  tone: StatusTone;
};

/**
 * Who came, or is about to: every replacement on the roster, and every candidate who accepted
 * and waits for approval, each on its own with the result bound to their own request.
 */
function arrivals(overview: CaseOverview): Arrival[] {
  const requests = overview.requests ?? [];
  const destination = overview.shift?.ward_name ?? null;
  const list: Arrival[] = [];
  const done = new Set<number>();
  for (const replacement of overview.replacements) {
    const id = replacement.staff.staff_id;
    // The latest approved request of the person, so a move shows where they came from
    const request = [...requests].reverse().find((row) => row.candidate.staff_id === id && row.status === "APPROVED") ?? null;
    if (id !== null) done.add(id);
    list.push({
      key: `came-${id}-${replacement.at}`,
      person: replacement.staff,
      destination: request?.destination_ward_name ?? destination,
      request,
      result:
        replacement.how === "MANUAL"
          ? "summary.result.MANUAL"
          : replacement.how === "TRANSFERRED"
            ? "summary.result.TRANSFERRED"
            : "summary.result.APPROVED",
      tone: "ok",
    });
  }
  for (const request of requests) {
    if (request.status !== "PENDING" || done.has(request.candidate.staff_id ?? -1)) continue;
    list.push({
      key: `waiting-${request.approval_id}`,
      person: request.candidate,
      destination: request.destination_ward_name,
      request,
      result: "summary.result.WAITING",
      tone: "waiting",
    });
  }
  return list;
}

function WhoCame({ overview, caseStatus }: { overview: CaseOverview; caseStatus: string }) {
  const t = useT();
  const people = arrivals(overview);
  return (
    <Section title={t("overview.replacements")}>
      {people.length === 0 ? (
        <Row>
          <p>
            <span className="text-slate-600">{t("summary.nowStep")}</span>{" "}
            <span className="font-medium">
              {caseStatus === "WAITING_RESPONSE" || caseStatus === "OUTREACH"
                ? (overview.open_offers ?? 0) > 0
                  ? t("summary.step.waitingAnswersCount", { count: overview.open_offers ?? 0 })
                  : t(STEP[caseStatus])
                : STEP[caseStatus]
                  ? t(STEP[caseStatus])
                  : caseStatus}
            </span>
          </p>
          {LOOKING.has(caseStatus) && (
            <a className="mt-2 inline-block text-sm font-medium text-brand-700 underline" href={`#${CANDIDATES_ID}`}>
              {t("summary.seeCandidates")}
            </a>
          )}
        </Row>
      ) : (
        people.map((arrival) => {
          const home = arrival.person.ward_name;
          const crossWard = home !== null && arrival.destination !== null && home !== arrival.destination;
          const move = arrival.request?.moved_from ?? null;
          return (
            <Row key={arrival.key}>
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Person person={arrival.person} showWard={false} />
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm">
                {home && <Badge>{t("summary.homeWard", { ward: home })}</Badge>}
                {crossWard && (
                  <>
                    <span aria-hidden="true">→</span>
                    <Badge tone="waiting">{t("summary.helping", { ward: arrival.destination ?? "" })}</Badge>
                  </>
                )}
                {/* "Moved" only when they really leave a shift of their own (6.19) */}
                {move && (
                  <span className="text-slate-600">
                    {t("summary.movedFrom", {
                      ward: move.ward_name,
                      id: move.shift_id,
                      from: minutes(move.start_at).slice(11),
                      until: minutes(move.end_at).slice(11),
                    })}
                  </span>
                )}
              </p>
              <p className="mt-1 text-sm">
                <span className="text-slate-600">{t("summary.result")}</span>{" "}
                <Badge tone={arrival.tone}>{t(arrival.result)}</Badge>
              </p>
            </Row>
          );
        })
      )}
    </Section>
  );
}

/** "Head nurse of the destination ward" for a two-ward request, "Head nurse" for one ward */
function sideLabel(side: OverviewSide, twoWards: boolean, t: Translate): string {
  if (!twoWards) return t("summary.side.headNurseOf", { ward: side.ward_name });
  return t(side.side === "SOURCE" ? "summary.side.source" : "summary.side.destination", { ward: side.ward_name });
}

/**
 * The rows of one request: a ward side each, or one row when the same person (a Supervisor)
 * decided both sides the same way (round 6 PR EV8, docs/workflow.md 6.38.6).
 */
function sideRows(request: OverviewRequest): { sides: OverviewSide[]; both: boolean }[] {
  const [first, second] = request.sides;
  if (
    second !== undefined &&
    first.by !== null &&
    second.by !== null &&
    first.by.staff_id === second.by.staff_id &&
    first.status === second.status
  ) {
    return [{ sides: [first, second], both: true }];
  }
  return request.sides.map((side) => ({ sides: [side], both: false }));
}

function Decider({ side }: { side: OverviewSide }) {
  const t = useT();
  if (side.by) {
    const role = side.decided_as === "SUPERVISOR" ? t("summary.role.SUPERVISOR") : t("role.headNurse");
    return (
      <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1">
        <Person person={{ ...side.by, role: null }} showWard={false} />
        <Badge>{role}</Badge>
        {side.by.ward_name && <Badge>{t("summary.homeWard", { ward: side.by.ward_name })}</Badge>}
      </span>
    );
  }
  if (side.status !== "PENDING") return <span className="text-slate-500">—</span>;
  const heads = side.waiting_for.map((person) => `${person.name} (${person.staff_id})`).join(", ");
  return (
    <span className="text-sm text-slate-700">
      {heads ? t("summary.waitingFor", { who: heads }) : t("summary.waitingForNoHead")}
      {side.supervisor_from && (
        <span className="text-slate-500"> {t("summary.orSupervisorFrom", { at: minutes(side.supervisor_from) })}</span>
      )}
    </span>
  );
}

function Approvals({ overview }: { overview: CaseOverview }) {
  const t = useT();
  const requests = overview.requests ?? [];
  // Decisions that are not a ward side of a request: staffed by hand, closed
  const others = overview.decisions.filter((row) => row.kind === "MANUAL_ASSIGNMENT" || row.kind === "CLOSED_UNRESOLVED");
  return (
    <Section title={t("summary.approvals")}>
      {requests.length === 0 && others.length === 0 && <Row>{t("summary.noApproval")}</Row>}
      {requests.map((request) => {
        const twoWards = request.sides.length > 1;
        return (
          <Row key={request.approval_id}>
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              <span className="text-slate-600">{t("summary.forCandidate")}</span>
              <Person person={request.candidate} showWard={false} />
              {twoWards && <Badge tone="waiting">{t("summary.twoWards")}</Badge>}
            </p>
            <ul className="mt-2 space-y-2">
              {sideRows(request).map(({ sides, both }) => {
                const side = sides[0];
                const status = SIDE_STATUS[side.status];
                return (
                  <li key={sides.map((row) => row.side).join("-")} className="border-t border-slate-200 pt-2 first:border-t-0 first:pt-0">
                    <p className="text-xs font-medium text-slate-500">
                      {both ? t("summary.side.both") : sideLabel(side, twoWards, t)}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <Decider side={side} />
                      <Badge tone={status.tone}>{t(status.key)}</Badge>
                      {side.at && <span className="text-xs text-slate-500">{minutes(side.at)}</span>}
                    </div>
                    {side.reason && <p className="mt-1 text-sm text-slate-600">“{side.reason}”</p>}
                  </li>
                );
              })}
            </ul>
          </Row>
        );
      })}
      {others.map((row, index) => (
        <Row key={`other-${index}`}>
          <p className="text-xs font-medium text-slate-500">
            {t(row.kind === "MANUAL_ASSIGNMENT" ? "summary.manual" : "summary.closedBy")}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <Person person={row.by} showRole />
            {row.kind === "MANUAL_ASSIGNMENT" && row.candidate && (
              <span className="text-sm">
                {t("summary.assigned", { name: row.candidate.name, id: row.candidate.staff_id ?? "" })}
              </span>
            )}
            <span className="text-xs text-slate-500">{minutes(row.at)}</span>
          </div>
          {row.reason && <p className="mt-1 text-sm text-slate-600">“{row.reason}”</p>}
        </Row>
      ))}
    </Section>
  );
}

function WhyStopped({ outcome }: { outcome: NonNullable<CaseOverview["outcome"]> }) {
  const t = useT();
  const code = outcome.reason;
  const known = code === null ? undefined : (HANDOFF_REASON[code] ?? SKIP_REASON_KEYS.get(code));
  // A close carries the words of the person; a handoff or a failure carries a code
  const words = outcome.kind === "CLOSED_UNRESOLVED" ? (code ? `“${code}”` : null) : known ? t(known) : null;
  return (
    <Section title={t("overview.why")}>
      <Row>
        <p className={outcome.kind === "FAILED" ? "font-medium text-red-700" : "font-medium text-amber-900"}>
          {t(OUTCOME[outcome.kind])}
          {words && <span className="font-normal">: {words}</span>}
        </p>
        <details className="mt-1 text-sm">
          <summary className="cursor-pointer text-brand-700">{t("summary.details")}</summary>
          <dl className="mt-2 grid grid-cols-1 gap-x-3 gap-y-1 sm:grid-cols-[max-content_1fr]">
            {code && (
              <>
                <dt className="text-slate-500">{t(outcome.kind === "CLOSED_UNRESOLVED" ? "summary.closeReason" : "summary.code")}</dt>
                <dd className={outcome.kind === "CLOSED_UNRESOLVED" ? "" : "font-mono text-xs"}>{code}</dd>
              </>
            )}
            {outcome.by && (
              <>
                <dt className="text-slate-500">{t("overview.by")}</dt>
                <dd>
                  <Person person={outcome.by} showRole />
                </dd>
              </>
            )}
            <dt className="text-slate-500">{t("summary.when")}</dt>
            <dd>{minutes(outcome.at)}</dd>
          </dl>
        </details>
      </Row>
    </Section>
  );
}

/**
 * The replacement summary at the top of the case page (round 6 PR EV7, reworked in EV8,
 * docs/workflow.md 6.38.6): what happened, who came instead, who approved (each ward of a
 * cross-ward move on its own row), and why the case stopped. Names first, IDs after them,
 * wards and roles as badges, and words instead of codes. All of it is in the timeline too.
 */
export function CaseOverviewCard({ overview, caseStatus }: { overview: CaseOverview; caseStatus: string }) {
  const t = useT();
  return (
    <Card label={t("overview.title")} title={t("overview.title")}>
      <WhatHappened overview={overview} />
      <WhoCame overview={overview} caseStatus={caseStatus} />
      <Approvals overview={overview} />
      {overview.outcome && <WhyStopped outcome={overview.outcome} />}
    </Card>
  );
}
