import type { GapIntervalView } from "@/lib/types/case";

/**
 * Answers of the read-only routes GET /dashboard and GET /gap/shifts (docs/workflow.md,
 * sections 6.31 and 9.8). Money is a Decimal sent as text.
 */
export type DashboardModes = {
  line_mode: "simulation" | "real";
  llm_provider: "fake" | "bedrock" | "lambda";
  llm_enabled: boolean;
};

export type CaseStatusCount = { status: string; count: number };

export type NamedGap = { name: string; gap_count: number };

/** A shift of a visible ward that is short now */
export type Shortage = {
  shift_id: number;
  ward_id: number;
  start_at: string;
  end_at: string;
  headcount_gap: number;
  role_gaps: NamedGap[];
  skill_gaps: NamedGap[];
  case_id: number | null;
};

export type WardCount = { ward_id: number; count: number };

export type NoShowEvent = {
  event_id: number;
  shift_id: number;
  staff_id: number;
  created_at: string;
};

export type LlmUsage = {
  /** The quota day, by real time like the counter */
  date: string;
  used: number;
  cap: number;
  month_cost_usd: string;
  /** Attempts of this month whose cost is unknown, so month_cost_usd may be too low */
  month_calls_without_cost: number;
  budget_usd: string;
};

export type Dashboard = {
  now: string;
  modes: DashboardModes;
  /** The wards the numbers cover */
  wards: number[];
  cases_by_status: CaseStatusCount[];
  shortages: Shortage[];
  pending_approvals: WardCount[];
  open_offers: { count: number };
  recent_no_show: NoShowEvent[];
  /** null while LLM_ENABLED is false */
  llm_usage: LlmUsage | null;
};

/** One item of GET /gap/shifts */
export type GapShiftSummary = {
  shift_id: number;
  ward_id: number;
  start_at: string;
  end_at: string;
  required_staff: number;
  rostered_count: number;
  headcount_gap: number;
  case_id: number | null;
};

export type GapRosterEntry = {
  roster_assignment_id: number;
  staff_id: number;
  name: string;
  status: string;
  effective_start_at: string;
  effective_end_at: string;
  on_leave: boolean;
  checked_in: boolean;
};

/** GET /gap/shifts/{shift_id} */
export type GapShiftDetail = {
  shift_id: number;
  ward_id: number;
  start_at: string;
  end_at: string;
  evaluated_from: string | null;
  intervals: GapIntervalView[];
  roster: GapRosterEntry[];
  case_id: number | null;
};
