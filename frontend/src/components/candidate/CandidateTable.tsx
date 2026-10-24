"use client";

import { ScrollX } from "@/components/ScrollX";
import { CANDIDATE_STAGE_INFO, TONE_CLASS } from "@/lib/constants";
import { formatDateTime, formatScore } from "@/lib/format";
import type { Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CandidateView } from "@/lib/types/case";

/** A stage the map does not know is shown as it is. */
function StageLabel({ stage }: { stage: string }) {
  const t = useT();
  const info = CANDIDATE_STAGE_INFO.get(stage);
  return <span className={TONE_CLASS[info?.tone ?? "neutral"]}>{info ? t(info.messageKey) : stage}</span>;
}

/** Both ends null means the whole shift (docs/workflow.md, section 6.20). */
function coverText(candidate: CandidateView, t: Translate): string {
  if (candidate.cover_start_at === null && candidate.cover_end_at === null) return t("cand.wholeShift");
  const start =
    candidate.cover_start_at === null ? t("cand.shiftStart") : formatDateTime(candidate.cover_start_at);
  const end =
    candidate.cover_end_at === null ? t("cand.shiftEnd") : formatDateTime(candidate.cover_end_at);
  return `${start} – ${end}`;
}

/**
 * Candidates in the order the API sends them, which is by rank.
 *
 * "Covers" and "Moved from" are shown only when some candidate differs (round 6 PR EV8): in most
 * cases everyone covers the whole shift and nobody is moved off another shift, so the two
 * columns said the same thing in every row of every case.
 */
export function CandidateTable({
  candidates,
  stopped = false,
}: {
  candidates: CandidateView[];
  /** The case will not get a plan any more, so an empty list is final */
  stopped?: boolean;
}) {
  const t = useT();
  if (candidates.length === 0) {
    return <p className="mt-2">{stopped ? t("cand.none") : t("cand.noneYet")}</p>;
  }
  const partCovers = candidates.some(
    (candidate) => candidate.cover_start_at !== null || candidate.cover_end_at !== null,
  );
  const moves = candidates.some((candidate) => candidate.source_assignment !== null);
  return (
    <ScrollX>
      <table aria-label={t("case.candidates")} className="mt-2">
        <thead>
          <tr>
            <th>{t("cand.rank")}</th>
            <th>{t("common.staffId")}</th>
            <th>{t("common.name")}</th>
            <th>{t("cand.source")}</th>
            <th>{t("cand.status")}</th>
            <th>{t("cand.score")}</th>
            <th>{t("cand.homeWard")}</th>
            {partCovers && <th>{t("cand.covers")}</th>}
            {moves && <th>{t("cand.movedFrom")}</th>}
          </tr>
        </thead>
        <tbody>
          {candidates.map(candidate => (
            <tr key={candidate.candidate_item_id}>
              <td>{candidate.rank}</td>
              <td>{candidate.staff_id}</td>
              <td>{candidate.first_name} {candidate.last_name}</td>
              <td>{candidate.source}</td>
              <td>
                <StageLabel stage={candidate.stage} />
              </td>
              <td>{candidate.score ? formatScore(candidate.score.total) : "—"}</td>
              <td>{candidate.home_ward_name}</td>
              {partCovers && <td>{coverText(candidate, t)}</td>}
              {moves && (
                <td>
                  {candidate.source_assignment
                    ? t("cand.sourceShift", {
                        ward: candidate.source_assignment.ward_name,
                        shift: candidate.source_assignment.shift_id,
                      })
                    : "—"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollX>
  );
}
