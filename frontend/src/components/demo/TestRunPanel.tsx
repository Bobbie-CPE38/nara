"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ApiError, apiRequest } from "@/lib/api";
import { describeError } from "@/lib/errors";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import { TESTER_CODE_PATTERN, formatSeconds } from "@/lib/testRuns";
import {
  TEST_RUN_SCENARIOS,
  type TestRunClosed,
  type TestRunScenario,
  type TestRunStarted,
  type TestRunView,
} from "@/lib/types/testRun";

const SCENARIO_LABELS: Record<TestRunScenario, MessageKey> = {
  golden: "run.scenario.golden",
  cross_ward: "run.scenario.cross_ward",
  // Round 6 PR EV7 (docs/workflow.md 6.37.10)
  surge: "run.scenario.surge",
  no_show: "run.scenario.no_show",
  handoff: "run.scenario.handoff",
  supervisor: "run.scenario.supervisor",
};

/** The scenario's name in the language of the page; an unknown one as the Backend sent it. */
export function useScenarioLabel() {
  const t = useT();
  return (scenario: string) =>
    scenario in SCENARIO_LABELS ? t(SCENARIO_LABELS[scenario as TestRunScenario]) : scenario;
}

type Outcome =
  | { kind: "started"; run: TestRunStarted }
  | { kind: "closed"; closed: TestRunClosed }
  | { kind: "error"; cause: unknown };

/**
 * The test-run part of the Demo control (round 6 PR EV5b, docs/workflow.md 6.35.5): start a run
 * for a tester code, then finish or abort it. Starting is a demo reset, which keeps every login
 * and LINE binding since round 6 PR EV6 (6.36.2).
 */
export function TestRunPanel({
  open,
  runsError,
  blocked = false,
  onBusyChange,
  onChange,
}: {
  /** The open run, read from GET /demo/test-runs; undefined when there is none */
  open: TestRunView | undefined;
  runsError: Error | null;
  /** Another request of the page is running, for example an advance of the clock */
  blocked?: boolean;
  /** Tell the page while a request of this panel runs, so its own buttons wait too */
  onBusyChange?: (busy: boolean) => void;
  /** Read the list again after a start, a finish or an abort */
  onChange: () => void;
}) {
  const t = useT();
  const scenarioLabel = useScenarioLabel();
  const [code, setCode] = useState("");
  const [scenario, setScenario] = useState<TestRunScenario>("golden");
  const [autoNurses, setAutoNurses] = useState(true);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const codeValid = TESTER_CODE_PATTERN.test(code);
  const waiting = busy || blocked;

  async function act(action: () => Promise<Outcome>) {
    setBusy(true);
    onBusyChange?.(true);
    setOutcome(null);
    try {
      setOutcome(await action());
    } catch (cause) {
      setOutcome({ kind: "error", cause });
    } finally {
      setBusy(false);
      onBusyChange?.(false);
      onChange();
    }
  }

  const start = () =>
    act(async () => ({
      kind: "started",
      run: await apiRequest<TestRunStarted>("/demo/test-runs", {
        method: "POST",
        json: { tester_code: code, scenario, auto_nurses: autoNurses },
      }),
    }));

  const close = (how: "finish" | "abort") => {
    if (open === undefined) return;
    const id = open.test_run_id;
    return act(async () => ({
      kind: "closed",
      closed: await apiRequest<TestRunClosed>(`/demo/test-runs/${id}/${how}`, {
        method: "POST",
        json: how === "abort" && reason.trim() ? { reason: reason.trim() } : undefined,
      }),
    }));
  };

  return (
    <fieldset className="mt-4 flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 shadow-md">
      <legend className="px-1 font-semibold text-brand-800">{t("run.title")}</legend>
      <p className="text-sm text-slate-600">{t("run.intro")}</p>
      {runsError && (
        <Notice kind="warning" role="status">
          {t("run.listFailed", { error: describeError(runsError, t) })}
        </Notice>
      )}
      {open === undefined ? (
        <>
          <label htmlFor="run-code">
            {t("run.code")}{" "}
            <input
              id="run-code"
              value={code}
              maxLength={16}
              disabled={waiting}
              aria-invalid={code !== "" && !codeValid}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <p className="text-sm text-slate-500">{t("run.codeHint")}</p>
          <label htmlFor="run-scenario">
            {t("run.scenario")}{" "}
            <select
              id="run-scenario"
              value={scenario}
              disabled={waiting}
              onChange={(event) => setScenario(event.target.value as TestRunScenario)}
            >
              {TEST_RUN_SCENARIOS.map((item) => (
                <option key={item} value={item}>
                  {scenarioLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={autoNurses}
              disabled={waiting}
              onChange={(event) => setAutoNurses(event.target.checked)}
            />
            {t("run.autoNurses")}
          </label>
          <div>
            <Button variant="primary" disabled={waiting || !codeValid} onClick={start}>
              {t("run.start")}
            </Button>
          </div>
        </>
      ) : (
        <>
          <p role="status">
            {t("run.inProgress", {
              id: open.test_run_id,
              code: open.tester_code,
              scenario: scenarioLabel(open.scenario),
            })}{" "}
            {t(open.auto_nurses ? "run.withAutoNurses" : "run.withoutAutoNurses")}
          </p>
          {open.elapsed_seconds === null ? (
            <Notice kind="warning" role="status">
              {t("run.clockLost")}
            </Notice>
          ) : (
            <p>
              {t("run.elapsed", {
                time: formatSeconds(open.elapsed_seconds),
                advanced: formatSeconds(open.advanced_seconds),
              })}
            </p>
          )}
          <div className="flex flex-wrap items-end gap-2">
            <Button variant="primary" disabled={waiting} onClick={() => close("finish")}>
              {t("run.finish")}
            </Button>
            <label htmlFor="run-reason">
              {t("run.reason")}{" "}
              <input
                id="run-reason"
                value={reason}
                maxLength={100}
                disabled={waiting}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <Button disabled={waiting} onClick={() => close("abort")}>
              {t("run.abort")}
            </Button>
          </div>
        </>
      )}
      {busy && <p>{t("ctl.working")}</p>}
      {outcome?.kind === "started" && (
        <p className="font-medium text-green-700">
          {t("run.started", { id: outcome.run.test_run_id })}{" "}
          {outcome.run.case_id !== null && (
            <Link className="underline" href={`/cases/${outcome.run.case_id}`}>
              {t("run.openCase", { id: outcome.run.case_id })}
            </Link>
          )}
        </p>
      )}
      {outcome?.kind === "closed" &&
        (outcome.closed.result.invalid ? (
          <p className="font-medium text-amber-800">
            {t("run.closedInvalid", {
              id: outcome.closed.test_run_id,
              reason: outcome.closed.result.reason ?? "—",
            })}
          </p>
        ) : (
          <p className="font-medium text-green-700">
            {t("run.finished", {
              id: outcome.closed.test_run_id,
              time: formatSeconds(outcome.closed.result.time_to_fill_s),
            })}
          </p>
        ))}
      {outcome?.kind === "error" && (
        <p className="text-red-700" role="alert">
          {describeError(outcome.cause, t)}
          {outcome.cause instanceof ApiError ? ` (HTTP ${outcome.cause.status})` : ""}
        </p>
      )}
      <p>
        <Link className="underline" href="/demo/test-runs">
          {t("run.results")}
        </Link>
      </p>
    </fieldset>
  );
}
