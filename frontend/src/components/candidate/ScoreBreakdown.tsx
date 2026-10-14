import { FIRST_WAVE_INFO, SCORE_TERM_INFO } from "@/lib/constants";
import { formatScore } from "@/lib/format";
import type { CandidateScore, CandidateView } from "@/lib/types/case";

function ScoreTable({ staffId, score }: { staffId: number; score: CandidateScore }) {
  // A copy, so the API array is not changed. The sort is stable, so equal points keep the API order.
  const terms = [...score.terms].sort((a, b) => b.points - a.points);
  return (
    <table aria-label={`Score of staff ${staffId}`} className="mt-2 w-full text-left">
      <thead>
        <tr>
          <th className="py-1 pr-4">Term</th>
          <th className="py-1 pr-4">Value</th>
          <th className="py-1 pr-4">Weight</th>
          <th className="py-1 pr-4">Points</th>
        </tr>
      </thead>
      <tbody>
        {terms.map(term => {
          const reason = SCORE_TERM_INFO.get(term.name);
          return (
            <tr key={term.name}>
              <td className="py-1 pr-4">
                {term.name}
                {reason && <span className="ml-2 text-sm text-gray-500">{reason}</span>}
              </td>
              <td className="py-1 pr-4">{formatScore(term.value)}</td>
              <td className="py-1 pr-4">{formatScore(term.weight)}</td>
              <td className="py-1 pr-4">{formatScore(term.points)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Score of each candidate that has one, as the API sent it. Candidates without a score are left out. */
export function ScoreBreakdown({ candidates }: { candidates: CandidateView[] }) {
  const scored = candidates.flatMap(candidate => (candidate.score ? [{ candidate, score: candidate.score }] : []));
  if (scored.length === 0) return null;
  return (
    <>
      <h3 className="mt-4 font-semibold">Why this order</h3>
      <p className="mt-2 text-sm text-gray-500">Penalty points stored with the plan. Fewer points is better.</p>
      {scored.map(({ candidate, score }) => (
        <div key={candidate.candidate_item_id}>
          <h3 className="mt-4 font-semibold">
            {`Rank ${candidate.rank} · ${candidate.first_name} ${candidate.last_name} (${candidate.staff_id}) · ${formatScore(score.total)} points`}
          </h3>
          <p>{FIRST_WAVE_INFO[score.first_wave ? "true" : "false"]}</p>
          <ScoreTable staffId={candidate.staff_id} score={score} />
        </div>
      ))}
    </>
  );
}
