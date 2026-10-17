"use client";

import { useCallback, useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { DEMO_APPROVER_ID, DEMO_SHIFT_IDS, formatDemoTime } from "@/lib/demo";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { ShiftRoster } from "@/lib/types/roster";

const api = createDemoApi(DEMO_APPROVER_ID);

const COLUMNS: readonly MessageKey[] = [
  "roster.col.assignment",
  "common.staff",
  "common.role",
  "cand.homeWard",
  "roster.col.staffStatus",
  "roster.col.rosterStatus",
  "roster.col.type",
  "cand.source",
  "roster.col.interval",
  "roster.col.transferred",
];

function Roster({ shiftId }: { shiftId: number }) {
  const t = useT();
  const load = useCallback(
    (signal: AbortSignal) =>
      api<ShiftRoster>(`/roster?shift_id=${shiftId}`, { signal }),
    [shiftId],
  );
  const { data, error, isLoading } = usePolling(load);
  return (
    <section className="mt-6 space-y-4" aria-label={t("roster.title")}>
      {isLoading && <p role="status">{t("roster.loading")}</p>}
      {error && (
        <Notice kind="error" role="alert">
          {t("roster.refreshFailed", { error: describeError(error, t) })}
        </Notice>
      )}
      {data && (
        <Card>
          <h2 className="text-lg font-semibold text-brand-800">
            {t("roster.heading", {
              ward: data.shift.ward_name,
              id: data.shift.id,
              type: data.shift.shift_type,
            })}
            {!data.shift.is_active && t("roster.inactive")}
          </h2>
          <p className="mt-1">
            {formatDemoTime(data.shift.start_at)} –{" "}
            {formatDemoTime(data.shift.end_at)} {t("roster.bangkok")}
          </p>
          {data.assignments.length === 0 ? (
            <p className="mt-3">{t("roster.none")}</p>
          ) : (
            <ScrollX>
              <table className="mt-3 text-sm">
                <caption className="sr-only">
                  {t("roster.caption", { id: shiftId })}
                </caption>
                <thead>
                  <tr>
                    {COLUMNS.map((label) => (
                      <th key={label} scope="col">
                        {t(label)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.assignments.map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td>
                      <td>
                        {row.staff_id} — {row.first_name} {row.last_name}
                      </td>
                      <td>{row.role_name}</td>
                      <td>
                        {row.home_ward_name}
                        {row.home_ward_id !== data.shift.ward_id &&
                          t("roster.crossWard")}
                      </td>
                      <td>{row.staff_status}</td>
                      <td className="font-medium">
                        {row.status}
                        {row.is_unavailable && (
                          <span className="ml-2">
                            <Badge tone="waiting">{t("roster.onLeave")}</Badge>
                          </span>
                        )}
                      </td>
                      <td>{row.assignment_type}</td>
                      <td>{row.candidate_source ?? "—"}</td>
                      <td>
                        {formatDemoTime(row.actual_start_at ?? data.shift.start_at)} –{" "}
                        {formatDemoTime(row.actual_end_at ?? data.shift.end_at)}
                      </td>
                      <td>{row.transferred_from_assignment_id ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollX>
          )}
          <p className="mt-3 text-sm text-slate-600">{t("roster.note")}</p>
        </Card>
      )}
    </section>
  );
}

export default function RosterPage() {
  const t = useT();
  const [shiftId, setShiftId] = useState<number>(DEMO_SHIFT_IDS[0]);
  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("roster.title")} description={t("roster.intro", { id: DEMO_APPROVER_ID })}>
        <label className="flex flex-wrap items-center gap-2 text-sm font-medium" htmlFor="shift">
          {t("common.shift")}
          <select
            id="shift"
            value={shiftId}
            onChange={(event) => setShiftId(Number(event.target.value))}
          >
            {DEMO_SHIFT_IDS.map((id) => (
              <option key={id} value={id}>
                {t("roster.shiftOption", { id })}
              </option>
            ))}
          </select>
        </label>
      </PageHeader>
      <Roster key={shiftId} shiftId={shiftId} />
    </main>
  );
}
