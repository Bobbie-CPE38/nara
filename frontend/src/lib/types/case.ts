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

export type GapView = {
  id: number;
  headcount_gap: number;
  computed_at: string;
  roles: GapCount[];
  skills: GapCount[];
};

export type CandidateView = {
  candidate_item_id: number;
  rank: number;
  staff_id: number;
  first_name: string;
  last_name: string;
  source: string;
  /** null until an offer was created for this candidate */
  outreach_status: string | null;
};

/** GET /cases/{id} */
export type CaseDetail = {
  id: number;
  status: string;
  event_id: number;
  shift_id: number;
  required_replacement_time: string;
  created_at: string;
  updated_at: string;
  /** null until the ASSESSING step stored a gap */
  gap: GapView | null;
  /** Empty until the solver stored a plan. Ordered by rank */
  candidates: CandidateView[];
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
