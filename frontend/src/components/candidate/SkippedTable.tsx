import type { SkipRecord } from "@/lib/cases";
import { SKIP_REASON_INFO } from "@/lib/constants";
import type { CandidateView } from "@/lib/types/case";

export function SkippedTable({
  skips,
  candidates,
}: {
  skips: SkipRecord[];
  candidates: CandidateView[];
}) {
  return (
    <table aria-label="Skipped" className="mt-2 w-full text-left">
      <thead>
        <tr>
          <th className="py-1 pr-4">When</th>
          <th className="py-1 pr-4">Staff ID</th>
          <th className="py-1 pr-4">Name</th>
          <th className="py-1 pr-4">Reason</th>
        </tr>
      </thead>
      <tbody>
        {skips.map(skip => {
          const person = candidates.find(candidate => candidate.staff_id === skip.staffId);
          const meaning = SKIP_REASON_INFO.get(skip.reason);
          return (
            <tr key={skip.key}>
              <td className="py-1 pr-4">{skip.origin}</td>
              <td className="py-1 pr-4">{skip.staffId}</td>
              <td className="py-1 pr-4">{person ? `${person.first_name} ${person.last_name}` : "—"}</td>
              <td className="py-1 pr-4">
                {skip.reason}
                {meaning && <span className="ml-2 text-sm text-gray-500">{meaning}</span>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
