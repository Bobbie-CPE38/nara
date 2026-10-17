import {
  EXPLANATION_BLOCKED,
  EXPLANATION_BUTTON,
  EXPLANATION_FAILED,
  EXPLANATION_FAKE_NOTE,
  EXPLANATION_NOT_READY,
  EXPLANATION_NOT_REQUESTED,
  EXPLANATION_PENDING,
  EXPLANATION_SOURCE_NOTE,
  FIRST_WAVE_INFO,
  SCORE_TERM_INFO,
} from "@/lib/constants";
import { formatScore } from "@/lib/format";
import type { CandidateScore, CandidateView, RankExplanation } from "@/lib/types/case";

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

/** What the user asked for, if anything: set by CaseView around POST /cases/{id}/explanation. */
export type ExplanationRequest = {
  busy: boolean;
  /** Why the last request was refused or failed; null otherwise */
  message: string | null;
  onRequest: () => void;
};

/** The status line of an explanation that is not READY. Never a failure reason. */
function statusText(explanation: RankExplanation | null): string {
  if (explanation === null) return EXPLANATION_NOT_READY;
  if (explanation.status === "PENDING") return EXPLANATION_PENDING;
  if (explanation.status === "UNAVAILABLE") return EXPLANATION_FAILED;
  return EXPLANATION_NOT_REQUESTED;
}

/**
 * The LLM sentence when READY. Otherwise the status and, when the plan can be explained, the
 * button that asks for it (round 6 PR E2). The button follows can_request from the API and
 * nothing else. It never replaces the numbers below it.
 */
function Explanation({ explanation, request }: { explanation: RankExplanation | null; request: ExplanationRequest }) {
  if (explanation?.status !== "READY") {
    const blocked = explanation?.request_blocked_reason;
    const reason = blocked && blocked in EXPLANATION_BLOCKED
      ? EXPLANATION_BLOCKED[blocked as keyof typeof EXPLANATION_BLOCKED]
      : undefined;
    return (
      <>
        <p>{statusText(explanation)}</p>
        {explanation && explanation.status !== "PENDING" && (
          <button
            type="button"
            className="mt-2 rounded border px-3 py-1 disabled:opacity-50"
            disabled={!explanation.can_request || request.busy}
            onClick={request.onRequest}
          >
            {EXPLANATION_BUTTON}
          </button>
        )}
        {reason && !explanation?.can_request && <p className="mt-2 text-sm text-gray-600">{reason}</p>}
        {/* The reason above is the case as read again after a refusal; saying it twice adds nothing */}
        {request.message && !(reason && !explanation?.can_request) && (
          <p className="mt-2 text-sm text-red-700" role="alert">{request.message}</p>
        )}
      </>
    );
  }
  return (
    <>
      <p style={{ whiteSpace: "pre-line" }}>{explanation.text}</p>
      <p className="text-sm text-gray-500">{EXPLANATION_SOURCE_NOTE}</p>
      {explanation.provider === "fake" && <p className="text-sm text-gray-500">{EXPLANATION_FAKE_NOTE}</p>}
      {explanation.model_id && <p className="text-sm text-gray-500">{`Model: ${explanation.model_id}`}</p>}
    </>
  );
}

/** Score of each candidate that has one, as the API sent it. Candidates without a score are left out. */
export function ScoreBreakdown({ candidates, explanation, partialPlan, request }: {
  candidates: CandidateView[];
  explanation: RankExplanation | null;
  request: ExplanationRequest;
  /** true when no group could cover every target, so coverage chose the first wave */
  partialPlan: boolean;
}) {
  const scored = candidates.flatMap(candidate => (candidate.score ? [{ candidate, score: candidate.score }] : []));
  if (scored.length === 0) return null;
  return (
    <>
      <h3 className="mt-4 font-semibold">Score breakdown</h3>
      <p className="mt-2 text-sm text-gray-500">
        {partialPlan
          ? "Coverage decides first: no group could cover every target, so the first wave is the group that leaves the least time uncovered (headcount, then role, then skill). Points only decide between groups that cover the same."
          : "Points decide which group becomes the first wave: the group that covers the gap with the fewest points in total."}
        {" "}Inside the first wave and inside the reserve, people are ordered by source, then hours this week, consecutive shifts, overtime and staff ID, so points may not follow rank.
      </p>
      <section aria-label="Ranking explanation" className="mt-2">
        <Explanation explanation={explanation} request={request} />
      </section>
      {scored.map(({ candidate, score }) => (
        <div key={candidate.candidate_item_id}>
          <h4 className="mt-4 font-semibold">
            {`Rank ${candidate.rank} · ${candidate.first_name} ${candidate.last_name} (${candidate.staff_id}) · ${formatScore(score.total)} points`}
          </h4>
          <p>{FIRST_WAVE_INFO[score.first_wave ? "true" : "false"]}</p>
          <ScoreTable staffId={candidate.staff_id} score={score} />
        </div>
      ))}
    </>
  );
}
