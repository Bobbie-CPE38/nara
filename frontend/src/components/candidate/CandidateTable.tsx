import { CANDIDATE_STAGE_INFO, TONE_CLASS } from "@/lib/constants";
import { formatDateTime, formatScore } from "@/lib/format";
import type { CandidateView } from "@/lib/types/case";

/** A stage the map does not know is shown as it is. */
function StageLabel({ stage }: { stage: string }) {
  const info = CANDIDATE_STAGE_INFO.get(stage);
  return <span className={TONE_CLASS[info?.tone ?? "neutral"]}>{info?.label ?? stage}</span>;
}

/** Both ends null means the whole shift (docs/workflow.md, section 6.20). */
function coverText(candidate: CandidateView): string {
  if (candidate.cover_start_at === null && candidate.cover_end_at === null) return "Whole shift";
  const start =
    candidate.cover_start_at === null ? "shift start" : formatDateTime(candidate.cover_start_at);
  const end =
    candidate.cover_end_at === null ? "shift end" : formatDateTime(candidate.cover_end_at);
  return `${start} – ${end}`;
}

/** Candidates in the order the API sends them, which is by rank. */
export function CandidateTable({
  candidates,
  stopped = false,
}: {
  candidates: CandidateView[];
  /** The case will not get a plan any more, so an empty list is final */
  stopped?: boolean;
}) {
  if (candidates.length === 0) {
    return <p className="mt-2">{stopped ? "No candidates." : "No candidates yet."}</p>;
  }
  return (
    <table aria-label="Candidates" className="mt-2 w-full text-left">
      <thead>
        <tr>
          <th className="py-1 pr-4">Rank</th>
          <th className="py-1 pr-4">Staff ID</th>
          <th className="py-1 pr-4">Name</th>
          <th className="py-1 pr-4">Source</th>
          <th className="py-1 pr-4">Status</th>
          <th className="py-1 pr-4">Score</th>
          <th className="py-1 pr-4">Home ward</th>
          <th className="py-1 pr-4">Covers</th>
          <th className="py-1 pr-4">Moved from</th>
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
              <StageLabel stage={candidate.stage} />
            </td>
            <td className="py-1 pr-4">{candidate.score ? formatScore(candidate.score.total) : "—"}</td>
            <td className="py-1 pr-4">{candidate.home_ward_name}</td>
            <td className="py-1 pr-4">{coverText(candidate)}</td>
            <td className="py-1 pr-4">
              {candidate.source_assignment
                ? `${candidate.source_assignment.ward_name}, shift ${candidate.source_assignment.shift_id}`
                : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
