/** One item of GET /cases?status=... (docs/workflow.md, section 9.4). */
export type HandoffCase = {
  id: number;
  status: string;
  shift_id: number;
  ward_id: number;
  required_replacement_time: string;
  created_at: string;
  /** null when the case has no gap row */
  headcount_gap: number | null;
  assigned_count: number;
  /** Only a MANUAL_HANDOFF case can be staffed or closed by hand */
  can_manage: boolean;
};

/** One item of GET /cases/{id}/handoff/candidates. */
export type HandoffCandidate = {
  staff_id: number;
  first_name: string;
  last_name: string;
  role_id: number;
  role_name: string;
  /** Hard Rule codes that fail now. Empty: can be assigned */
  blocking_rules: string[];
  /** Running cases where this person has a live offer */
  other_case_ids: number[];
};

/** Answer of POST /cases/{id}/handoff/assignments. */
export type ManualAssignmentResult = {
  manual_assignment_id: number;
  assignment_id: number;
  staff_id: number;
  case_id: number;
  case_status: string;
  cancelled_outreach_ids: number[];
};

/** Answer of POST /cases/{id}/handoff/close. */
export type CloseCaseResult = {
  case_id: number;
  case_status: string;
};

/** The `detail` of a 409 that carries data, keyed by `code`. */
export type HandoffConflict =
  | { code: "HARD_RULES_FAILED"; message: string; failed_rules: string[] }
  | { code: "CONFLICTING_OFFERS"; message: string; case_ids: number[] };
