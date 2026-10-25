// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setSessionMode } from "../../../src/lib/api";
import { ClockProvider } from "../../../src/components/ClockProvider";
import { DemoClock } from "../../../src/components/DemoClock";
import { LanguageSwitch } from "../../../src/components/layout/LanguageSwitch";
import { LanguageProvider } from "../../../src/lib/i18n/LanguageProvider";
import DemoControl from "../../../src/app/demo/control/page";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// The page also reads GET /clock every second (to enable the right freeze button), the list
// of test runs (round 6 PR EV5b), and the wards and shifts to pick from (round 6 PR EV6). Those
// reads are answered here and kept out of the mock, so the tests count only the calls they
// care about.
const CLOCK_ANSWER = { now: "2026-10-09T21:00:00+07:00", frozen: true };

const WARDS = [
  { id: 1, name: "ICU", is_active: true, is_float_pool: false, head_nurse_id: 900 },
  { id: 2, name: "Medicine", is_active: true, is_float_pool: false, head_nurse_id: 902 },
  { id: 3, name: "Float Pool", is_active: true, is_float_pool: true },
];
const person = (staff_id: number, checked_in = false) => ({
  staff_id,
  first_name: `Name${staff_id}`,
  last_name: "Demo",
  status: "ASSIGNED",
  checked_in,
});
const shift = (id: number, wardId: number, start: string, staffIds: number[]) => ({
  id,
  ward_id: wardId,
  shift_type: start.endsWith("23:00:00+07:00") ? "NIGHT" : "DAY",
  start_at: start,
  end_at: start,
  people: staffIds.map((staffId) => person(staffId)),
});
/** The shifts of the seed by ward and day, as GET /demo/shifts answers them */
const SHIFTS: Record<string, unknown[]> = {
  "1/2026-10-09": [shift(1, 1, "2026-10-09T23:00:00+07:00", [101, 102, 103, 104, 105])],
  "1/2026-10-11": [shift(2, 1, "2026-10-11T07:00:00+07:00", [202, 203])],
  "2/2026-10-09": [shift(21, 2, "2026-10-09T23:00:00+07:00", [301, 302, 401, 902, 950])],
  "2/2026-10-11": [shift(22, 2, "2026-10-11T07:00:00+07:00", [301, 302, 401, 902, 950])],
};

/** The answer of a picker read, or null for any other request */
function pickerAnswer(url: string): Response | null {
  if (/\/demo\/wards$/.test(url)) return new Response(JSON.stringify(WARDS));
  // Round 6 PR EV7: the offers panel; no offer waits unless a test says so
  if (/\/demo\/offers$/.test(url)) return new Response("[]");
  const match = url.match(/\/demo\/shifts\?ward_id=(\d+)&date=([\d-]+)/);
  return match ? new Response(JSON.stringify(SHIFTS[`${match[1]}/${match[2]}`] ?? [])) : null;
}

function answerClock(fetchMock: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const picked = pickerAnswer(url);
    if (picked) return Promise.resolve(picked);
    return /\/clock$/.test(url)
      ? Promise.resolve(new Response(JSON.stringify(CLOCK_ANSWER)))
      : /\/demo\/test-runs$/.test(url) && (init?.method ?? "GET") === "GET"
        ? Promise.resolve(new Response("[]"))
        : (fetchMock(url, init) as Promise<Response>);
  });
}

function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockImplementation(async (url: string) => {
    const match = url.match(/\/cases\/(\d+)$/);
    return match
      ? new Response(JSON.stringify({ id: Number(match[1]), status: "WAITING_RESPONSE" }))
      : new Response(JSON.stringify(body), { status });
  });
  answerClock(fetchMock);
  return fetchMock;
}

// A link to a case is named by its ID; the test-run panel's link to its results is not
const CASE_LINK = /^\d/;

function click(name: string) {
  fireEvent.click(screen.getByRole("button", { name }));
}

/** Reset, Freeze and Unfreeze wait for the first list of test runs (review of #144). */
async function clickWhenReady(name: string) {
  const button = screen.getByRole<HTMLButtonElement>("button", { name });
  await vi.waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.click(button);
}

// Read the action's own text separately from nested live-status controls.
function directText(element: Element) {
  return Array.from(element.childNodes)
    .filter((node) => node.nodeType === Node.TEXT_NODE)
    .map((node) => node.textContent)
    .join("");
}

describe("demo control page", () => {
  it("reports the leave of 105 as that staff member and links to the opened case", async () => {
    const fetchMock = stubFetch(
      { event_id: 3, event_status: "PROCESSED", case_id: 7, case_status: "WAITING_RESPONSE" },
      201,
    );
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");

    const link = await screen.findByRole("link", { name: "7 (WAITING_RESPONSE)" });
    expect(link.getAttribute("href")).toBe("/cases/7");
    expect(screen.getByText("3 (PROCESSED)")).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    // The Demo control's own route, with the character in the body and no identity header
    expect(url).toMatch(/\/demo\/events$/);
    expect(request.method).toBe("POST");
    expect(request.headers.has("X-Demo-User")).toBe(false);
    expect(JSON.parse(request.body)).toEqual({
      event_type: "STAFF_UNAVAILABLE",
      shift_id: 1,
      reporter_staff_id: 105,
    });
  });

  it("shows that the leave of 203 on shift 2 opened no case", async () => {
    const fetchMock = stubFetch(
      { event_id: 4, event_status: "IGNORED", case_id: null, case_status: null, ignored_reason: "NO_GAP" },
      201,
    );
    render(createElement(DemoControl));
    click("203 reports leave (shift 2, no gap)");

    expect(
      await screen.findByText("Recorded. The shift still has enough people, so no case is needed."),
    ).toBeTruthy();
    expect(screen.getByText("4 (IGNORED)")).toBeTruthy();
    expect(screen.queryByRole("link", { name: CASE_LINK })).toBeNull();
    const request = fetchMock.mock.calls[0][1];
    expect(request.headers.has("X-Demo-User")).toBe(false);
    expect(JSON.parse(request.body)).toEqual({
      event_type: "STAFF_UNAVAILABLE",
      shift_id: 2,
      reporter_staff_id: 203,
    });
  });

  it("says that a leave joined the case already running on its shift (round 6 PR EV10)", async () => {
    stubFetch(
      { event_id: 6, event_status: "PROCESSED", case_id: 1, case_status: "WAITING_RESPONSE", joined_running_case: true },
      201,
    );
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");

    expect(
      await screen.findByText(/Added to case 1, which was already looking for people for this shift/),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: CASE_LINK })).toBeTruthy();
  });

  it("says that an event is waiting when its merge window is still open", async () => {
    stubFetch(
      { event_id: 5, event_status: "RECEIVED", case_id: null, case_status: null, window_closes_at: "2026-10-09T21:10:00+07:00" },
      201,
    );
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");

    expect(
      await screen.findByText(
        "Received. It is applied when the shift's merge window closes, at 2026-10-09 21:10:00 at the earliest.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("5 (RECEIVED)")).toBeTruthy();
    expect(screen.queryByRole("link", { name: CASE_LINK })).toBeNull();
  });

  it.each([
    [
      "900 cancels the assignment of 104 (shift 1)",
      {
        event_type: "ASSIGNMENT_CANCELLED",
        shift_id: 1,
        staff_id: 104,
        reason: "Cancelled from demo control",
      },
    ],
    [
      "900 reports 12 patients (shift 1)",
      { event_type: "PATIENT_SURGE", shift_id: 1, patient_count: 12 },
    ],
    [
      "900 requires 3 ICU nurses (shift 1)",
      {
        event_type: "REQUIREMENT_CHANGED",
        shift_id: 1,
        skills: [{ skill_id: 1, required_count: 3 }],
      },
    ],
  ])("sends '%s' as the head nurse", async (label, body) => {
    const fetchMock = stubFetch(
      { event_id: 6, event_status: "PROCESSED", case_id: 8, case_status: "WAITING_RESPONSE" },
      201,
    );
    render(createElement(DemoControl));
    click(label);

    const link = await screen.findByRole("link", { name: "8 (WAITING_RESPONSE)" });
    expect(link.getAttribute("href")).toBe("/cases/8");
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/demo\/events$/);
    expect(request.headers.has("X-Demo-User")).toBe(false);
    expect(JSON.parse(request.body)).toEqual({ ...body, reporter_staff_id: 900 });
  });

  it("advances the clock and links to the case of a closed merge window", async () => {
    const fetchMock = stubFetch({
      clock: "2026-10-09T21:10:00+07:00",
      closed_windows: [
        { shift_id: 1, event_ids: [3, 4], case_id: 7, case_status: "WAITING_RESPONSE" },
        { shift_id: 3, event_ids: [5], case_id: null, case_status: null },
      ],
      timed_out_approval_request_ids: [],
      timed_out_outreach_ids: [],
      recovered_case_ids: [],
    });
    render(createElement(DemoControl));
    click("Advance clock");

    expect(await screen.findByText("Clock: 2026-10-09T21:10:00+07:00")).toBeTruthy();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(directText(items[0])).toBe("Shift 1, events 3, 4: ");
    expect(items[1].textContent).toBe("Shift 3, events 5: no case opened");
    expect(within(items[1]).queryByRole("link")).toBeNull();
    const links = within(items[0]).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["7 (WAITING_RESPONSE)"]);
    const link = links[0];
    expect(link.getAttribute("href")).toBe("/cases/7");
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/demo\/clock\/advance$/);
    expect(request.method).toBe("POST");
    expect(request.headers.has("X-Demo-User")).toBe(false);
    expect(JSON.parse(request.body)).toEqual({ seconds: 600 });
  });

  it("says so when advancing the clock closed no merge window", async () => {
    stubFetch({
      clock: "2026-10-09T21:10:00+07:00",
      closed_windows: [],
      timed_out_approval_request_ids: [],
      timed_out_outreach_ids: [],
      recovered_case_ids: [],
    });
    render(createElement(DemoControl));
    click("Advance clock");

    expect(await screen.findByText("No merge window was due.")).toBeTruthy();
    expect(screen.queryByRole("listitem")).toBeNull();
    expect(screen.queryByText(/Offers timed out/)).toBeNull();
    expect(screen.queryByText(/Waiting cases rechecked/)).toBeNull();
  });

  it("shows the offers that timed out and the cases that were rechecked", async () => {
    stubFetch({
      clock: "2026-10-09T21:10:00+07:00",
      closed_windows: [],
      timed_out_approval_request_ids: [],
      timed_out_outreach_ids: [1, 2],
      recovered_case_ids: [7, 9],
    });
    render(createElement(DemoControl));
    click("Advance clock");

    expect(await screen.findByText("Offers timed out: 1, 2")).toBeTruthy();
    await screen.findByRole("link", { name: "9 (WAITING_RESPONSE)" });
    const recovered = screen.getByText(/Waiting cases rechecked/);
    expect(directText(recovered)).toBe("Waiting cases rechecked: ");
    expect(Array.from(recovered.children).map(directText)).toEqual(["", ", "]);
    const links = within(recovered).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "7 (WAITING_RESPONSE)",
      "9 (WAITING_RESPONSE)",
    ]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/cases/7", "/cases/9"]);
  });

  it("shows why the clock cannot be advanced before a reset", async () => {
    stubFetch(
      { detail: "The demo clock is not frozen. Call POST /demo/reset first" },
      409,
    );
    render(createElement(DemoControl));
    click("Advance clock");

    expect(
      await screen.findByText(
        "Advance clock 10 minutes: The demo clock is not frozen. Call POST /demo/reset first (HTTP 409)",
      ),
    ).toBeTruthy();
  });

  it("shows approvals that timed out after advancing the clock", async () => {
    stubFetch({
      clock: "2026-10-09T21:15:00+07:00",
      closed_windows: [],
      timed_out_outreach_ids: [],
      timed_out_approval_request_ids: [4, 8],
      recovered_case_ids: [],
    });
    render(createElement(DemoControl));
    click("Advance clock");
    expect(await screen.findByText("Approvals timed out: 4, 8")).toBeTruthy();
  });

  it("resets the demo without a demo user and shows the new clock", async () => {
    const fetchMock = stubFetch({ status: "ok", clock: "2026-10-09T21:00:00+07:00" });
    render(createElement(DemoControl));
    await clickWhenReady("Reset demo");

    expect(await screen.findByText("Demo reset. Clock: 2026-10-09T21:00:00+07:00")).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/demo\/reset$/);
    expect(request.method).toBe("POST");
    expect(request.headers.has("X-Demo-User")).toBe(false);
  });

  it("shows the reason of a rejected request and frees the buttons again", async () => {
    stubFetch({ detail: "Staff 105 has no assigned roster on shift 1" }, 409);
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");

    expect(
      await screen.findByText(
        "105 reports leave (shift 1): Staff 105 has no assigned roster on shift 1 (HTTP 409)",
      ),
    ).toBeTruthy();
    // the clock buttons follow the state of the clock, the others only the running request.
    // Starting a test run waits for a tester code (round 6 PR EV5b), a leave or a check-in
    // for a person picked on a shift of the clock's day (round 6 PR EV6)
    for (const button of screen.getAllByRole<HTMLButtonElement>("button")) {
      const name = button.textContent ?? "";
      if (/^(Freeze|Unfreeze) clock|^Run on from|^Set and |^Start test run|^Report leave|^Simulate check-in|^Report patient surge/.test(name)) continue;
      expect(button.disabled).toBe(false);
    }
  });

  it("says so when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(createElement(DemoControl));
    await clickWhenReady("Reset demo");

    expect(
      await screen.findByText(
        "Reset demo: Cannot reach the API. Check that the backend is running.",
      ),
    ).toBeTruthy();
  });

  it("disables every button while a request is running", async () => {
    let respond!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        /\/demo\/test-runs$/.test(url)
          ? Promise.resolve(new Response("[]"))
          : new Promise<Response>((resolve) => { respond = resolve; }),
      ),
    );
    render(createElement(DemoControl));
    await clickWhenReady("Reset demo");

    expect(await screen.findByText("Working…")).toBeTruthy();
    for (const button of screen.getAllByRole<HTMLButtonElement>("button")) {
      expect(button.disabled).toBe(true);
    }
    respond(new Response(JSON.stringify({ status: "ok", clock: "now" })));
    expect(await screen.findByText("Demo reset. Clock: now")).toBeTruthy();
  });
});

describe("demo control events in session mode", () => {
  afterEach(() => setSessionMode(false));

  it("plays a character through /demo/events with the login cookie and no identity header", async () => {
    setSessionMode(true);
    const fetchMock = stubFetch(
      { event_id: 9, event_status: "PROCESSED", case_id: 11, case_status: "WAITING_RESPONSE" },
      201,
    );
    render(createElement(DemoControl));
    click("900 reports 12 patients (shift 1)");

    await screen.findByRole("link", { name: "11 (WAITING_RESPONSE)" });
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/demo\/events$/);
    // The session is the identity; the character is only in the body
    expect(request.credentials).toBe("include");
    expect(request.headers.has("X-Demo-User")).toBe(false);
    expect(JSON.parse(request.body)).toMatchObject({ reporter_staff_id: 900, event_type: "PATIENT_SURGE" });
  });

  it("shows the refusal of a login that is not a manager as a sentence, not a code", async () => {
    setSessionMode(true);
    stubFetch({ detail: "AUTH_FORBIDDEN" }, 403);
    render(createElement(DemoControl));
    click("900 reports 12 patients (shift 1)");

    const message = await screen.findByText(/You do not have the right to do this\./);
    expect(message.textContent).not.toContain("AUTH_FORBIDDEN");
  });
});

describe("demo control live case status", () => {
  const event = {
    event_id: 3,
    event_status: "PROCESSED",
    case_id: 7,
    case_status: "WAITING_RESPONSE",
  };
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status });
  const tick = async (ms = 0) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  function serve() {
    vi.useFakeTimers();
    let reply = () =>
      Promise.resolve(json({ id: 7, status: "WAITING_RESPONSE" }));
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (options?.method === "POST") {
        if (url.endsWith("/demo/reset"))
          return Promise.resolve(json({ clock: "now" }));
        return Promise.resolve(json(event));
      }
      return reply();
    });
    answerClock(fetchMock);
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");
    return {
      fetchMock,
      setReply: (next: typeof reply) => {
        reply = next;
      },
    };
  }

  it("follows acceptance and approval without replaying the event, then stops on completion", async () => {
    const { fetchMock, setReply } = serve();
    await tick();
    expect(
      screen.getByRole("link", { name: "7 (WAITING_RESPONSE)" }),
    ).toBeTruthy();
    setReply(() =>
      Promise.resolve(json({ id: 7, status: "WAITING_APPROVAL" })),
    );
    await tick(2000);
    expect(
      screen.getByRole("link", { name: "7 (WAITING_APPROVAL)" }),
    ).toBeTruthy();
    expect(screen.getByText("WAITING_RESPONSE")).toBeTruthy();
    setReply(() => Promise.resolve(json({ id: 7, status: "RESOLVED" })));
    await tick(2000);
    expect(screen.getByRole("link", { name: "7 (RESOLVED)" })).toBeTruthy();
    const count = fetchMock.mock.calls.length;
    await tick(10000);
    expect(fetchMock).toHaveBeenCalledTimes(count);
    expect(
      fetchMock.mock.calls.filter(([, options]) => options?.method === "POST"),
    ).toHaveLength(1);
  });

  it("keeps reading MANUAL_HANDOFF because it can still be resolved manually", async () => {
    const { setReply } = serve();
    await tick();
    setReply(() => Promise.resolve(json({ id: 7, status: "MANUAL_HANDOFF" })));
    await tick(2000);
    expect(
      screen.getByRole("link", { name: "7 (MANUAL_HANDOFF)" }),
    ).toBeTruthy();
    setReply(() => Promise.resolve(json({ id: 7, status: "RESOLVED" })));
    await tick(2000);
    expect(screen.getByRole("link", { name: "7 (RESOLVED)" })).toBeTruthy();
  });

  it("keeps the last status with an error and recovers on a manual refresh", async () => {
    const { setReply } = serve();
    await tick();
    setReply(() => Promise.resolve(json({ detail: "Unavailable" }, 503)));
    await tick(2000);
    expect(
      screen.getByRole("link", { name: "7 (WAITING_RESPONSE)" }),
    ).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain(
      "Status may be outdated",
    );
    setReply(() =>
      Promise.resolve(json({ id: 7, status: "WAITING_APPROVAL" })),
    );
    click("Refresh case 7");
    await tick();
    expect(
      screen.getByRole("link", { name: "7 (WAITING_APPROVAL)" }),
    ).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("drops stale status and stops polling when an external reset removes the case", async () => {
    const { fetchMock, setReply } = serve();
    await tick();
    setReply(() => Promise.resolve(json({ detail: "Not found" }, 404)));
    await tick(2000);
    expect(screen.getByRole("link", { name: "7" })).toBeTruthy();
    expect(screen.getByText(/Case no longer exists/)).toBeTruthy();
    const count = fetchMock.mock.calls.length;
    await tick(6000);
    expect(fetchMock).toHaveBeenCalledTimes(count);
  });

  it("never refreshes a missing case even when a new case reuses its ID", async () => {
    const { fetchMock, setReply } = serve();
    await tick();
    setReply(() => Promise.resolve(json({ detail: "Not found" }, 404)));
    await tick(2000);
    expect(screen.queryByRole("button", { name: "Refresh case 7" })).toBeNull();

    // Reset reuses IDs. A later 200 belongs to a different case and must not
    // replace the missing-case notice under the original event result.
    setReply(() => Promise.resolve(json({ id: 7, status: "WAITING_APPROVAL" })));
    const count = fetchMock.mock.calls.length;
    await tick(10000);
    expect(fetchMock).toHaveBeenCalledTimes(count);
    expect(screen.getByText(/Case no longer exists/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "7" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "7 (WAITING_APPROVAL)" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Refresh case 7" })).toBeNull();
  });

  it("ignores a response still in flight when the demo is reset", async () => {
    const { fetchMock, setReply } = serve();
    await tick();
    let finish!: (response: Response) => void;
    setReply(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    await tick(2000);
    const pendingOptions = fetchMock.mock.calls.at(-1)?.[1];
    click("Reset demo");
    await tick();
    expect(pendingOptions?.signal?.aborted).toBe(true);
    finish(json({ id: 7, status: "WAITING_APPROVAL" }));
    await tick();
    expect(screen.getByText("Demo reset. Clock: now")).toBeTruthy();
    expect(screen.queryByRole("link", { name: CASE_LINK })).toBeNull();
  });

  it("updates both merge-window and recovery links after a clock action", async () => {
    vi.useFakeTimers();
    let status = "WAITING_APPROVAL";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options?: RequestInit) => {
        if (options?.method === "POST")
          return json({
            clock: "now",
            closed_windows: [
              {
                shift_id: 1,
                event_ids: [3],
                case_id: 7,
                case_status: "WAITING_RESPONSE",
              },
            ],
            timed_out_approval_request_ids: [],
            timed_out_outreach_ids: [],
            recovered_case_ids: [9],
          });
        return json({ id: Number(url.split("/").at(-1)), status });
      }),
    );
    render(createElement(DemoControl));
    click("Advance clock");
    await tick();
    expect(
      screen.getByRole("link", { name: "7 (WAITING_APPROVAL)" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "9 (WAITING_APPROVAL)" }),
    ).toBeTruthy();
    status = "RESOLVED";
    await tick(2000);
    expect(screen.getByRole("link", { name: "7 (RESOLVED)" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "9 (RESOLVED)" })).toBeTruthy();
  });

  it("ignores an old case response when another event replaces the displayed case", async () => {
    const { fetchMock, setReply } = serve();
    await tick();
    let finish!: (response: Response) => void;
    setReply(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    await tick(2000);
    const oldSignal = fetchMock.mock.calls.at(-1)?.[1]?.signal;
    fetchMock.mockImplementation((url: string, options?: RequestInit) =>
      Promise.resolve(
        json(
          options?.method === "POST"
            ? { ...event, case_id: 8 }
            : { id: Number(url.split("/").at(-1)), status: "WAITING_RESPONSE" },
        ),
      ),
    );
    click("900 reports 12 patients (shift 1)");
    await tick();
    expect(oldSignal?.aborted).toBe(true);
    finish(json({ id: 7, status: "RESOLVED" }));
    await tick();
    expect(
      screen.getByRole("link", { name: "8 (WAITING_RESPONSE)" }),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: /7/ })).toBeNull();
  });

  it("cancels polling when the page unmounts", async () => {
    const { fetchMock } = serve();
    await tick();
    cleanup();
    const count = fetchMock.mock.calls.length;
    await tick(10000);
    expect(fetchMock).toHaveBeenCalledTimes(count);
  });

  /** The Demo control inside the clock the picker reads its day from */
  function renderWithClock() {
    render(createElement(ClockProvider, { children: createElement(DemoControl) }));
  }

  async function optionsOf(label: string, expected: string[]) {
    await vi.waitFor(() =>
      expect(
        Array.from(screen.getByLabelText<HTMLSelectElement>(label).options).map((item) => item.value),
      ).toEqual(expected),
    );
  }

  it("reports a leave on the chosen ward, day, shift and person (PR U, round 6 PR EV6)", async () => {
    const fetchMock = stubFetch(
      { event_id: 5, event_status: "PROCESSED", case_id: 8, case_status: "WAITING_RESPONSE" },
    );
    renderWithClock();
    await optionsOf("Ward", ["1", "2"]);
    fireEvent.change(screen.getByLabelText("Ward"), { target: { value: "2" } });
    await vi.waitFor(() =>
      expect(screen.getByLabelText<HTMLInputElement>("Day the shift starts").value).toBe("2026-10-09"),
    );
    fireEvent.change(screen.getByLabelText("Day the shift starts"), { target: { value: "2026-10-11" } });
    await optionsOf("Shift", ["22"]);
    fireEvent.change(screen.getByLabelText("Staff on the shift"), { target: { value: "401" } });
    click("Report leave");

    expect(await screen.findByText("401 reports leave (Medicine, shift 22)")).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/demo\/events$/);
    expect(request.headers.has("X-Demo-User")).toBe(false);
    expect(JSON.parse(request.body)).toEqual({
      event_type: "STAFF_UNAVAILABLE",
      shift_id: 22,
      reporter_staff_id: 401,
    });
  });

  it("offers the wards of the database and the shifts and people of the chosen day (round 6 PR EV6)", async () => {
    stubFetch({});
    renderWithClock();
    // A Float Pool has no shifts of its own
    await optionsOf("Ward", ["1", "2"]);
    fireEvent.change(screen.getByLabelText("Ward"), { target: { value: "2" } });

    await optionsOf("Shift", ["21"]);
    await optionsOf("Staff on the shift", ["301", "302", "401", "902", "950"]);
    expect(screen.getByRole("option", { name: /^301 — Name301 Demo · ASSIGNED$/ })).toBeTruthy();
  });

  it("simulates the check-in of the chosen staff member through the demo route", async () => {
    const fetchMock = stubFetch({
      attendance_id: 4,
      shift_id: 1,
      check_in_at: "2026-10-09T22:50:00+07:00",
      on_time: true,
      deadline: "2026-10-09T23:15:00+07:00",
    });
    renderWithClock();
    await optionsOf("Staff on the shift", ["101", "102", "103", "104", "105"]);
    click("Simulate check-in (demo)");

    expect(
      await screen.findByText(/Simulated check-in of 101 \(ICU, shift 1\): on time/),
    ).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/demo\/attendance\/check-in$/);
    expect(request.method).toBe("POST");
    expect(JSON.parse(request.body)).toEqual({ staff_id: 101, shift_id: 1 });
  });

  it("lists the no-show events the clock advance recorded", async () => {
    stubFetch({
      clock: "2026-10-09T23:20:00+07:00",
      closed_windows: [],
      timed_out_approval_request_ids: [],
      timed_out_outreach_ids: [],
      auto_approved_request_ids: [],
      failed_auto_approval_ward_ids: [],
      recovered_case_ids: [],
      no_show_event_ids: [11, 12],
    });
    render(createElement(DemoControl));
    click("Advance clock");
    expect(await screen.findByText("No-show events recorded: 11, 12")).toBeTruthy();
  });
});

describe("demo control clock buttons", () => {
  function serveClock(frozen: boolean) {
    let isFrozen = frozen;
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      if (init?.method === "POST") {
        calls.push(path);
        isFrozen = path.endsWith("/freeze");
      }
      if (path === "/demo/test-runs") return new Response("[]");
      return new Response(JSON.stringify({ now: "2026-10-09T21:00:00+07:00", frozen: isFrozen }));
    });
    return calls;
  }

  it("unfreezes a frozen clock, and the freeze button waits for it", async () => {
    const calls = serveClock(true);
    render(createElement(ClockProvider, null, createElement(DemoControl)));

    const freeze = await screen.findByRole("button", { name: "Freeze clock" });
    const unfreeze = screen.getByRole("button", { name: "Unfreeze clock (real time)" });
    await vi.waitFor(() => expect((freeze as HTMLButtonElement).disabled).toBe(true));
    expect((unfreeze as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(unfreeze);
    expect(await screen.findByText(/Clock follows real time again/)).toBeTruthy();
    expect(calls).toEqual(["/demo/clock/unfreeze"]);
  });

  it("freezes a clock that follows real time", async () => {
    const calls = serveClock(false);
    render(createElement(ClockProvider, null, createElement(DemoControl)));

    const freeze = screen.getByRole("button", { name: "Freeze clock" });
    await vi.waitFor(() =>
      expect((screen.getByRole("button", { name: "Unfreeze clock (real time)" }) as HTMLButtonElement).disabled).toBe(true),
    );
    await vi.waitFor(() => expect((freeze as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(freeze);
    expect(await screen.findByText(/Clock frozen at/)).toBeTruthy();
    expect(calls).toEqual(["/demo/clock/freeze"]);
  });
});

describe("demo control clock reads", () => {
  it("makes one read of /clock a second for the top bar and the buttons together", async () => {
    vi.useFakeTimers();
    let reads = 0;
    vi.stubGlobal("fetch", async (url: string) => {
      if (/\/clock$/.test(url)) reads += 1;
      return new Response(JSON.stringify({ now: "2026-10-09T21:00:00+07:00", frozen: true }));
    });
    render(
      createElement(
        ClockProvider,
        null,
        createElement(DemoClock),
        createElement(DemoControl),
      ),
    );
    await act(async () => { await vi.advanceTimersByTimeAsync(3500); });
    // one at the start, then one at 1, 2 and 3 seconds
    expect(reads).toBe(4);
  });

  it("disables Advance clock while the clock follows real time", async () => {
    vi.stubGlobal("fetch", async () =>
      new Response(JSON.stringify({ now: "2026-10-09T21:00:00+07:00", frozen: false })),
    );
    render(createElement(ClockProvider, null, createElement(DemoControl)));
    const advance = screen.getByRole("button", { name: "Advance clock" }) as HTMLButtonElement;
    await vi.waitFor(() => expect(advance.disabled).toBe(true));
  });

  it("gives the words of an error in the language of the page", async () => {
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) =>
      /\/clock$/.test(url)
        ? new Response(JSON.stringify({ now: "2026-10-09T21:00:00+07:00", frozen: true }))
        : (/\/demo\/test-runs$/.test(url) && (init?.method ?? "GET") === "GET") || /\/demo\/offers$/.test(url)
          ? new Response("[]")
          : new Response("{}", { status: 500 }),
    );
    const view = render(
      createElement(LanguageProvider, { initial: "th", children: createElement(DemoControl) }),
    );
    await clickWhenReady("รีเซ็ต Demo");
    expect(await screen.findByText(/คำขอไปยัง API ไม่สำเร็จ \(500\)/)).toBeTruthy();
    view.unmount();
    // the same failure shown in English: the sentence is ours, so it follows the language
    render(createElement(LanguageProvider, { initial: "en", children: createElement(DemoControl) }));
    await clickWhenReady("Reset demo");
    expect(await screen.findByText(/API request failed \(500\)/)).toBeTruthy();
  });
});

describe("demo control language switch", () => {
  it("changes an error that stays on the screen from Thai to English without a remount", async () => {
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) =>
      /\/clock$/.test(url)
        ? new Response(JSON.stringify({ now: "2026-10-09T21:00:00+07:00", frozen: true }))
        : (/\/demo\/test-runs$/.test(url) && (init?.method ?? "GET") === "GET") || /\/demo\/offers$/.test(url)
          ? new Response("[]")
          : new Response("{}", { status: 500 }),
    );
    render(
      createElement(LanguageProvider, {
        initial: "th",
        children: [createElement(LanguageSwitch, { key: "switch" }), createElement(DemoControl, { key: "page" })],
      }),
    );
    await clickWhenReady("รีเซ็ต Demo");
    expect(await screen.findByText(/คำขอไปยัง API ไม่สำเร็จ \(500\)/)).toBeTruthy();

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "EN" })); });

    expect(screen.getByText(/Reset demo: API request failed \(500\)/)).toBeTruthy();
    expect(screen.queryByText(/คำขอไปยัง API ไม่สำเร็จ/)).toBeNull();
  });
});

describe("demo control clock of round 6 PR EV6", () => {
  /** The Backend clock; a POST answers with `answer` and is kept with its body */
  function serve(answer: Record<string, unknown>) {
    const posts: { path: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      const picked = pickerAnswer(url);
      if (picked) return picked;
      const path = new URL(url).pathname;
      if (path === "/demo/test-runs") return new Response("[]");
      if (init?.method === "POST") {
        posts.push({ path, body: init.body ? JSON.parse(String(init.body)) : undefined });
        return new Response(JSON.stringify(answer));
      }
      return new Response(JSON.stringify({ now: "2026-10-09T21:00:00+07:00", frozen: true, mode: "frozen" }));
    });
    render(createElement(ClockProvider, null, createElement(DemoControl)));
    return posts;
  }

  it("sets the clock to the time picked and lets it run on from there", async () => {
    const posts = serve({ now: "2026-10-12T08:30:00+07:00", frozen: false, mode: "running" });
    const time = screen.getByLabelText<HTMLInputElement>("Time");
    // It starts at the time the clock shows, in Bangkok time
    await vi.waitFor(() => expect(time.value).toBe("2026-10-09T21:00"));

    fireEvent.change(time, { target: { value: "2026-10-12T08:30" } });
    await clickWhenReady("Set and run on");

    expect(await screen.findByText("Clock runs on at real speed. Now: 2026-10-12 08:30:00")).toBeTruthy();
    expect(posts).toEqual([
      { path: "/demo/clock/set", body: { at: "2026-10-12T08:30:00+07:00", running: true } },
    ]);
  });

  it("sets the clock and keeps it frozen there", async () => {
    const posts = serve({ now: "2026-10-10T06:45:00+07:00", frozen: true, mode: "frozen" });
    const time = screen.getByLabelText<HTMLInputElement>("Time");
    await vi.waitFor(() => expect(time.value).toBe("2026-10-09T21:00"));

    fireEvent.change(time, { target: { value: "2026-10-10T06:45" } });
    await clickWhenReady("Set and freeze");

    expect(await screen.findByText("Clock frozen at 2026-10-10 06:45:00")).toBeTruthy();
    expect(posts[0].body).toEqual({ at: "2026-10-10T06:45:00+07:00", running: false });
  });

  it("runs on from the time shown instead of going back to real time", async () => {
    const posts = serve({ now: "2026-10-09T21:00:00+07:00", frozen: false, mode: "running" });

    await clickWhenReady("Run on from the time shown");

    expect(await screen.findByText("Clock runs on at real speed. Now: 2026-10-09 21:00:00")).toBeTruthy();
    expect(posts.map((post) => post.path)).toEqual(["/demo/clock/resume"]);
  });

  it("resets with the hospital demo unless it is unticked", async () => {
    const posts = serve({ status: "ok", clock: "2026-10-09T21:00:00+07:00" });

    await clickWhenReady("Reset demo");
    await screen.findByText(/Demo reset/);
    fireEvent.click(screen.getByLabelText("Load the hospital demo (5 more wards for a week)"));
    await clickWhenReady("Reset demo");

    await vi.waitFor(() => expect(posts).toHaveLength(2));
    expect(posts.map((post) => post.body)).toEqual([{ hospital: true }, { hospital: false }]);
  });
});

describe("demo control picker after a reset (review of #145)", () => {
  it("reads the wards again, so the hospital wards appear without a page reload", async () => {
    let hospital = false;
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      if (path === "/demo/wards") {
        const surgery = { id: 20001, name: "Surgery", is_active: true, is_float_pool: false };
        return new Response(JSON.stringify(hospital ? [...WARDS, surgery] : WARDS));
      }
      const picked = pickerAnswer(url);
      if (picked) return picked;
      if (path === "/demo/test-runs") return new Response("[]");
      if (init?.method === "POST" && path === "/demo/reset") {
        hospital = true;
        return new Response(JSON.stringify({ status: "ok", clock: "2026-10-09T21:00:00+07:00" }));
      }
      return new Response(JSON.stringify(CLOCK_ANSWER));
    });
    render(createElement(ClockProvider, null, createElement(DemoControl)));
    const wards = () =>
      Array.from(screen.getByLabelText<HTMLSelectElement>("Ward").options).map((item) => item.textContent);
    await vi.waitFor(() => expect(wards()).toEqual(["ICU", "Medicine"]));

    await clickWhenReady("Reset demo");

    await vi.waitFor(() => expect(wards()).toEqual(["ICU", "Medicine", "Surgery"]));
  });
});

describe("demo control of round 6 PR EV7", () => {
  const ADVANCED = {
    clock: "2026-10-09T21:30:00+07:00",
    closed_windows: [],
    timed_out_approval_request_ids: [],
    timed_out_outreach_ids: [],
    auto_approved_request_ids: [],
    failed_auto_approval_ward_ids: [],
    recovered_case_ids: [],
    no_show_event_ids: [],
  };

  it("advances the clock by a chosen step, or by minutes typed in", async () => {
    const fetchMock = stubFetch(ADVANCED);
    render(createElement(DemoControl));

    fireEvent.change(screen.getByLabelText("Advance by"), { target: { value: "30" } });
    click("Advance clock");
    await screen.findByText(/Clock: 2026-10-09T21:30/);
    fireEvent.change(screen.getByLabelText("Advance by"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("Minutes"), { target: { value: "7" } });
    click("Advance clock");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(String(init.body)));
    expect(bodies).toEqual([{ seconds: 1800 }, { seconds: 420 }]);
    // Nothing that is not a whole number of minutes is sent
    fireEvent.change(screen.getByLabelText("Minutes"), { target: { value: "0" } });
    expect((screen.getByRole("button", { name: "Advance clock" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("reports a patient surge on the picked shift as its ward's head nurse", async () => {
    const fetchMock = stubFetch({ event_id: 9, event_status: "PROCESSED", case_id: 4, case_status: "WAITING_RESPONSE" });
    render(createElement(ClockProvider, { children: createElement(DemoControl) }));
    await vi.waitFor(() =>
      expect(Array.from(screen.getByLabelText<HTMLSelectElement>("Shift").options).map((item) => item.value)).toEqual(["1"]),
    );

    fireEvent.change(screen.getByLabelText("Patients on the shift"), { target: { value: "14" } });
    click("Report patient surge");

    expect(await screen.findByText("Patient surge to 14 (ICU, shift 1)")).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/demo\/events$/);
    expect(JSON.parse(request.body)).toEqual({
      event_type: "PATIENT_SURGE",
      shift_id: 1,
      patient_count: 14,
      reporter_staff_id: 900,
    });
  });

  it("accepts an offer in the candidate's place", async () => {
    const offer = {
      id: 31,
      case_id: 7,
      staff_id: 201,
      first_name: "Arunee",
      last_name: "Demo",
      ward_name: "ICU",
      shift_start_at: "2026-10-09T23:00:00+07:00",
      can_accept: true,
      can_reject: true,
    };
    let open = [offer];
    const posts: { url: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      if (/\/demo\/offers$/.test(url)) return new Response(JSON.stringify(open));
      if (init?.method === "POST" && /\/demo\/offers\/31\/response$/.test(url)) {
        posts.push({ url, body: JSON.parse(String(init.body)) });
        open = [];
        return new Response(
          JSON.stringify({ outreach_id: 31, outreach_status: "ACCEPTED", case_id: 7, case_status: "WAITING_APPROVAL" }),
        );
      }
      const picked = pickerAnswer(url);
      if (picked) return picked;
      if (/\/demo\/test-runs$/.test(url)) return new Response("[]");
      return new Response(JSON.stringify(CLOCK_ANSWER));
    });
    render(createElement(DemoControl));

    fireEvent.click(await screen.findByRole("button", { name: "Accept for 201 (case 7)" }));

    expect(await screen.findByText("201 accepted for case 7. Case: WAITING_APPROVAL")).toBeTruthy();
    expect(posts).toEqual([{ url: expect.stringMatching(/\/demo\/offers\/31\/response$/), body: { response: "ACCEPT" } }]);
    await vi.waitFor(() => expect(screen.getByText("No offer is waiting.")).toBeTruthy());
  });
});
