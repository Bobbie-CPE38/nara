import type { KpiInterval, TestRunView } from "@/lib/types/testRun";

/** The tester code the Backend accepts (6.35.2): a code such as T01, never a name. */
export const TESTER_CODE_PATTERN = /^[A-Za-z0-9_-]{1,16}$/;

/** The run that is still open, if any. A run is open until it is finished or aborted. */
export function openRun(runs: readonly TestRunView[] | undefined): TestRunView | undefined {
  return runs?.find((run) => run.open);
}

/** Closed runs that have a KPI: an aborted or lost run is listed but not counted (6.35.4). */
export function validRuns(runs: readonly TestRunView[]): TestRunView[] {
  return runs.filter((run) => !run.open && run.invalid === false && run.kpi !== null);
}

export type Spread = { count: number; median: number; min: number; max: number };

/** Median and range of one interval over the valid runs where it happened; null if none did. */
export function spread(runs: readonly TestRunView[], key: KpiInterval): Spread | null {
  const values = validRuns(runs)
    .map((run) => run.kpi?.[key])
    .filter((value): value is number => typeof value === "number")
    .sort((a, b) => a - b);
  if (values.length === 0) return null;
  const middle = Math.floor(values.length / 2);
  const median = values.length % 2 === 1 ? values[middle] : (values[middle - 1] + values[middle]) / 2;
  return { count: values.length, median, min: values[0], max: values[values.length - 1] };
}

/** Seconds as the pages show them: whole seconds under two minutes, then minutes and seconds. */
export function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const total = Math.round(value);
  if (total < 120) return `${total} s`;
  return `${Math.floor(total / 60)} min ${total % 60} s`;
}
