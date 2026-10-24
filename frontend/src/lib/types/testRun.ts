/** Test runs of the Demo control (round 6 PR EV5b, docs/workflow.md 6.35). */

export const TEST_RUN_SCENARIOS = ["golden", "cross_ward", "surge", "no_show", "handoff", "supervisor"] as const;
export type TestRunScenario = (typeof TEST_RUN_SCENARIOS)[number];

/** The intervals of 6.35.4 in seconds the tester really spent (clock advances taken out). */
export const KPI_INTERVALS = [
  "detect_s",
  "shortlist_s",
  "first_offer_s",
  "first_accept_s",
  "approval_s",
  "time_to_fill_s",
] as const;
export type KpiInterval = (typeof KPI_INTERVALS)[number];

/** KPI of a closed, valid run. A value that did not happen in the run is null, never 0. */
export type TestRunKpi = Record<KpiInterval, number | null> & {
  filled_before_shift_start: boolean | null;
  offers_sent: number;
  candidates_skipped_by_rules: number;
  from_other_ward: boolean | null;
  [system: `${string}_system_s`]: number | null;
};

/** One row of GET /demo/test-runs. */
export type TestRunView = {
  test_run_id: number;
  tester_code: string;
  scenario: string;
  auto_nurses: boolean;
  started_at: string;
  started_real_at: string | null;
  open: boolean;
  /** System time since the start, advances included; null when this API lost the run's clock */
  elapsed_seconds: number | null;
  /** null while open; true for an aborted, CLOCK_LOST, START_FAILED or NO_CASE run */
  invalid: boolean | null;
  reason: string | null;
  advanced_seconds: number;
  /** null while open or when invalid */
  kpi: TestRunKpi | null;
};

/** POST /demo/test-runs. */
export type TestRunStarted = {
  test_run_id: number;
  scenario: TestRunScenario;
  started_at: string;
  case_id: number | null;
};

/** POST /demo/test-runs/{id}/finish and /abort: the payload of TEST_RUN_FINISHED. */
export type TestRunClosed = {
  test_run_id: number;
  result: { invalid: boolean; reason?: string } & Partial<TestRunKpi>;
};
