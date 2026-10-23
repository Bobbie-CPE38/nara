"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useBackendClock } from "@/components/ClockProvider";
import { TestRunPanel } from "@/components/demo/TestRunPanel";
import { Notice } from "@/components/ui/Notice";
import { usePolling } from "@/hooks/usePolling";
import { useShiftPicker } from "@/hooks/useShiftPicker";
import { useTestRuns } from "@/hooks/useTestRuns";
import { ApiError, apiRequest } from "@/lib/api";
import { POLL_INTERVAL_MS, TERMINAL_CASE_STATUSES } from "@/lib/constants";
import { describeError } from "@/lib/errors";
import { openRun } from "@/lib/testRuns";
import { formatDateTime } from "@/lib/format";
import type { MessageKey, Params, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CheckInResult, ClockView } from "@/lib/types/attendance";
import type { ClockAdvanceResult, EventResult } from "@/lib/types/event";

// Golden Case IDs (docs/workflow.md, section 10). 900 is the head nurse, the
// only one who may report the last three event types (section 3.4)
const EVENTS: readonly { label: MessageKey; staffId: number; json: Record<string, unknown> }[] = [
  {
    label: "ctl.ev.leave105",
    staffId: 105,
    json: { event_type: "STAFF_UNAVAILABLE", shift_id: 1 },
  },
  {
    label: "ctl.ev.leave203",
    staffId: 203,
    json: { event_type: "STAFF_UNAVAILABLE", shift_id: 2 },
  },
  {
    label: "ctl.ev.cancel104",
    staffId: 900,
    json: {
      event_type: "ASSIGNMENT_CANCELLED",
      shift_id: 1,
      staff_id: 104,
      reason: "Cancelled from demo control",
    },
  },
  {
    label: "ctl.ev.surge",
    staffId: 900,
    json: { event_type: "PATIENT_SURGE", shift_id: 1, patient_count: 12 },
  },
  {
    label: "ctl.ev.require",
    staffId: 900,
    json: {
      event_type: "REQUIREMENT_CHANGED",
      shift_id: 1,
      skills: [{ skill_id: 1, required_count: 3 }],
    },
  },
];

// Moving the frozen demo clock also runs what became due, like the job does with
// real time (section 3.8): offers time out after 300 seconds, waiting cases are
// rechecked and merge windows close
const ADVANCE_SECONDS = 600;

/** A text of the page (a key and its values, in the language of the user) or the words of the API. */
type Message = { key: MessageKey; params?: Params } | { failure: unknown };

type ClockMode = NonNullable<ClockView["mode"]>;

type Outcome =
  | { kind: "reset"; clock: string }
  | { kind: "clockMode"; mode: ClockMode; clock: string }
  | { kind: "clock"; result: ClockAdvanceResult }
  | { kind: "event"; label: Message; result: EventResult }
  | { kind: "checkIn"; label: Message; result: CheckInResult }
  | { kind: "error"; label: Message; message: Message };

/** What the clock does after a clock button, in the words of the page (round 6 PR EV6). */
const CLOCK_MODE_TEXT: Record<ClockMode, MessageKey> = {
  frozen: "ctl.frozenAt",
  real: "ctl.unfrozen",
  running: "ctl.runningFrom",
  scenario: "ctl.runningFrom",
};

/** The Backend Clock as the value of a datetime-local field, in Bangkok time */
function localInput(iso: string | undefined): string {
  return iso ? formatDateTime(iso).slice(0, 16).replace(" ", "T") : "";
}

/** An error as the user reads it; called when the page renders, so a switch of language also reaches it. */
function errorText(cause: unknown, t: Translate): string {
  return cause instanceof ApiError ? `${describeError(cause, t)} (HTTP ${cause.status})` : describeError(cause, t);
}

function CaseLink({ id, status }: { id: number; status: string | null }) {
  const t = useT();
  const load = useCallback(
    async (signal: AbortSignal) => {
      const result = await apiRequest<{ id: number; status: string }>(
        `/cases/${id}`,
        { signal },
      );
      if (!result || result.id !== id || typeof result.status !== "string") {
        throw new Error("Invalid case status response");
      }
      return result;
    },
    [id],
  );
  const { data, error, isLoading, refresh } = usePolling(load, {
    stopOnData: (result) => TERMINAL_CASE_STATUSES.has(result.status),
    stopOnError: (cause) => cause instanceof ApiError && cause.status === 404,
  });
  const missing = error instanceof ApiError && error.status === 404;
  const latest = data?.status ?? status;
  return (
    <span>
      <Link className="underline" href={`/cases/${id}`}>
        {id}
        {!missing && latest !== null ? ` (${latest})` : ""}
      </Link>
      {missing ? (
        <span role="status">{t("ctl.caseGone")}</span>
      ) : error ? (
        <span role="status">
          {t("ctl.statusOutdated", {
            error: errorText(error, t),
          })}
        </span>
      ) : (
        <span className="text-sm text-slate-500">
          {isLoading
            ? t("ctl.checking")
            : latest !== null && TERMINAL_CASE_STATUSES.has(latest)
              ? t("ctl.final")
              : t("ctl.updating", { seconds: POLL_INTERVAL_MS / 1000 })}
        </span>
      )}
      {!missing && (
        <button type="button" className="ml-2 underline" onClick={() => void refresh()}>
          {t("ctl.refreshCase", { id })}
        </button>
      )}
    </span>
  );
}

export default function DemoControl() {
  const t = useT();
  const [busy, setBusy] = useState(false);
  // One request at a time on the whole page: an advance and a Finish or Abort of the test-run
  // panel never overlap (review of #144; the Backend also serializes them)
  const [panelBusy, setPanelBusy] = useState(false);
  const working = busy || panelBusy;
  // The buttons that need a frozen clock, or a running one, follow the one shared read of /clock
  const clockView = useBackendClock().data;
  const clockFrozen = clockView?.frozen;
  // A test run's clock can be advanced too (6.35.1); an older Backend sends no mode
  const canAdvance = clockView === undefined || (clockView.mode ?? (clockView.frozen ? "frozen" : "real")) !== "real";
  // While a test run is open, Reset and the clock buttons would spoil it (6.35.2)
  const testRuns = useTestRuns();
  const runOpen = openRun(testRuns.data);
  // Off until the first list has come: the Backend would refuse them during a run anyway
  const runsKnown = testRuns.data !== undefined || testRuns.error !== null;
  const runBlocks = runOpen !== undefined || !runsKnown;
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // A leave or a check-in of anyone on any ward, day and shift (round 6 PR EV6, 6.36.5)
  const picker = useShiftPicker();
  // The time the clock is set to; empty until the user types one, then the field keeps it
  const [clockInput, setClockInput] = useState<string | null>(null);
  const clockValue = clockInput ?? localInput(clockView?.now);
  // The hospital demo of 6.36.3: five more wards for a week; ticked by default
  const [withHospital, setWithHospital] = useState(true);

  const text = (message: Message) => ("failure" in message ? errorText(message.failure, t) : t(message.key, message.params));

  async function run(label: Message, action: () => Promise<Outcome>) {
    setBusy(true);
    setOutcome(null);
    try {
      setOutcome(await action());
    } catch (cause) {
      setOutcome({ kind: "error", label, message: { failure: cause } });
    } finally {
      setBusy(false);
    }
  }

  const reset = () =>
    run({ key: "ctl.reset" }, async () => {
      const { clock } = await apiRequest<{ status: string; clock: string }>(
        "/demo/reset",
        { method: "POST", json: { hospital: withHospital } },
      );
      setClockInput(null);
      void picker.reload();
      return { kind: "reset", clock };
    });

  /** Freeze where it is, run on from where it is (6.36.1), or follow real time again */
  const CLOCK_BUTTONS = {
    freeze: { path: "/demo/clock/freeze", label: "ctl.freezeClock" },
    resume: { path: "/demo/clock/resume", label: "ctl.resumeClock" },
    unfreeze: { path: "/demo/clock/unfreeze", label: "ctl.unfreezeClock" },
  } as const;

  const clockOutcome = (view: ClockView): Outcome => ({
    kind: "clockMode",
    mode: view.mode ?? (view.frozen ? "frozen" : "real"),
    clock: formatDateTime(view.now),
  });

  const setClockMode = (button: keyof typeof CLOCK_BUTTONS) =>
    run({ key: CLOCK_BUTTONS[button].label }, async () => {
      const view = await apiRequest<ClockView>(CLOCK_BUTTONS[button].path, { method: "POST" });
      setClockInput(null);
      return clockOutcome(view);
    });

  // Any time within a year of real time, in Bangkok time, frozen there or running on (6.36.1)
  const setClock = (running: boolean) =>
    run({ key: running ? "ctl.setRunning" : "ctl.setFrozen" }, async () => {
      const view = await apiRequest<ClockView>("/demo/clock/set", {
        method: "POST",
        json: { at: `${clockValue}:00+07:00`, running },
      });
      setClockInput(null);
      return clockOutcome(view);
    });

  const advanceClock = () =>
    run({ key: "ctl.advance" }, async () => {
      const result = await apiRequest<ClockAdvanceResult>("/demo/clock/advance", {
        method: "POST",
        json: { seconds: ADVANCE_SECONDS },
      });
      return { kind: "clock", result };
    });

  const reportEvent = ({ label, staffId, json }: (typeof EVENTS)[number]) => {
    const name: Message = { key: label };
    return run(name, async () => {
      // POST /events is closed to every web account in session mode (docs/workflow.md 6.33.4):
      // the Demo control plays the character through /demo/events, which records the event by
      // the SYSTEM actor. In session mode it needs the login of a head nurse or a supervisor;
      // in demo mode it asks nobody. No X-Demo-User: the character is in the body
      const result = await apiRequest<EventResult>("/demo/events", {
        method: "POST",
        json: { ...json, reporter_staff_id: staffId },
      });
      return { kind: "event", label: name, result };
    });
  };

  const { ward, shift, person } = picker;
  const chosen = ward !== undefined && shift !== undefined && person !== undefined;

  const reportLeave = () => {
    if (!chosen) return;
    const name: Message = {
      key: "ctl.leaveLabel",
      params: { staff: person.staff_id, ward: ward.name, shift: shift.id },
    };
    return run(name, async () => {
      try {
        const result = await apiRequest<EventResult>("/demo/events", {
          method: "POST",
          json: { event_type: "STAFF_UNAVAILABLE", shift_id: shift.id, reporter_staff_id: person.staff_id },
        });
        return { kind: "event", label: name, result };
      } finally {
        void picker.refresh();
      }
    });
  };

  // Not the nurse's own check-in: the demo plays a character arriving (R5-Q23)
  const simulateCheckIn = () => {
    if (!chosen) return;
    const label: Message = {
      key: "ctl.checkInLabel",
      params: { staff: person.staff_id, ward: ward.name, shift: shift.id },
    };
    return run(label, async () => {
      try {
        const result = await apiRequest<CheckInResult>("/demo/attendance/check-in", {
          method: "POST",
          json: { staff_id: person.staff_id, shift_id: shift.id },
        });
        return { kind: "checkIn", label, result };
      } finally {
        void picker.refresh();
      }
    });
  };

  return (
    <main className="mx-auto max-w-3xl px-4 py-6 sm:py-8">
      <PageHeader title={t("ctl.title")} />
      <Card>
        <div className="grid gap-2 sm:grid-cols-2">
          <Button className="text-left" disabled={working || runBlocks} onClick={reset}>
            {t("ctl.reset")}
          </Button>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={withHospital}
              disabled={working}
              onChange={(event) => setWithHospital(event.target.checked)}
            />
            {t("ctl.withHospital")}
          </label>
          {EVENTS.map((event) => (
            <Button
              key={event.label}
              className="text-left"
              disabled={working}
              onClick={() => reportEvent(event)}
            >
              {t(event.label)}
            </Button>
          ))}
        </div>
        {runOpen !== undefined && (
          <div className="mt-2">
            <Notice kind="info" role="status">
              {t("run.blocked")}
            </Notice>
          </div>
        )}
      </Card>

      {/* The clock: set it to any time, frozen there or running on (round 6 PR EV6, 6.36.1) */}
      <fieldset className="mt-4 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-md">
        <legend className="px-1 font-semibold text-brand-800">{t("ctl.clockTitle")}</legend>
        <p className="text-sm text-slate-600">{t("ctl.clockIntro")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm font-medium" htmlFor="clock-at">
            {t("ctl.clockAt")}{" "}
            <input
              id="clock-at"
              type="datetime-local"
              step={60}
              value={clockValue}
              disabled={working || runBlocks}
              onChange={(event) => setClockInput(event.target.value)}
            />
          </label>
          <Button disabled={working || runBlocks || clockValue === ""} onClick={() => setClock(false)}>
            {t("ctl.setFrozen")}
          </Button>
          <Button variant="primary" disabled={working || runBlocks || clockValue === ""} onClick={() => setClock(true)}>
            {t("ctl.setRunning")}
          </Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Button className="text-left" disabled={working || !canAdvance} onClick={advanceClock}>
            {t("ctl.advance")}
          </Button>
          <Button
            className="text-left"
            disabled={working || clockFrozen === true || runBlocks}
            onClick={() => setClockMode("freeze")}
          >
            {t("ctl.freezeClock")}
          </Button>
          <Button
            className="text-left"
            disabled={working || clockView?.mode === "running" || runBlocks}
            onClick={() => setClockMode("resume")}
          >
            {t("ctl.resumeClock")}
          </Button>
          <Button
            className="text-left"
            disabled={working || (clockFrozen === false && clockView?.mode !== "running") || runBlocks}
            onClick={() => setClockMode("unfreeze")}
          >
            {t("ctl.unfreezeClock")}
          </Button>
        </div>
      </fieldset>

      <TestRunPanel
        open={runOpen}
        runsError={testRuns.error}
        blocked={busy}
        onBusyChange={setPanelBusy}
        onChange={() => {
          void testRuns.refresh();
          // Starting or ending a run resets the demo or pauses wards: what the picker lists changes
          void picker.reload();
        }}
      />

      <fieldset className="mt-4 flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 shadow-md">
        <legend className="px-1 font-semibold text-brand-800">{t("ctl.fieldset")}</legend>
        {picker.error && (
          <Notice kind="warning" role="status">
            {t("ctl.pickerFailed", { error: errorText(picker.error, t) })}
          </Notice>
        )}
        <label htmlFor="leave-ward">
          {t("common.ward")}{" "}
          <select
            id="leave-ward"
            value={ward?.id ?? ""}
            disabled={working || picker.wards.length === 0}
            onChange={(event) => picker.pickWard(Number(event.target.value))}
          >
            {picker.wards.map((item) => (
              <option key={item.id} value={item.id}>
                {item.is_active ? item.name : t("ctl.wardPaused", { ward: item.name })}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="leave-date">
          {t("gapPage.day")}{" "}
          <input
            id="leave-date"
            type="date"
            min="2000-01-01"
            max="2999-12-31"
            value={picker.date}
            disabled={working}
            onChange={(event) => picker.pickDate(event.target.value)}
          />
        </label>
        <label htmlFor="leave-shift">
          {t("common.shift")}{" "}
          <select
            id="leave-shift"
            value={shift?.id ?? ""}
            disabled={working || picker.shifts.length === 0}
            onChange={(event) => picker.pickShift(Number(event.target.value))}
          >
            {picker.shifts.map((item) => (
              <option key={item.id} value={item.id}>
                {t("ctl.shiftOption", {
                  id: item.id,
                  type: item.shift_type,
                  from: formatDateTime(item.start_at).slice(11, 16),
                  until: formatDateTime(item.end_at).slice(11, 16),
                })}
              </option>
            ))}
          </select>
        </label>
        {ward !== undefined && picker.date !== "" && picker.shifts.length === 0 && (
          <p className="text-sm text-slate-600">{t("gapPage.noShifts")}</p>
        )}
        <label htmlFor="leave-staff">
          {t("ctl.staffOnShift")}{" "}
          <select
            id="leave-staff"
            value={person?.staff_id ?? ""}
            disabled={working || picker.people.length === 0}
            onChange={(event) => picker.pickPerson(Number(event.target.value))}
          >
            {picker.people.map((item) => (
              <option key={item.staff_id} value={item.staff_id}>
                {`${item.staff_id} — ${item.first_name} ${item.last_name} · ${item.status}${
                  item.checked_in ? ` · ${t("ctl.checkedIn")}` : ""
                }`}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          <Button disabled={working || !chosen} onClick={reportLeave}>
            {t("ctl.reportLeave")}
          </Button>
          <Button disabled={working || !chosen} onClick={simulateCheckIn}>
            {t("ctl.simCheckIn")}
          </Button>
        </div>
      </fieldset>

      {busy && <p className="mt-4">{t("ctl.working")}</p>}
      {outcome?.kind === "reset" && (
        <p className="mt-4 font-medium text-green-700">{t("ctl.resetDone", { clock: outcome.clock })}</p>
      )}
      {outcome?.kind === "clockMode" && (
        <p className="mt-4 font-medium text-green-700">
          {t(CLOCK_MODE_TEXT[outcome.mode], { clock: outcome.clock })}
        </p>
      )}
      {outcome?.kind === "error" && (
        <p className="mt-4 text-red-700">
          {text(outcome.label)}: {text(outcome.message)}
        </p>
      )}
      {outcome?.kind === "clock" && (
        <Card className="mt-4">
          <p className="font-medium text-green-700">{t("ctl.clock", { clock: outcome.result.clock })}</p>
          {outcome.result.closed_windows.length === 0 ? (
            <p>{t("ctl.noWindow")}</p>
          ) : (
            <ul className="list-disc pl-5">
              {outcome.result.closed_windows.map((window) => (
                <li key={window.shift_id}>
                  {t("ctl.window", { shift: window.shift_id, events: window.event_ids.join(", ") })}{" "}
                  {window.case_id === null ? (
                    t("ctl.noCaseOpened")
                  ) : (
                    <CaseLink
                      key={window.case_id}
                      id={window.case_id}
                      status={window.case_status}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
          {outcome.result.timed_out_approval_request_ids.length > 0 && (
            <p>{t("ctl.approvalsTimedOut", { ids: outcome.result.timed_out_approval_request_ids.join(", ") })}</p>
          )}
          {outcome.result.timed_out_outreach_ids.length > 0 && (
            <p>{t("ctl.offersTimedOut", { ids: outcome.result.timed_out_outreach_ids.join(", ") })}</p>
          )}
          {(outcome.result.no_show_event_ids ?? []).length > 0 && (
            <p>{t("ctl.noShows", { ids: outcome.result.no_show_event_ids.join(", ") })}</p>
          )}
          {outcome.result.recovered_case_ids.length > 0 && (
            <p>
              {t("ctl.rechecked")}{" "}
              {outcome.result.recovered_case_ids.map((id, index) => (
                <span key={id}>
                  {index > 0 && ", "}
                  <CaseLink id={id} status={null} />
                </span>
              ))}
            </p>
          )}
        </Card>
      )}
      {outcome?.kind === "checkIn" && (
        <p className={outcome.result.on_time ? "mt-4 text-green-700" : "mt-4 text-amber-700"}>
          {t("ctl.checkInResult", {
            label: text(outcome.label),
            when: t(outcome.result.on_time ? "me.onTime" : "me.late"),
            time: formatDateTime(outcome.result.check_in_at),
            deadline: formatDateTime(outcome.result.deadline),
          })}
        </p>
      )}
      {outcome?.kind === "event" && (
        <Card className="mt-4">
          <dl className="grid grid-cols-2 gap-2">
            <dt className="font-medium">{t("ctl.action")}</dt>
            <dd>{text(outcome.label)}</dd>
            <dt className="font-medium">{t("ctl.event")}</dt>
            <dd>
              {outcome.result.event_id} ({outcome.result.event_status})
            </dd>
            <dt className="font-medium">{t("ctl.caseStatusAtEvent")}</dt>
            <dd>{outcome.result.case_status ?? t("dash.noCaseYet")}</dd>
            <dt className="font-medium">{t("ctl.caseCurrent")}</dt>
            <dd>
              {outcome.result.case_id !== null ? (
                <CaseLink
                  key={outcome.result.case_id}
                  id={outcome.result.case_id}
                  status={outcome.result.case_status}
                />
              ) : outcome.result.event_status === "RECEIVED" ? (
                // Its shift has an open merge window, or a case that is still running
                t("ctl.eventWaiting")
              ) : (
                t("ctl.noCaseOpenedCap")
              )}
            </dd>
          </dl>
        </Card>
      )}
    </main>
  );
}
