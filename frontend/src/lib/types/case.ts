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

/** The LLM sentence about the plan's ranking. PENDING and UNAVAILABLE carry no text. The numbers stay the source of truth */
export type RankExplanation = {
  status: "PENDING" | "READY" | "UNAVAILABLE";
  /** Only when READY */
  text: string | null;
  /** Only when READY. "fake" is a test adapter, not a real model */
  provider: "fake" | "bedrock" | null;
  /** Only when READY. null for fake */
  model_id: string | null;
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
