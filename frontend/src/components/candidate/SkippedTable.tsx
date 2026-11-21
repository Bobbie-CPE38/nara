"use client";

import { ScrollX } from "@/components/ScrollX";
import type { SkipRecord } from "@/lib/cases";
import { SKIP_REASON_KEYS } from "@/lib/constants";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CandidateView } from "@/lib/types/case";

export function SkippedTable({
  skips,
  candidates,
}: {
  skips: SkipRecord[];
  candidates: CandidateView[];
}) {
  const t = useT();
  // A case that stopped without a plan has no candidate to name
  const named = skips.some(skip => candidates.some(candidate => candidate.staff_id === skip.staffId));
  return (
    <ScrollX>
      <table aria-label={t("case.skipped")} className="mt-2">
        <thead>
          <tr>
            <th>{t("skip.when")}</th>
            <th>{t("common.staffId")}</th>
            {named && <th>{t("common.name")}</th>}
            <th>{t("skip.reason")}</th>
          </tr>
        </thead>
        <tbody>
          {skips.map(skip => {
            const person = candidates.find(candidate => candidate.staff_id === skip.staffId);
            const meaningKey = SKIP_REASON_KEYS.get(skip.reason);
            return (
              <tr key={skip.key}>
                <td>{skip.origin}</td>
                <td>{skip.staffId}</td>
                {named && (
                  <td>{person ? `${person.first_name} ${person.last_name}` : "—"}</td>
                )}
                <td>
                  {skip.reason}
                  {meaningKey && <span className="ml-2 text-sm text-slate-500">{t(meaningKey)}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollX>
  );
}
