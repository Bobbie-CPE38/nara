"use client";

import { useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { useScenarioLabel } from "@/components/demo/TestRunPanel";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { useTestRuns } from "@/hooks/useTestRuns";
import { apiRequest } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import { formatSeconds, spread, validRuns } from "@/lib/testRuns";
import { KPI_INTERVALS, type KpiInterval, type TestRunView } from "@/lib/types/testRun";

const INTERVAL_LABELS: Record<KpiInterval, MessageKey> = {
  detect_s: "runs.kpi.detect",
  shortlist_s: "runs.kpi.shortlist",
  first_offer_s: "runs.kpi.firstOffer",
  first_accept_s: "runs.kpi.firstAccept",
  approval_s: "runs.kpi.approval",
  time_to_fill_s: "runs.kpi.timeToFill",
};

/**
 * Results of the test runs (round 6 PR EV5b, docs/workflow.md 6.35.5): every run, the median
 * and range of the valid ones, and the CSV of 6.35.2. Times are what the tester really
 * spent: clock advances are taken out (6.35.4).
 */
export default function TestRuns() {
  const t = useT();
  const scenarioLabel = useScenarioLabel();
  const { data: runs, error, isLoading } = useTestRuns();
  const [downloadError, setDownloadError] = useState<unknown>(null);

  const yesNo = (value: boolean | null | undefined) =>
    value === null || value === undefined ? "—" : t(value ? "runs.yes" : "runs.no");

  function status(run: TestRunView): string {
    if (run.open) return t("runs.open");
    return run.invalid ? t("runs.invalid", { reason: run.reason ?? "—" }) : t("runs.valid");
  }

  async function download() {
    setDownloadError(null);
    try {
      const text = await apiRequest<string>("/demo/test-runs.csv");
      const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "test-runs.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setDownloadError(cause);
    }
  }

  const valid = runs ? validRuns(runs) : [];

  return (
    <main className="mx-auto max-w-5xl px-4 py-6 sm:py-8">
      <PageHeader title={t("runs.title")} />
      <p className="mb-4 text-sm text-slate-600">{t("runs.intro")}</p>
      {error && (
        <div className="mb-4">
          <Notice kind="error" role="alert">
            {t("run.listFailed", { error: describeError(error, t) })}
          </Notice>
        </div>
      )}
      {isLoading && runs === undefined && <p>{t("runs.loading")}</p>}
      {runs !== undefined && runs.length === 0 && <p>{t("runs.empty")}</p>}
      {runs !== undefined && runs.length > 0 && (
        <>
          <Card>
            <h2 className="mb-2 font-semibold">
              {t("runs.summary", {
                valid: valid.length,
                filled: valid.filter((run) => run.kpi?.time_to_fill_s !== null).length,
                total: runs.length,
              })}
            </h2>
            <ScrollX>
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-left">{t("runs.kpi")}</th>
                    <th className="text-right">{t("runs.median")}</th>
                    <th className="text-right">{t("runs.range")}</th>
                    <th className="text-right">{t("runs.count")}</th>
                  </tr>
                </thead>
                <tbody>
                  {KPI_INTERVALS.map((key) => {
                    const values = spread(runs, key);
                    return (
                      <tr key={key}>
                        <td>{t(INTERVAL_LABELS[key])}</td>
                        <td className="whitespace-nowrap text-right">{formatSeconds(values?.median)}</td>
                        <td className="whitespace-nowrap text-right">
                          {values ? `${formatSeconds(values.min)} – ${formatSeconds(values.max)}` : "—"}
                        </td>
                        <td className="whitespace-nowrap text-right">{values?.count ?? 0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </ScrollX>
          </Card>

          <Card className="mt-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">{t("runs.all")}</h2>
              <Button onClick={() => void download()}>{t("runs.csv")}</Button>
            </div>
            {downloadError !== null && (
              <Notice kind="error" role="alert">
                {t("runs.csvFailed", { error: describeError(downloadError, t) })}
              </Notice>
            )}
            <ScrollX>
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-left">{t("runs.id")}</th>
                    <th className="text-left">{t("run.code")}</th>
                    <th className="text-left">{t("run.scenario")}</th>
                    <th className="text-left">{t("runs.auto")}</th>
                    <th className="text-left">{t("runs.startedAt")}</th>
                    <th className="text-left">{t("runs.status")}</th>
                    <th className="text-right">{t("runs.kpi.timeToFill")}</th>
                    <th className="text-right">{t("runs.kpi.firstOffer")}</th>
                    <th className="text-right">{t("runs.kpi.firstAccept")}</th>
                    <th className="text-right">{t("runs.kpi.approval")}</th>
                    <th className="text-left">{t("runs.beforeStart")}</th>
                    <th className="text-right">{t("runs.offers")}</th>
                    <th className="text-left">{t("runs.otherWard")}</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.test_run_id}>
                      <td>{run.test_run_id}</td>
                      <td>{run.tester_code}</td>
                      <td>{scenarioLabel(run.scenario)}</td>
                      <td>{yesNo(run.auto_nurses)}</td>
                      <td>{run.started_real_at ? formatDateTime(run.started_real_at) : "—"}</td>
                      <td>{status(run)}</td>
                      <td className="whitespace-nowrap text-right">{formatSeconds(run.kpi?.time_to_fill_s)}</td>
                      <td className="whitespace-nowrap text-right">{formatSeconds(run.kpi?.first_offer_s)}</td>
                      <td className="whitespace-nowrap text-right">{formatSeconds(run.kpi?.first_accept_s)}</td>
                      <td className="whitespace-nowrap text-right">{formatSeconds(run.kpi?.approval_s)}</td>
                      <td>{yesNo(run.kpi?.filled_before_shift_start)}</td>
                      <td className="whitespace-nowrap text-right">{run.kpi?.offers_sent ?? "—"}</td>
                      <td>{yesNo(run.kpi?.from_other_ward)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollX>
          </Card>
          <p className="mt-4 text-sm text-slate-600">{t("runs.footnote")}</p>
        </>
      )}
    </main>
  );
}
