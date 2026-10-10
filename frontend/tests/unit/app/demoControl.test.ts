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
  const fetchMock = vi.fn().mockImplementation(async () =>
    new Response(JSON.stringify(body), { status }),
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
      { event_id: 3, event_status: "PROCESSED", case_id: 7, case_status: "WAITING_RESPONSE" },
      201,
    );
    render(createElement(DemoControl));
    click("105 reports leave (shift 1)");

    const link = await screen.findByRole("link", { name: "7 (WAITING_RESPONSE)" });
    expect(link.getAttribute("href")).toBe("/cases/7");
    expect(screen.getByText("3 (PROCESSED)")).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/events$/);
    expect(request.method).toBe("POST");
    expect(request.headers.get("X-Demo-User")).toBe("105");
    expect(JSON.parse(request.body)).toEqual({ event_type: "STAFF_UNAVAILABLE", shift_id: 1 });
  });

  it("shows that the leave of 203 on shift 2 opened no case", async () => {
    const fetchMock = stubFetch(
      { event_id: 4, event_status: "IGNORED", case_id: null, case_status: null },
      201,
    );
    render(createElement(DemoControl));
    click("203 reports leave (shift 2, no gap)");

    expect(await screen.findByText("No case opened")).toBeTruthy();
    expect(screen.getByText("4 (IGNORED)")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
    const request = fetchMock.mock.calls[0][1];
    expect(request.headers.get("X-Demo-User")).toBe("203");
    expect(JSON.parse(request.body)).toEqual({ event_type: "STAFF_UNAVAILABLE", shift_id: 2 });
  });

  it("resets the demo without a demo user and shows the new clock", async () => {
    const fetchMock = stubFetch({ status: "ok", clock: "2026-10-09T21:00:00+07:00" });
    render(createElement(DemoControl));
    click("Reset demo");

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
    for (const button of screen.getAllByRole<HTMLButtonElement>("button")) {
      expect(button.disabled).toBe(false);
    }
  });

  it("says so when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
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
      vi.fn(() => new Promise<Response>((resolve) => { respond = resolve; })),
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
