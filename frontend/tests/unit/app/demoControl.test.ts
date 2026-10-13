// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DemoControl from "../../../src/app/demo/control/page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi
    .fn()
    .mockImplementation(
      async () => new Response(JSON.stringify(body), { status }),
    );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function click(name: string) {
  fireEvent.click(screen.getByRole("button", { name }));
}

describe("demo control page", () => {
  it("reports the leave of 105 as that staff member and links to the opened case", async () => {
    const fetchMock = stubFetch(
      {
        event_id: 3,
        event_status: "PROCESSED",
        case_id: 7,
        case_status: "WAITING_RESPONSE",
      },
      201,
    );
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");

    const link = await screen.findByRole("link", {
      name: "7 (WAITING_RESPONSE)",
    });
    expect(link.getAttribute("href")).toBe("/cases/7");
    expect(screen.getByText("3 (PROCESSED)")).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/events$/);
    expect(request.method).toBe("POST");
    expect(request.headers.get("X-Demo-User")).toBe("105");
    expect(JSON.parse(request.body)).toEqual({
      event_type: "STAFF_UNAVAILABLE",
      shift_id: 1,
    });
  });

  it("shows that the leave of 203 on shift 2 opened no case", async () => {
    const fetchMock = stubFetch(
      {
        event_id: 4,
        event_status: "IGNORED",
        case_id: null,
        case_status: null,
      },
      201,
    );
    render(createElement(DemoControl));
    click("203 reports leave (shift 2, no gap)");

    expect(await screen.findByText("No case opened")).toBeTruthy();
    expect(screen.getByText("4 (IGNORED)")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
    const request = fetchMock.mock.calls[0][1];
    expect(request.headers.get("X-Demo-User")).toBe("203");
    expect(JSON.parse(request.body)).toEqual({
      event_type: "STAFF_UNAVAILABLE",
      shift_id: 2,
    });
  });

  it("says that an event is waiting when its merge window is still open", async () => {
    stubFetch(
      {
        event_id: 5,
        event_status: "RECEIVED",
        case_id: null,
        case_status: null,
      },
      201,
    );
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");

    expect(
      await screen.findByText("Not decided yet. The event is waiting."),
    ).toBeTruthy();
    expect(screen.getByText("5 (RECEIVED)")).toBeTruthy();
    expect(screen.queryByText("No case opened")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
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
      {
        event_id: 6,
        event_status: "PROCESSED",
        case_id: 8,
        case_status: "WAITING_RESPONSE",
      },
      201,
    );
    render(createElement(DemoControl));
    click(label);

    const link = await screen.findByRole("link", {
      name: "8 (WAITING_RESPONSE)",
    });
    expect(link.getAttribute("href")).toBe("/cases/8");
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/events$/);
    expect(request.headers.get("X-Demo-User")).toBe("900");
    expect(JSON.parse(request.body)).toEqual(body);
  });

  it("advances the clock and links to the case of a closed merge window", async () => {
    const fetchMock = stubFetch({
      clock: "2026-10-09T21:10:00+07:00",
      closed_windows: [
        {
          shift_id: 1,
          event_ids: [3, 4],
          case_id: 7,
          case_status: "WAITING_RESPONSE",
        },
        { shift_id: 3, event_ids: [5], case_id: null, case_status: null },
      ],
      timed_out_approval_request_ids: [],
      timed_out_outreach_ids: [],
      recovered_case_ids: [],
    });
    render(createElement(DemoControl));
    click("Advance clock 10 minutes");

    expect(
      await screen.findByText("Clock: 2026-10-09T21:10:00+07:00"),
    ).toBeTruthy();
    const items = screen
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(items).toEqual([
      "Shift 1, events 3, 4: 7 (WAITING_RESPONSE)",
      "Shift 3, events 5: no case opened",
    ]);
    const link = screen.getByRole("link", { name: "7 (WAITING_RESPONSE)" });
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
    click("Advance clock 10 minutes");

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
    click("Advance clock 10 minutes");

    expect(await screen.findByText("Offers timed out: 1, 2")).toBeTruthy();
    expect(screen.getByText(/Waiting cases rechecked/).textContent).toBe(
      "Waiting cases rechecked: 7, 9",
    );
    expect(screen.getByRole("link", { name: "9" }).getAttribute("href")).toBe(
      "/cases/9",
    );
  });

  it("shows why the clock cannot be advanced before a reset", async () => {
    stubFetch(
      { detail: "The demo clock is not frozen. Call POST /demo/reset first" },
      409,
    );
    render(createElement(DemoControl));
    click("Advance clock 10 minutes");

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
    click("Advance clock 10 minutes");
    expect(await screen.findByText("Approvals timed out: 4, 8")).toBeTruthy();
  });

  it("resets the demo without a demo user and shows the new clock", async () => {
    const fetchMock = stubFetch({
      status: "ok",
      clock: "2026-10-09T21:00:00+07:00",
    });
    render(createElement(DemoControl));
    click("Reset demo");

    expect(
      await screen.findByText("Demo reset. Clock: 2026-10-09T21:00:00+07:00"),
    ).toBeTruthy();
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
    for (const button of screen.getAllByRole<HTMLButtonElement>("button")) {
      expect(button.disabled).toBe(false);
    }
  });

  it("says so when the API cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    render(createElement(DemoControl));
    click("Reset demo");

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
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            respond = resolve;
          }),
      ),
    );
    render(createElement(DemoControl));
    click("Reset demo");

    expect(await screen.findByText("Working…")).toBeTruthy();
    for (const button of screen.getAllByRole<HTMLButtonElement>("button")) {
      expect(button.disabled).toBe(true);
    }
    respond(new Response(JSON.stringify({ status: "ok", clock: "now" })));
    expect(await screen.findByText("Demo reset. Clock: now")).toBeTruthy();
  });
});
