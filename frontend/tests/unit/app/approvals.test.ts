// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Approvals from "../../../src/app/approvals/page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PENDING = {
  id: 4,
  case_id: 7,
  candidate_item_id: 11,
  required_approver_role: 2,
  approval_mode: "MANUAL",
  is_pending: true,
  staff_id: 201,
  proposed_shift_id: 1,
  requested_at: "2026-10-09T21:00:00+07:00",
};

/** GET answers the list; POST answers `decision`. */
function stubFetch(list: unknown[], decision: { body: unknown; status?: number } | null = null) {
  const fetchMock = vi.fn().mockImplementation(async (_url: string, request: RequestInit) =>
    request.method === "POST" && decision
      ? new Response(JSON.stringify(decision.body), { status: decision.status ?? 200 })
      : new Response(JSON.stringify(list)),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function posts(fetchMock: ReturnType<typeof stubFetch>) {
  return fetchMock.mock.calls.filter(([, request]) => request.method === "POST");
}

describe("approvals page", () => {
  it("lists the pending requests read as the head nurse", async () => {
    const fetchMock = stubFetch([PENDING]);
    render(createElement(Approvals));

    const link = await screen.findByRole("link", { name: "7" });
    expect(link.getAttribute("href")).toBe("/cases/7");
    expect(screen.getByText("201")).toBeTruthy();
    expect(screen.getByText("09/10/2026, 21:00:00")).toBeTruthy();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/approvals\?pending=true$/);
    expect(request.headers.get("X-Demo-User")).toBe("900");
  });

  it("says so when nothing is pending", async () => {
    stubFetch([]);
    render(createElement(Approvals));

    expect(await screen.findByText("No pending approvals.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("approves as 900, shows the case result and drops the row", async () => {
    const fetchMock = stubFetch([PENDING], {
      body: { approval_id: 4, is_approved: true, case_id: 7, case_status: "RESOLVED" },
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Approval 4 approved. Case 7: RESOLVED")).toBeTruthy();
    // The stubbed list still holds the row: it is hidden before the next poll
    expect(screen.queryByRole("table")).toBeNull();
    const [[url, request]] = posts(fetchMock);
    expect(url).toMatch(/\/approvals\/4\/decision$/);
    expect(request.headers.get("X-Demo-User")).toBe("900");
    expect(JSON.parse(request.body)).toEqual({ approved: true });
  });

  it("sends a rejection and keeps the row when the API refuses it", async () => {
    const fetchMock = stubFetch([PENDING], {
      body: { detail: "Rejection is not supported yet" },
      status: 422,
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));

    expect(
      await screen.findByText("Approval 4: Rejection is not supported yet (HTTP 422)"),
    ).toBeTruthy();
    expect(JSON.parse(posts(fetchMock)[0][1].body)).toEqual({ approved: false });
    expect(screen.getByRole("table")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByRole<HTMLButtonElement>("button", { name: "Approve" }).disabled).toBe(
        false,
      ),
    );
  });

  it("shows a failed read", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Unknown demo user" }), { status: 401 }),
      ),
    );
    render(createElement(Approvals));

    expect(await screen.findByText("Unknown demo user")).toBeTruthy();
  });
});
