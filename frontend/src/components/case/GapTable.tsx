import { formatDateTime } from "@/lib/format";
import type { GapIntervalView, GapView } from "@/lib/types/case";

function Shortage({ count }: { count: number }) {
  return count > 0
    ? <span className="text-red-700">Short by {count}</span>
    : <span className="text-green-700">OK</span>;
}

function shortages(slice: GapIntervalView): string {
  const parts = [
    ...(slice.headcount.gap_count > 0
      ? [`${slice.headcount.gap_count} ${slice.headcount.gap_count === 1 ? "person" : "people"}`]
      : []),
    ...slice.roles.filter((row) => row.gap_count > 0).map((row) => `${row.gap_count} ${row.name}`),
    ...slice.skills.filter((row) => row.gap_count > 0).map((row) => `${row.gap_count} ${row.name}`),
  ];
  return parts.length === 0 ? "Covered" : `Short: ${parts.join(", ")}`;
}

/**
 * The gap by time slice (docs/workflow.md, section 6.20). Shown for every gap that
 * has slices: one slice is not always the whole shift, because a shift that has
 * started is measured only from the assessment time (evaluated_from) to its end.
 * A gap written before round 4 has no slices and shows none.
 */
export function GapIntervals({ intervals }: { intervals: GapIntervalView[] }) {
  if (intervals.length === 0) return null;
  return (
    <table aria-label="Gap by time" className="mt-2 w-full text-left">
      <thead>
        <tr>
          <th className="py-1 pr-4">From</th>
          <th className="py-1 pr-4">Until</th>
          <th className="py-1 pr-4">Headcount</th>
          <th className="py-1 pr-4">Gap</th>
        </tr>
      </thead>
      <tbody>
        {intervals.map((slice) => (
          <tr key={slice.start_at}>
            <td className="py-1 pr-4">{formatDateTime(slice.start_at)}</td>
            <td className="py-1 pr-4">{formatDateTime(slice.end_at)}</td>
            <td className="py-1 pr-4">
              {slice.headcount.current_count} of {slice.headcount.required_count}
            </td>
            <td className={`py-1 pr-4 ${shortages(slice) === "Covered" ? "text-green-700" : "text-red-700"}`}>
              {shortages(slice)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Headcount, roles and skills are separate checks and are never added together. */
export function GapTable({ gap }: { gap: GapView }) {
  const rows = [
    ...gap.roles.map((row) => ({ kind: "Role", ...row })),
    ...gap.skills.map((row) => ({ kind: "Skill", ...row })),
  ];
  return (
    <>
      <p className="mt-2">
        Headcount: <Shortage count={gap.headcount_gap} />
        <span className="ml-2">
          {gap.headcount_gap > 0
            ? `Minimum ${gap.effective_minimum}, ${gap.effective_minimum - gap.headcount_gap} on shift when assessed`
            : `Minimum ${gap.effective_minimum}`}
        </span>
        <span className="ml-4 text-sm text-gray-500">Computed {formatDateTime(gap.computed_at)}</span>
      </p>
      {gap.intervals.length > 1 && (
        <p className="mt-2 text-sm">The shortage changes during the shift. The numbers below are the worst slice.</p>
      )}
      <GapIntervals intervals={gap.intervals} />
      {rows.length === 0 ? (
        <p className="mt-2">No role or skill requirements.</p>
      ) : (
        <table aria-label="Gap" className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th className="py-1 pr-4">Type</th>
              <th className="py-1 pr-4">Name</th>
              <th className="py-1 pr-4">Required</th>
              <th className="py-1 pr-4">Current</th>
              <th className="py-1 pr-4">Gap</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.kind}-${row.id}`}>
                <td className="py-1 pr-4">{row.kind}</td>
                <td className="py-1 pr-4">{row.name}</td>
                <td className="py-1 pr-4">{row.required_count}</td>
                <td className="py-1 pr-4">{row.current_count}</td>
                <td className="py-1 pr-4"><Shortage count={row.gap_count} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
