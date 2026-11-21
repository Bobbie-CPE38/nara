// @vitest-environment jsdom
// Test runs in the web app (round 6 PR EV5b, docs/workflow.md 6.35.5).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DemoControl from "../../../src/app/demo/control/page";
import TestRuns from "../../../src/app/demo/test-runs/page";
import { ClockProvider } from "../../../src/components/ClockProvider";
import { DemoClock } from "../../../src/components/DemoClock";
import { LanguageProvider } from "../../../src/lib/i18n/LanguageProvider";
import { formatSeconds, spread } from "../../../src/lib/testRuns";
import type { TestRunKpi, TestRunView } from "../../../src/lib/types/testRun";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function kpi(timeToFill: number | null, extra: Partial<TestRunKpi> = {}): TestRunKpi {
  return {
    detect_s: 0,
    shortlist_s: 0,
    first_offer_s: 0,
    first_accept_s: 2,
    approval_s: 1,
    time_to_fill_s: timeToFill,
    filled_before_shift_start: timeToFill !== null,
    offers_sent: 2,
    candidates_skipped_by_rules: 11,
    from_other_ward: false,
    ...extra,
  };
}

function run(id: number, overrides: Partial<TestRunView> = {}): TestRunView {
  return {
    test_run_id: id,
    tester_code: `T0${id}`,
    scenario: "golden",
    auto_nurses: true,
    started_at: "2026-10-23T21:00:00+07:00",
    started_real_at: "2026-10-23T14:00:00+07:00",
    open: false,
    elapsed_seconds: null,
    invalid: false,
    reason: null,
    advanced_seconds: 0,
    kpi: kpi(60),
    ...overrides,
  };
}

const OPEN = run(7, { open: true, invalid: null, kpi: null, elapsed_seconds: 95, advanced_seconds: 60 });

type Call = { method: string; path: string; body: unknown };

/** Answer the reads of the pages and record every call. */
function backend(
  runs: TestRunView[],
  answers: Record<string, unknown> = {},
  clock: Record<string, unknown> = { now: "2026-10-23T21:01:35+07:00", frozen: false, mode: "scenario" },
) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    const method = init?.method ?? "GET";
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === "/clock") return new Response(JSON.stringify(clock));
    if (method === "GET" && path === "/demo/test-runs") return new Response(JSON.stringify(runs));
    const key = `${method} ${path}`;
    if (key in answers) {
      const answer = answers[key];
      return new Response(typeof answer === "string" ? answer : JSON.stringify(answer));
    }
    return new Response("{}", { status: 404 });
  }));
  return calls;
}

function control(lang: "th" | "en" = "en") {
  render(
    <LanguageProvider initial={lang}>
      <ClockProvider>
        <DemoControl />
      </ClockProvider>
    </LanguageProvider>,
  );
}

const button = (name: string | RegExp) => screen.getByRole<HTMLButtonElement>("button", { name });

describe("the test run on the Demo control", () => {
  it("starts a run with a tester code and links to its case", async () => {
    const calls = backend([], {
      "POST /demo/test-runs": { test_run_id: 9, scenario: "cross_ward", started_at: "2026-10-23T21:00:00+07:00", case_id: 1 },
    });
    control();

    expect(button("Start test run").disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Tester code"), { target: { value: "Somchai Jaidee" } });
    expect(button("Start test run").disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Tester code"), { target: { value: "T09" } });
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "cross_ward" } });
    fireEvent.click(button("Start test run"));

    expect(await screen.findByText("Run 9 started.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open case 1" }).getAttribute("href")).toBe("/cases/1");
    const start = calls.find((call) => call.method === "POST");
    expect(start).toEqual({
      method: "POST",
      path: "/demo/test-runs",
      body: { tester_code: "T09", scenario: "cross_ward", auto_nurses: true },
    });
  });

  it("turns off Reset, Freeze and Unfreeze while a run is open, and keeps Advance", async () => {
    backend([OPEN]);
    control();

    expect(await screen.findByText(/Run 7 in progress: tester T07, Golden Case/)).toBeTruthy();
    await waitFor(() => expect(button("Reset demo").disabled).toBe(true));
    expect(button("Freeze clock").disabled).toBe(true);
    expect(button("Unfreeze clock (real time)").disabled).toBe(true);
    expect(screen.getByText(/A test run is in progress/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start test run" })).toBeNull();
    // A test run's clock can be moved past the waits (6.35.1)
    await waitFor(() => expect(button("Advance clock").disabled).toBe(false));
    expect(screen.getByText("Time so far on the system clock: 95 s (advanced: 60 s).")).toBeTruthy();
  });

  it("finishes the open run and shows its time to fill", async () => {
    const calls = backend([OPEN], {
      "POST /demo/test-runs/7/finish": { test_run_id: 7, result: { invalid: false, ...kpi(35.6) } },
    });
    control();
    fireEvent.click(await screen.findByRole("button", { name: "Finish run" }));

    expect(await screen.findByText("Run 7 finished. Time to fill: 36 s.")).toBeTruthy();
    expect(calls.some((call) => call.method === "POST" && call.path === "/demo/test-runs/7/finish")).toBe(true);
  });

  it("aborts with the reason given", async () => {
    const calls = backend([OPEN], {
      "POST /demo/test-runs/7/abort": { test_run_id: 7, result: { invalid: true, reason: "tester left" } },
    });
    control();
    fireEvent.change(await screen.findByLabelText("Reason (optional)"), { target: { value: " tester left " } });
    fireEvent.click(button("Abort run"));

    expect(await screen.findByText("Run 7 closed without KPI: tester left.")).toBeTruthy();
    const abort = calls.find((call) => call.path === "/demo/test-runs/7/abort");
    expect(abort?.body).toEqual({ reason: "tester left" });
  });

  it("says when the server lost the run's clock", async () => {
    backend([{ ...OPEN, elapsed_seconds: null }], {}, { now: "2026-10-23T14:00:00+07:00", frozen: false, mode: "real" });
    control();

    expect(await screen.findByText(/lost this run's clock/)).toBeTruthy();
    expect(button("Finish run").disabled).toBe(false);
  });

  it("keeps Reset, Freeze and Unfreeze off until the list of runs has come", async () => {
    let answerList!: () => void;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const path = new URL(url).pathname;
      if (path === "/clock") return new Response(JSON.stringify({ now: "2026-10-23T21:00:00+07:00", frozen: true }));
      if (path === "/demo/test-runs") {
        await new Promise<void>((resolve) => { answerList = resolve; });
        return new Response("[]");
      }
      return new Response("{}", { status: 404 });
    }));
    control();

    await waitFor(() => expect(answerList).toBeTypeOf("function"));
    expect(button("Reset demo").disabled).toBe(true);
    expect(button("Freeze clock").disabled).toBe(true);
    answerList();
    await waitFor(() => expect(button("Reset demo").disabled).toBe(false));
  });

  it("keeps Finish and Abort off while the clock is advancing", async () => {
    let finishAdvance!: () => void;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      if (path === "/clock") return new Response(JSON.stringify({ now: "2026-10-23T21:00:00+07:00", frozen: false, mode: "scenario" }));
      if (path === "/demo/test-runs") return new Response(JSON.stringify([OPEN]));
      if (init?.method === "POST" && path === "/demo/clock/advance") {
        await new Promise<void>((resolve) => { finishAdvance = resolve; });
        return new Response(JSON.stringify({
          clock: "2026-10-23T21:10:00+07:00", closed_windows: [], auto_approved_request_ids: [],
          failed_auto_approval_ward_ids: [], no_show_event_ids: [], timed_out_outreach_ids: [],
          timed_out_approval_request_ids: [], recovered_case_ids: [],
        }));
      }
      return new Response("{}", { status: 404 });
    }));
    control();
    await waitFor(() => expect(button("Advance clock").disabled).toBe(false));

    fireEvent.click(button("Advance clock"));

    await waitFor(() => expect(button("Finish run").disabled).toBe(true));
    expect(button("Abort run").disabled).toBe(true);
    finishAdvance();
    await waitFor(() => expect(button("Finish run").disabled).toBe(false));
  });

  it("keeps the Advance button off while the panel finishes a run", async () => {
    let finishRun!: () => void;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      if (path === "/clock") return new Response(JSON.stringify({ now: "2026-10-23T21:00:00+07:00", frozen: false, mode: "scenario" }));
      if (path === "/demo/test-runs") return new Response(JSON.stringify([OPEN]));
      if (init?.method === "POST" && path === "/demo/test-runs/7/finish") {
        await new Promise<void>((resolve) => { finishRun = resolve; });
        return new Response(JSON.stringify({ test_run_id: 7, result: { invalid: false, ...kpi(30) } }));
      }
      return new Response("{}", { status: 404 });
    }));
    control();
    fireEvent.click(await screen.findByRole("button", { name: "Finish run" }));

    await waitFor(() => expect(button("Advance clock").disabled).toBe(true));
    finishRun();
    expect(await screen.findByText("Run 7 finished. Time to fill: 30 s.")).toBeTruthy();
  });

  it("offers the scenarios of round 6 PR EV7 too", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const path = new URL(url).pathname;
      if (path === "/clock") return new Response(JSON.stringify({ now: "2026-10-23T21:00:00+07:00", frozen: true }));
      if (path === "/demo/test-runs") return new Response("[]");
      return new Response("[]");
    }));
    control();
    const scenario = await screen.findByLabelText<HTMLSelectElement>("Scenario");
    expect(Array.from(scenario.options).map((option) => option.value)).toEqual([
      "golden",
      "cross_ward",
      "surge",
      "no_show",
      "handoff",
      "supervisor",
    ]);
  });

  it("is in Thai", async () => {
    backend([]);
    control("th");

    expect(await screen.findByRole("group", { name: "รอบทดสอบ" })).toBeTruthy();
    expect(button("เริ่มรอบทดสอบ")).toBeTruthy();
  });
});

describe("the test-run results page", () => {
  const RUNS = [
    run(1, { kpi: kpi(40) }),
    run(2, { kpi: kpi(100, { from_other_ward: true }), scenario: "cross_ward" }),
    run(3, { invalid: true, reason: "ABORTED", kpi: null }),
    run(4, { kpi: kpi(null) }),
    { ...OPEN, test_run_id: 5 },
  ];

  it("summarizes the valid runs and lists every run", async () => {
    backend(RUNS);
    render(<LanguageProvider initial="en"><TestRuns /></LanguageProvider>);

    expect(await screen.findByText("3 valid runs (2 filled) of 5")).toBeTruthy();
    const timeToFill = screen.getAllByRole("row").find((row) => row.textContent?.startsWith("Time to fill"));
    // 40 and 100 seconds: the run that filled nobody and the aborted one are not counted
    expect(within(timeToFill as HTMLElement).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "Time to fill", "70 s", "40 s – 100 s", "2",
    ]);
    expect(screen.getByText("Not counted (ABORTED)")).toBeTruthy();
    expect(screen.getByText("In progress")).toBeTruthy();
    expect(screen.getAllByText("Cross-ward (no safe ICU nurse, two-ward approval)")).toHaveLength(1);
  });

  it("downloads the CSV of the Backend", async () => {
    const calls = backend(RUNS, { "GET /demo/test-runs.csv": "test_run_id,tester_code\n1,T01\n" });
    const createObjectURL = vi.fn(() => "blob:runs");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    render(<LanguageProvider initial="en"><TestRuns /></LanguageProvider>);

    fireEvent.click(await screen.findByRole("button", { name: "Download CSV" }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    expect(calls.some((call) => call.path === "/demo/test-runs.csv")).toBe(true);
  });

  it("says there is no run yet, in Thai", async () => {
    backend([]);
    render(<LanguageProvider initial="th"><TestRuns /></LanguageProvider>);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("ผลรอบทดสอบ");
    expect(await screen.findByText("ยังไม่มีรอบทดสอบ")).toBeTruthy();
  });
});

describe("test-run helpers and the clock", () => {
  it("takes the median of the valid runs only", () => {
    const runs = [run(1, { kpi: kpi(10) }), run(2, { kpi: kpi(30) }), run(3, { kpi: kpi(20) })];
    expect(spread(runs, "time_to_fill_s")).toEqual({ count: 3, median: 20, min: 10, max: 30 });
    expect(spread(runs.slice(0, 2), "time_to_fill_s")?.median).toBe(20);
    expect(spread([run(4, { invalid: true, kpi: null })], "time_to_fill_s")).toBeNull();
  });

  it("formats seconds", () => {
    expect(formatSeconds(null)).toBe("—");
    expect(formatSeconds(0.4)).toBe("0 s");
    expect(formatSeconds(119.6)).toBe("2 min 0 s");
    expect(formatSeconds(185)).toBe("3 min 5 s");
  });

  it("shows a test run's clock in the top bar", async () => {
    backend([]);
    render(<LanguageProvider initial="en"><ClockProvider><DemoClock /></ClockProvider></LanguageProvider>);

    const clock = await screen.findByRole("status", { name: "Backend clock" });
    await waitFor(() => expect(clock.textContent).toContain("(test run, real speed)"));
  });
});
