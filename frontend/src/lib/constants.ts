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
  ["OUTREACH", { meaning: "Sending an offer", tone: "neutral" }],
  ["WAITING_RESPONSE", { meaning: "Waiting for the candidate to reply", tone: "waiting" }],
  ["SAFETY_VALIDATION", { meaning: "Rechecking hard constraints", tone: "neutral" }],
  ["WAITING_APPROVAL", { meaning: "Waiting for the approver", tone: "waiting" }],
  ["EXECUTING", { meaning: "Updating the roster", tone: "neutral" }],
  ["RESOLVED", { meaning: "Replacement found and recorded", tone: "ok" }],
  ["MANUAL_HANDOFF", { meaning: "Handed to a person, automation stopped", tone: "waiting" }],
  ["UNRESOLVED", { meaning: "Handled by a person but not solved", tone: "bad" }],
  ["FAILED", { meaning: "System or service error", tone: "bad" }],
]);
