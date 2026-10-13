import { CANDIDATE_STAGE_INFO, TONE_CLASS } from "@/lib/constants";
import type { CandidateView } from "@/lib/types/case";

/** Candidates in the order the API sends them, which is by rank. */
export function CandidateTable({ candidates }: { candidates: CandidateView[] }) {
  if (candidates.length === 0) return <p className="mt-2">No candidates yet.</p>;
  return (
    <table aria-label="Candidates" className="mt-2 w-full text-left">
      <thead>
        <tr>
          <th className="py-1 pr-4">Rank</th>
          <th className="py-1 pr-4">Staff ID</th>
          <th className="py-1 pr-4">Name</th>
          <th className="py-1 pr-4">Source</th>
          <th className="py-1 pr-4">Status</th>
        </tr>
      </thead>
      <tbody>
        {candidates.map(candidate => (
          <tr key={candidate.candidate_item_id}>
            <td className="py-1 pr-4">{candidate.rank}</td>
            <td className="py-1 pr-4">{candidate.staff_id}</td>
            <td className="py-1 pr-4">{candidate.first_name} {candidate.last_name}</td>
            <td className="py-1 pr-4">{candidate.source}</td>
            <td className="py-1 pr-4">
              {(() => {
                const info = CANDIDATE_STAGE_INFO.get(candidate.stage);
                return (
                  <span className={TONE_CLASS[info?.tone ?? "neutral"]}>
                    {info?.label ?? candidate.stage}
                  </span>
                );
              })()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
