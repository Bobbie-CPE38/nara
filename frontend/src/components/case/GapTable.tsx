import { formatDateTime } from "@/lib/format";
import type { GapView } from "@/lib/types/case";

function Shortage({ count }: { count: number }) {
  return count > 0
    ? <span className="text-red-700">Short by {count}</span>
    : <span className="text-green-700">OK</span>;
}

/** Headcount, roles and skills are separate checks and are never added together. */
export function GapTable({ gap }: { gap: GapView }) {
  const rows = [
    ...gap.roles.map(row => ({ kind: "Role", ...row })),
    ...gap.skills.map(row => ({ kind: "Skill", ...row })),
  ];
  return (
    <>
      <p className="mt-2">
        Headcount: <Shortage count={gap.headcount_gap} />
        <span className="ml-4 text-sm text-gray-500">Computed {formatDateTime(gap.computed_at)}</span>
      </p>
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
            {rows.map(row => (
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
