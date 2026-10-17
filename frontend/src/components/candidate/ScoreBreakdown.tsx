"use client";

import { ScrollX } from "@/components/ScrollX";
import { Button } from "@/components/ui/Button";
import { SCORE_TERM_KEYS } from "@/lib/constants";
import { formatScore } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CandidateScore, CandidateView, RankExplanation } from "@/lib/types/case";

function ScoreTable({ staffId, score }: { staffId: number; score: CandidateScore }) {
  const t = useT();
  // A copy, so the API array is not changed. The sort is stable, so equal points keep the API order.
  const terms = [...score.terms].sort((a, b) => b.points - a.points);
  return (
    <ScrollX>
      <table aria-label={t("score.tableLabel", { staffId })} className="mt-2">
        <thead>
          <tr>
            <th>{t("score.term")}</th>
            <th>{t("score.value")}</th>
            <th>{t("score.weight")}</th>
            <th>{t("score.points")}</th>
          </tr>
        </thead>
        <tbody>
          {terms.map(term => {
            const reasonKey = SCORE_TERM_KEYS.get(term.name);
            return (
              <tr key={term.name}>
                <td>
                  {term.name}
                  {reasonKey && <span className="ml-2 text-sm text-slate-500">{t(reasonKey)}</span>}
                </td>
                <td>{formatScore(term.value)}</td>
                <td>{formatScore(term.weight)}</td>
                <td>{formatScore(term.points)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollX>
  );
}

/** What the user asked for, if anything: set by CaseView around POST /cases/{id}/explanation. */
export type ExplanationRequest = {
  busy: boolean;
  /** Why the last request was refused or failed, as a key of the dictionary; null otherwise */
  message: MessageKey | null;
  onRequest: () => void;
};

/** Why the button is closed, by request_blocked_reason. PENDING and ALREADY_READY have no text: the status says it. */
const BLOCKED_KEYS: Record<string, MessageKey> = {
  QUOTA_EXHAUSTED: "ai.blockedQuota",
  NOT_CONFIGURED: "ai.blockedNotConfigured",
  INVALID_INPUT: "ai.blockedInvalidInput",
  ATTEMPTS_EXHAUSTED: "ai.blockedAttempts",
};

/** The status line of an explanation that is not READY. Never a failure reason. */
function statusKey(explanation: RankExplanation | null): MessageKey {
  if (explanation === null) return "ai.notReady";
  if (explanation.status === "PENDING") return "ai.pending";
  if (explanation.status === "UNAVAILABLE") return "ai.failed";
  return "ai.notRequested";
}

/**
 * The LLM sentence when READY. Otherwise the status and, when the plan can be explained, the
 * button that asks for it (round 6 PR E2). The button follows can_request from the API and
 * nothing else. It never replaces the numbers below it.
 */
function Explanation({ explanation, request }: { explanation: RankExplanation | null; request: ExplanationRequest }) {
  const t = useT();
  if (explanation?.status !== "READY") {
    const blocked = explanation?.request_blocked_reason;
    const reasonKey = blocked ? BLOCKED_KEYS[blocked] : undefined;
    return (
      <>
        <p>{t(statusKey(explanation))}</p>
        {explanation && explanation.status !== "PENDING" && (
          <Button
            variant="primary"
            className="mt-2"
            disabled={!explanation.can_request || request.busy}
            onClick={request.onRequest}
          >
            {t("ai.button")}
          </Button>
        )}
        {reasonKey && !explanation?.can_request && <p className="mt-2 text-sm text-slate-600">{t(reasonKey)}</p>}
        {/* The reason above is the case as read again after a refusal; saying it twice adds nothing */}
        {request.message && !(reasonKey && !explanation?.can_request) && (
          <p className="mt-2 text-sm text-red-700" role="alert">{t(request.message)}</p>
        )}
      </>
    );
  }
  return (
    <>
      <p style={{ whiteSpace: "pre-line" }}>{explanation.text}</p>
      <p className="text-sm text-slate-500">{t("ai.sourceNote")}</p>
      {explanation.provider === "fake" && <p className="text-sm text-slate-500">{t("ai.fakeNote")}</p>}
      {explanation.model_id && <p className="text-sm text-slate-500">{t("ai.model", { model: explanation.model_id })}</p>}
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
  const t = useT();
  const scored = candidates.flatMap(candidate => (candidate.score ? [{ candidate, score: candidate.score }] : []));
  if (scored.length === 0) return null;
  return (
    <>
      <h3 className="mt-4 font-semibold">{t("score.title")}</h3>
      <p className="mt-2 text-sm text-slate-600">
        {t(partialPlan ? "score.introPartial" : "score.introPoints")}
        {" "}{t("score.introOrder")}
      </p>
      <section aria-label={t("ai.regionLabel")} className="mt-3 rounded-lg border border-brand-200 bg-brand-50 p-3">
        <Explanation explanation={explanation} request={request} />
      </section>
      {scored.map(({ candidate, score }) => (
        <div key={candidate.candidate_item_id}>
          <h4 className="mt-4 font-semibold">
            {t("score.rankLine", {
              rank: candidate.rank,
              name: `${candidate.first_name} ${candidate.last_name}`,
              staffId: candidate.staff_id,
              points: formatScore(score.total),
            })}
          </h4>
          <p>{t(score.first_wave ? "firstWave.true" : "firstWave.false")}</p>
          <ScoreTable staffId={candidate.staff_id} score={score} />
        </div>
      ))}
    </>
  );
}
