"use client";

import { ScrollX } from "@/components/ScrollX";
import { formatDateTime } from "@/lib/format";
import type { Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { GapIntervalView, GapView } from "@/lib/types/case";

function Shortage({ count }: { count: number }) {
  const t = useT();
  return count > 0
    ? <span className="font-medium text-red-700">{t("gap.shortBy", { count })}</span>
    : <span className="text-green-700">{t("gap.ok")}</span>;
}

/** "Covered", or "Short: 1 person, 1 RN, 1 ICU": the names of roles and skills come from the API. */
function shortages(slice: GapIntervalView, t: Translate): string {
  const parts = [
    ...(slice.headcount.gap_count > 0
      ? [`${slice.headcount.gap_count} ${t(slice.headcount.gap_count === 1 ? "gap.person" : "gap.people")}`]
      : []),
    ...slice.roles.filter((row) => row.gap_count > 0).map((row) => `${row.gap_count} ${row.name}`),
    ...slice.skills.filter((row) => row.gap_count > 0).map((row) => `${row.gap_count} ${row.name}`),
  ];
  return parts.length === 0 ? t("gap.covered") : t("gap.short", { parts: parts.join(", ") });
}

/**
 * The gap by time slice (docs/workflow.md, section 6.20). Shown for every gap that
 * has slices: one slice is not always the whole shift, because a shift that has
 * started is measured only from the assessment time (evaluated_from) to its end.
 * A gap written before round 4 has no slices and shows none.
 */
export function GapIntervals({ intervals }: { intervals: GapIntervalView[] }) {
  const t = useT();
  if (intervals.length === 0) return null;
  return (
    <ScrollX>
      <table aria-label={t("gap.byTime")} className="mt-2">
        <thead>
          <tr>
            <th>{t("common.from")}</th>
            <th>{t("common.until")}</th>
            <th>{t("gap.headcount")}</th>
            <th>{t("common.gap")}</th>
          </tr>
        </thead>
        <tbody>
          {intervals.map((slice) => {
            const covered = slice.headcount.gap_count === 0
              && slice.roles.every((row) => row.gap_count === 0)
              && slice.skills.every((row) => row.gap_count === 0);
            return (
              <tr key={slice.start_at}>
                <td>{formatDateTime(slice.start_at)}</td>
                <td>{formatDateTime(slice.end_at)}</td>
                <td>
                  {t("gap.countOf", {
                    current: slice.headcount.current_count,
                    required: slice.headcount.required_count,
                  })}
                </td>
                <td className={covered ? "text-green-700" : "font-medium text-red-700"}>
                  {shortages(slice, t)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollX>
  );
}

/** Headcount, roles and skills are separate checks and are never added together. */
export function GapTable({ gap }: { gap: GapView }) {
  const t = useT();
  const rows = [
    ...gap.roles.map((row) => ({ kind: t("gap.kindRole"), ...row })),
    ...gap.skills.map((row) => ({ kind: t("gap.kindSkill"), ...row })),
  ];
  return (
    <>
      <p className="mt-2">
        {t("gap.headcountLabel")} <Shortage count={gap.headcount_gap} />
        <span className="ml-2">
          {gap.headcount_gap > 0
            ? t("gap.minimumShort", {
                minimum: gap.effective_minimum,
                onShift: gap.effective_minimum - gap.headcount_gap,
              })
            : t("gap.minimum", { minimum: gap.effective_minimum })}
        </span>
        <span className="ml-4 text-sm text-slate-500">{t("gap.computed", { time: formatDateTime(gap.computed_at) })}</span>
      </p>
      {gap.intervals.length > 1 && (
        <p className="mt-2 text-sm">{t("gap.changes")}</p>
      )}
      <GapIntervals intervals={gap.intervals} />
      {rows.length === 0 ? (
        <p className="mt-2">{t("gap.noRequirements")}</p>
      ) : (
        <ScrollX>
          <table aria-label={t("common.gap")} className="mt-2">
            <thead>
              <tr>
                <th>{t("gap.type")}</th>
                <th>{t("common.name")}</th>
                <th>{t("gap.required")}</th>
                <th>{t("gap.current")}</th>
                <th>{t("common.gap")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.kind}-${row.id}`}>
                  <td>{row.kind}</td>
                  <td>{row.name}</td>
                  <td>{row.required_count}</td>
                  <td>{row.current_count}</td>
                  <td><Shortage count={row.gap_count} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollX>
      )}
    </>
  );
}
