import type { MessageKey } from "@/lib/i18n";

/** The one time between reads. usePolling defaults to it and the "updates every N seconds" texts show it. */
export const POLL_INTERVAL_MS = 2000;

/** Same set as TERMINAL_CASE_STATUSES in backend/app/domain/enums.py. */
export const TERMINAL_CASE_STATUSES: ReadonlySet<string> = new Set([
  "RESOLVED",
  "UNRESOLVED",
  "FAILED",
]);

export type StatusTone = "ok" | "bad" | "waiting" | "neutral";

/**
 * Meaning of each case status (docs/workflow.md, section 4): the key of its text in the
 * dictionary and its tone. A Map, so an unknown status is undefined. The text itself is in
 * lib/i18n (round 6 PR UI1), so it follows the language of the page.
 */
export const CASE_STATUS_INFO: ReadonlyMap<string, { messageKey: MessageKey; tone: StatusTone }> = new Map([
  ["OPEN", { messageKey: "caseStatus.OPEN", tone: "neutral" }],
  ["ASSESSING", { messageKey: "caseStatus.ASSESSING", tone: "neutral" }],
  ["OPTIMIZING", { messageKey: "caseStatus.OPTIMIZING", tone: "neutral" }],
  ["OUTREACH", { messageKey: "caseStatus.OUTREACH", tone: "neutral" }],
  ["WAITING_RESPONSE", { messageKey: "caseStatus.WAITING_RESPONSE", tone: "waiting" }],
  ["SAFETY_VALIDATION", { messageKey: "caseStatus.SAFETY_VALIDATION", tone: "neutral" }],
  ["WAITING_APPROVAL", { messageKey: "caseStatus.WAITING_APPROVAL", tone: "waiting" }],
  ["EXECUTING", { messageKey: "caseStatus.EXECUTING", tone: "neutral" }],
  ["RESOLVED", { messageKey: "caseStatus.RESOLVED", tone: "ok" }],
  ["MANUAL_HANDOFF", { messageKey: "caseStatus.MANUAL_HANDOFF", tone: "waiting" }],
  ["UNRESOLVED", { messageKey: "caseStatus.UNRESOLVED", tone: "bad" }],
  ["FAILED", { messageKey: "caseStatus.FAILED", tone: "bad" }],
]);

export const TONE_CLASS: Record<StatusTone, string> = {
  ok: "text-green-700",
  bad: "text-red-700",
  waiting: "text-amber-700",
  neutral: "",
};

/** Where a candidate is in a case (docs/workflow.md, section 4.1). A Map, so an unknown stage is undefined. */
export const CANDIDATE_STAGE_INFO: ReadonlyMap<string, { messageKey: MessageKey; tone: StatusTone }> = new Map([
  ["NOT_CONTACTED", { messageKey: "stage.NOT_CONTACTED", tone: "neutral" }],
  ["OFFER_PENDING", { messageKey: "stage.OFFER_PENDING", tone: "neutral" }],
  ["OFFER_SENT", { messageKey: "stage.OFFER_SENT", tone: "waiting" }],
  ["OFFER_REJECTED", { messageKey: "stage.OFFER_REJECTED", tone: "neutral" }],
  ["OFFER_TIMEOUT", { messageKey: "stage.OFFER_TIMEOUT", tone: "neutral" }],
  ["OFFER_FAILED", { messageKey: "stage.OFFER_FAILED", tone: "bad" }],
  ["OFFER_CANCELLED", { messageKey: "stage.OFFER_CANCELLED", tone: "neutral" }],
  ["ACCEPTED", { messageKey: "stage.ACCEPTED", tone: "waiting" }],
  ["SAFETY_FAILED", { messageKey: "stage.SAFETY_FAILED", tone: "bad" }],
  ["WAITING_APPROVAL", { messageKey: "stage.WAITING_APPROVAL", tone: "waiting" }],
  ["APPROVAL_REJECTED", { messageKey: "stage.APPROVAL_REJECTED", tone: "bad" }],
  ["APPROVAL_TIMEOUT", { messageKey: "stage.APPROVAL_TIMEOUT", tone: "neutral" }],
  ["APPROVED", { messageKey: "stage.APPROVED", tone: "waiting" }],
  ["ASSIGNED", { messageKey: "stage.ASSIGNED", tone: "ok" }],
]);

/** Fixed reason of each score term (docs/workflow.md, section 6.15), as a dictionary key. */
export const SCORE_TERM_KEYS: ReadonlyMap<string, MessageKey> = new Map([
  ["candidate_count", "scoreTerm.candidate_count"],
  ["consecutive_shift", "scoreTerm.consecutive_shift"],
  ["workload_imbalance", "scoreTerm.workload_imbalance"],
  ["projected_overtime", "scoreTerm.projected_overtime"],
  ["candidate_source", "scoreTerm.candidate_source"],
]);

/** Round 6 PR E2 (docs/workflow.md 6.27). The AI explanation is made only when a user asks. */
/** A request that has not answered by then is given up, like a polling read (usePolling timeoutMs) */
export const EXPLANATION_REQUEST_TIMEOUT_MS = 10_000;
/** Skip reason codes (docs/database-schema.md, Candidate Skip Reasons), as dictionary keys. */
export const SKIP_REASON_KEYS: ReadonlyMap<string, MessageKey> = new Map(
  [
    "STAFF_NOT_ACTIVE",
    "ALREADY_ON_SHIFT",
    "UNAVAILABLE",
    "SHIFT_CONFLICT",
    "ROLE_MISMATCH",
    "SKILL_MISMATCH",
    "INSUFFICIENT_REST",
    "DAILY_HOURS_EXCEEDED",
    "WEEKLY_HOURS_EXCEEDED",
    "CONSECUTIVE_SHIFTS_EXCEEDED",
    "SOURCE_WARD_MINIMUM_VIOLATION",
    "OFFER_LIMIT_REACHED",
    "SOURCE_SHIFT_TAKEN",
  ].map((code) => [code, `skip.${code}` as MessageKey]),
);
