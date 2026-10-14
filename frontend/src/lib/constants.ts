export const POLL_INTERVAL_MS = 2000;

/** Same set as TERMINAL_CASE_STATUSES in backend/app/domain/enums.py. */
export const TERMINAL_CASE_STATUSES: ReadonlySet<string> = new Set([
  "RESOLVED",
  "UNRESOLVED",
  "FAILED",
]);

export type StatusTone = "ok" | "bad" | "waiting" | "neutral";

/** Meaning of each case status (docs/workflow.md, section 4). A Map, so an unknown status is undefined. */
export const CASE_STATUS_INFO: ReadonlyMap<string, { meaning: string; tone: StatusTone }> = new Map([
  ["OPEN", { meaning: "Case opened, a gap was found", tone: "neutral" }],
  ["ASSESSING", { meaning: "Assessing the staffing gap", tone: "neutral" }],
  ["OPTIMIZING", { meaning: "Building the candidate list", tone: "neutral" }],
  ["OUTREACH", { meaning: "Sending offers to a wave of candidates", tone: "neutral" }],
  ["WAITING_RESPONSE", { meaning: "Waiting for candidates to reply", tone: "waiting" }],
  ["SAFETY_VALIDATION", { meaning: "Rechecking hard constraints", tone: "neutral" }],
  ["WAITING_APPROVAL", { meaning: "Waiting for the approver", tone: "waiting" }],
  ["EXECUTING", { meaning: "Closing the case", tone: "neutral" }],
  ["RESOLVED", { meaning: "Gap closed by the assigned replacements", tone: "ok" }],
  ["MANUAL_HANDOFF", { meaning: "Handed to a person, automation stopped", tone: "waiting" }],
  ["UNRESOLVED", { meaning: "Handled by a person but not solved", tone: "bad" }],
  ["FAILED", { meaning: "System or service error", tone: "bad" }],
]);

export const TONE_CLASS: Record<StatusTone, string> = {
  ok: "text-green-700",
  bad: "text-red-700",
  waiting: "text-amber-700",
  neutral: "",
};

/** Where a candidate is in a case (docs/workflow.md, section 4.1). A Map, so an unknown stage is undefined. */
export const CANDIDATE_STAGE_INFO: ReadonlyMap<string, { label: string; tone: StatusTone }> = new Map([
  ["NOT_CONTACTED", { label: "Not contacted", tone: "neutral" }],
  ["OFFER_PENDING", { label: "Offer queued", tone: "neutral" }],
  ["OFFER_SENT", { label: "Offer sent, waiting for reply", tone: "waiting" }],
  ["OFFER_REJECTED", { label: "Declined the offer", tone: "neutral" }],
  ["OFFER_TIMEOUT", { label: "Did not reply in time", tone: "neutral" }],
  ["OFFER_FAILED", { label: "Offer could not be delivered", tone: "bad" }],
  ["OFFER_CANCELLED", { label: "Offer cancelled", tone: "neutral" }],
  ["ACCEPTED", { label: "Accepted, on reserve", tone: "waiting" }],
  ["SAFETY_FAILED", { label: "Accepted, failed the safety check", tone: "bad" }],
  ["WAITING_APPROVAL", { label: "Accepted, waiting for approval", tone: "waiting" }],
  ["APPROVAL_REJECTED", { label: "Not approved", tone: "bad" }],
  ["APPROVAL_TIMEOUT", { label: "Approval timed out", tone: "neutral" }],
  ["APPROVED", { label: "Approved, not on the roster", tone: "waiting" }],
  ["ASSIGNED", { label: "Assigned to the shift", tone: "ok" }],
]);

/** Fixed reason of each score term (docs/workflow.md, section 6.15). A Map, so an unknown term is undefined. */
export const SCORE_TERM_INFO: ReadonlyMap<string, string> = new Map([
  ["candidate_count", "Same for everyone: each person called in adds this"],
  ["consecutive_shift", "Shifts in a row with this shift added"],
  ["workload_imbalance", "Hours already worked this week"],
  ["projected_overtime", "Overtime hours already worked this week"],
  ["candidate_source", "Position of their source in the source priority, 0 is the closest"],
]);

/** Fixed reason for first_wave (docs/workflow.md, section 6.15). */
export const FIRST_WAVE_INFO = {
  true: "First wave: chosen to fill the gap",
  false: "Reserve: ranked after the first wave",
} as const;

/** Skip reason codes (docs/database-schema.md, Candidate Skip Reasons). */
export const SKIP_REASON_INFO: ReadonlyMap<string, string> = new Map([
  ["STAFF_NOT_ACTIVE", "Not an active staff member"],
  ["ALREADY_ON_SHIFT", "Already on this shift"],
  ["UNAVAILABLE", "Unavailable during this shift"],
  ["SHIFT_CONFLICT", "Has another shift at the same time"],
  ["ROLE_MISMATCH", "Does not have the role that is short"],
  ["SKILL_MISMATCH", "Does not have the skill that is short"],
  ["INSUFFICIENT_REST", "Not enough rest before or after the shift"],
  ["DAILY_HOURS_EXCEEDED", "Would exceed the daily hours limit"],
  ["WEEKLY_HOURS_EXCEEDED", "Would exceed the weekly hours limit"],
  ["CONSECUTIVE_SHIFTS_EXCEEDED", "Would exceed the consecutive shifts limit"],
  ["SOURCE_WARD_MINIMUM_VIOLATION", "Their own ward would fall below its minimum"],
  ["OFFER_LIMIT_REACHED", "Already holds the maximum number of open offers"],
]);
