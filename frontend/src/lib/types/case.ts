/**
 * Answers of the case read routes (docs/workflow.md, section 9.3).
 * Mirrors backend/app/schemas/case.py. Enum fields are plain strings: the values
 * are not locked yet (D8), so the UI shows a value it does not know as it is.
 */

/** One role or skill of a gap. `id` is the role ID or the skill ID. */
export type GapCount = {
  id: number;
  name: string;
  required_count: number;
  current_count: number;
  gap_count: number;
};

/** Headcount of one time slice of a gap */
export type HeadcountCount = { required_count: number; current_count: number; gap_count: number };

/** One time slice [start_at, end_at) of a gap */
export type GapIntervalView = {
  start_at: string;
  end_at: string;
  headcount: HeadcountCount;
  roles: GapCount[];
  skills: GapCount[];
};

export type GapView = {
  id: number;
  /** The headcount target the gap was measured against */
  effective_minimum: number;
  /** The worst slice of each dimension, for display */
  headcount_gap: number;
  computed_at: string;
  roles: GapCount[];
  skills: GapCount[];
  /** Where the measured window starts; null for a gap written before round 4 */
  evaluated_from: string | null;
  /** Every slice in time order; empty for a gap written before round 4 */
  intervals: GapIntervalView[];
};

/** One term of a score: points = weight x value, as stored with the plan */
export type ScoreTerm = { name: string; value: number; weight: number; points: number };

/** Terms are in formula order. first_wave tells a first-wave pick from a reserve */
export type CandidateScore = { total: number; terms: ScoreTerm[]; first_wave: boolean };

/** Why the explanation cannot be asked for now (docs/workflow.md 9.8) */
export type ExplanationBlock =
  | "ALREADY_READY" | "PENDING" | "NOT_CONFIGURED" | "INVALID_INPUT" | "ATTEMPTS_EXHAUSTED" | "QUOTA_EXHAUSTED";

/** Requested case summary for the current snapshot, with earlier successful summaries. */
export type CaseSummaryView = {
  current: {
    summary_id: number | null;
    status: "NOT_REQUESTED" | "PENDING" | "READY" | "UNAVAILABLE" | "QUOTA_EXHAUSTED";
    text: string | null;
    generated_at: string | null;
    stale: boolean;
    can_request: boolean;
    request_blocked_reason: ExplanationBlock | null;
  };
  history: { summary_id: number; text: string; generated_at: string }[];
};

/** The LLM sentence about the plan's ranking, made only when a user asks (round 6 PR E1). Only READY carries text. The numbers stay the source of truth */
export type RankExplanation = {
  status: "NOT_REQUESTED" | "PENDING" | "READY" | "UNAVAILABLE" | "QUOTA_EXHAUSTED";
  /** Only when READY */
  text: string | null;
  /** Only when READY. "fake" is a test adapter, not a real model */
  provider: "fake" | "bedrock" | "lambda" | null;
  /** Only when READY. null for fake */
  model_id: string | null;
  /** True when POST /cases/{id}/explanation would queue it now */
  can_request: boolean;
  /** null exactly when can_request is true */
  request_blocked_reason: ExplanationBlock | null;
};

/** The roster row a candidate is moved out of when they take this shift */
export type SourceAssignmentView = {
  assignment_id: number;
  shift_id: number;
  ward_id: number;
  ward_name: string;
};

export type CandidateView = {
  candidate_item_id: number;
  rank: number;
  staff_id: number;
  first_name: string;
  last_name: string;
  source: string;
  /** The candidate's home ward (docs/workflow.md, section 9.6) */
  home_ward_id: number;
  home_ward_name: string;
  /** null until an offer was created for this candidate */
  outreach_status: string | null;
  /** Where the candidate is in the case (docs/workflow.md, section 4.1) */
  stage: string;
  /** Numbers come from the plan's snapshot (docs/workflow.md, section 6.15). null means no score, for a reason the API does not give */
  score: CandidateScore | null;
  /** Both null means the whole shift (docs/workflow.md, section 6.20) */
  cover_start_at: string | null;
  cover_end_at: string | null;
  /** null means the candidate is not moved out of another shift */
  source_assignment: SourceAssignmentView | null;
};

/** Immutable snapshot returned by /me/handovers and the case detail API. */
export type HandoverView = {
  handover_id: number;
  roster_assignment_id: number;
  active: boolean;
  generated_at: string;
  /** Preserve unknown content keys/versions for future readers. */
  content: Record<string, unknown>;
};

/** GET /cases/{id} */
export type CaseDetail = {
  id: number;
  status: string;
  /** Every event of the case, by ID. One merge window can put several into one case */
  event_ids: number[];
  shift_id: number;
  required_replacement_time: string;
  created_at: string;
  updated_at: string;
  /** null until the ASSESSING step stored a gap */
  gap: GapView | null;
  /** People this case already put on the roster */
  assigned_count: number;
  /** Empty until the solver stored a plan. Ordered by rank */
  candidates: CandidateView[];
  /** null when the latest plan has no explanation row (LLM off, an old plan, no plan) */
  explanation: RankExplanation | null;
  /** true when no group could cover every target, so the solver used the partial plan */
  partial_plan: boolean;
  handovers: HandoverView[];
  summary: CaseSummaryView | null;
  /** Round 6 PR EV7: who left, who came, who decided, why it stopped. Absent from an older Backend */
  overview?: CaseOverview;
};

/** Someone the case overview names */
export type OverviewPerson = {
  staff_id: number | null;
  name: string;
  role: string | null;
  ward_name: string | null;
};

/** One ward's approval of a request (round 6 PR EV8): the destination, and the source of a move */
export type OverviewSide = {
  side: "DESTINATION" | "SOURCE";
  ward_name: string;
  /** NOT_NEEDED: the request ended before this ward decided */
  status: "PENDING" | "APPROVED" | "REJECTED" | "AUTO_APPROVED" | "TIMED_OUT" | "NOT_NEEDED";
  by: OverviewPerson | null;
  decided_as: "HEAD_NURSE" | "SUPERVISOR" | null;
  reason: string | null;
  at: string | null;
  /** While PENDING: the ward's head nurses */
  waiting_for: OverviewPerson[];
  /** While PENDING: when the Supervisor may decide too */
  supervisor_from: string | null;
};

/** One accepted offer and its approval, bound to its candidate (round 6 PR EV8) */
export type OverviewRequest = {
  approval_id: number;
  candidate: OverviewPerson;
  destination_ward_name: string;
  /** null: free that day; a move needs both wards */
  moved_from: { shift_id: number; ward_name: string; start_at: string; end_at: string } | null;
  status: "PENDING" | "APPROVED" | "REJECTED" | "TIMED_OUT" | "CANCELLED";
  approval_mode: "MANUAL" | "AUTO";
  /** The candidate is on the case's shift now */
  assigned: boolean;
  requested_at: string;
  sides: OverviewSide[];
};

export type OverviewShift = {
  shift_id: number;
  ward_id: number;
  ward_name: string;
  shift_type: string;
  start_at: string;
  end_at: string;
};

export type CaseOverview = {
  events: {
    event_id: number;
    event_type: string;
    staff: OverviewPerson | null;
    occurred_at: string;
    /** NO_SHOW for the check-in job's event; the words of a cancel (round 6 PR EV8) */
    reason?: string | null;
    patient_count?: number | null;
  }[];
  replacements: { staff: OverviewPerson; how: "APPROVED" | "TRANSFERRED" | "MANUAL"; at: string }[];
  decisions: {
    kind: "APPROVED" | "REJECTED" | "AUTO_APPROVED" | "APPROVAL_TIMEOUT" | "MANUAL_ASSIGNMENT" | "CLOSED_UNRESOLVED";
    by: OverviewPerson;
    ward_name: string | null;
    side: "DESTINATION" | "SOURCE" | null;
    candidate: OverviewPerson | null;
    reason: string | null;
    at: string;
  }[];
  outcome: { kind: "MANUAL_HANDOFF" | "CLOSED_UNRESOLVED" | "FAILED"; reason: string | null; by: OverviewPerson | null; at: string } | null;
  /** Round 6 PR EV8; absent from an older Backend */
  shift?: OverviewShift | null;
  requests?: OverviewRequest[];
  /** Offers still waiting for an answer */
  open_offers?: number;
};

/** One item of GET /cases/{id}/audit */
export type AuditEntry = {
  id: number;
  action: string;
  actor_id: number;
  /** str(staff.id) for a staff actor, e.g. "105" */
  actor_name: string;
  actor_type: string;
  entity_type: string;
  entity_id: number | null;
  payload: Record<string, unknown>;
  created_at: string;
};
