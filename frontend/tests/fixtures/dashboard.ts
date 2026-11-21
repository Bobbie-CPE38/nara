import type { Dashboard, GapShiftDetail, GapShiftSummary } from "@/lib/types/dashboard";

const STATUSES = [
  "OPEN",
  "ASSESSING",
  "OPTIMIZING",
  "OUTREACH",
  "WAITING_RESPONSE",
  "SAFETY_VALIDATION",
  "WAITING_APPROVAL",
  "EXECUTING",
  "RESOLVED",
  "MANUAL_HANDOFF",
  "UNRESOLVED",
  "FAILED",
];

/** A quiet ICU: every count is 0 and nothing is short. Tests override what they need. */
export function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    now: "2026-10-17T21:00:00+07:00",
    modes: { line_mode: "simulation", llm_provider: "fake", llm_enabled: false },
    wards: [1],
    ward_options: [{ id: 1, name: "ICU" }],
    cases_by_status: STATUSES.map((status) => ({ status, count: 0 })),
    shortages: [],
    pending_approvals: [],
    open_offers: { count: 0 },
    recent_no_show: [],
    llm_usage: null,
    ...overrides,
  };
}

export function withCounts(counts: Record<string, number>): Dashboard["cases_by_status"] {
  return STATUSES.map((status) => ({ status, count: counts[status] ?? 0 }));
}

export const SHIFT_ROW: GapShiftSummary = {
  shift_id: 1,
  ward_id: 1,
  start_at: "2026-10-17T23:00:00+07:00",
  end_at: "2026-10-18T07:00:00+07:00",
  required_staff: 5,
  rostered_count: 4,
  headcount_gap: 1,
  case_id: 7,
};

export const SHIFT_DETAIL: GapShiftDetail = {
  shift_id: 1,
  ward_id: 1,
  start_at: "2026-10-17T23:00:00+07:00",
  end_at: "2026-10-18T07:00:00+07:00",
  evaluated_from: "2026-10-17T23:00:00+07:00",
  intervals: [
    {
      start_at: "2026-10-17T23:00:00+07:00",
      end_at: "2026-10-18T07:00:00+07:00",
      headcount: { required_count: 5, current_count: 4, gap_count: 1 },
      roles: [{ id: 1, name: "RN", required_count: 5, current_count: 4, gap_count: 1 }],
      skills: [{ id: 1, name: "ICU", required_count: 2, current_count: 1, gap_count: 1 }],
    },
  ],
  roster: [
    {
      roster_assignment_id: 1,
      staff_id: 101,
      name: "Pimchanok Demo",
      status: "CANCELLED",
      effective_start_at: "2026-10-17T23:00:00+07:00",
      effective_end_at: "2026-10-18T07:00:00+07:00",
      on_leave: true,
      checked_in: false,
    },
    {
      roster_assignment_id: 2,
      staff_id: 102,
      name: "Thanaphon Demo",
      status: "ASSIGNED",
      effective_start_at: "2026-10-17T23:00:00+07:00",
      effective_end_at: "2026-10-18T07:00:00+07:00",
      on_leave: false,
      checked_in: true,
    },
  ],
  case_id: 7,
};
