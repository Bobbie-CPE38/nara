// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Approvals from "../../../src/app/approvals/page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
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

/** The part of GET /cases/{id} the page reads: a gap of two with one person assigned. */
const CASE = { id: 7, gap: { headcount_gap: 2 }, assigned_count: 1 };

/** GET answers the list or the case; POST answers `decision`. */
function stubFetch(
  list: unknown[],
  decision: { body: unknown; status?: number } | null = null,
  caseAnswer: { body: unknown; status?: number } = { body: CASE },
) {
  const fetchMock = vi.fn().mockImplementation(async (url: string, request: RequestInit) => {
    if (request.method === "POST" && decision) {
      return new Response(JSON.stringify(decision.body), { status: decision.status ?? 200 });
    }
    if (/\/cases\/\d+$/.test(url)) {
      return new Response(JSON.stringify(caseAnswer.body), { status: caseAnswer.status ?? 200 });
    }
    return new Response(JSON.stringify(list));
  });
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
    expect(screen.getByText("2026-10-09 21:00:00")).toBeTruthy();
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

  it("shows how many people the case still needs", async () => {
    const fetchMock = stubFetch([PENDING, { ...PENDING, id: 5, staff_id: 202 }]);
    render(createElement(Approvals));

    expect(await screen.findAllByText("Short by 1")).toHaveLength(2);
    // Two requests of one case need one read of that case
    const caseReads = fetchMock.mock.calls.filter(([url]) => /\/cases\/7$/.test(url));
    expect(caseReads).toHaveLength(1);
  });

  it("says so when the people already assigned cover the headcount", async () => {
    stubFetch([PENDING], null, { body: { ...CASE, assigned_count: 2 } });
    render(createElement(Approvals));

    expect(await screen.findByText("Headcount covered")).toBeTruthy();
  });

  it("still lists the request when its case cannot be read", async () => {
    stubFetch([PENDING], null, { body: { detail: "No case 7" }, status: 404 });
    render(createElement(Approvals));

    expect(await screen.findByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("asks for a reason before it sends a rejection", async () => {
    const fetchMock = stubFetch([PENDING], {
      body: { approval_id: 4, is_approved: false, case_id: 7, case_status: "WAITING_RESPONSE" },
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));

    const input = screen.getByLabelText<HTMLTextAreaElement>(
      "Reason for rejecting approval 4 (staff 201, case 7)",
    );
    const confirm = screen.getByRole<HTMLButtonElement>("button", { name: "Confirm rejection" });
    expect(input.maxLength).toBe(500);
    expect(confirm.disabled).toBe(true);
    // Spaces alone are not a reason: the API answers 422
    fireEvent.change(input, { target: { value: "   " } });
    expect(confirm.disabled).toBe(true);
    expect(posts(fetchMock)).toHaveLength(0);

    fireEvent.change(input, { target: { value: "  Needs rest  " } });
    fireEvent.click(confirm);

    expect(await screen.findByText("Approval 4 rejected. Case 7: WAITING_RESPONSE")).toBeTruthy();
    const [[url, request]] = posts(fetchMock);
    expect(url).toMatch(/\/approvals\/4\/decision$/);
    expect(JSON.parse(request.body)).toEqual({ approved: false, reason: "Needs rest" });
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirm rejection" })).toBeNull();
  });

  it("drops the reason and sends nothing when the rejection is cancelled", async () => {
    const fetchMock = stubFetch([PENDING]);
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Needs rest" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("textbox")).toBeNull();
    expect(posts(fetchMock)).toHaveLength(0);
    // A new rejection starts with an empty reason
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("");
  });

  it("keeps the row and the reason when the API refuses the rejection", async () => {
    const fetchMock = stubFetch([PENDING], {
      body: { detail: "This case has stopped; the request cannot be decided" },
      status: 409,
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Needs rest" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));

    expect(
      await screen.findByText(
        "Approval 4: This case has stopped; the request cannot be decided (HTTP 409)",
      ),
    ).toBeTruthy();
    expect(posts(fetchMock)).toHaveLength(1);
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("Needs rest");
    expect(screen.getByRole("table")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByRole<HTMLButtonElement>("button", { name: "Approve" }).disabled).toBe(
        false,
      ),
    );
  });

  it("shows a new request that reuses a decided ID after a demo reset", async () => {
    vi.useFakeTimers();
    let list: unknown[] = [PENDING];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string, request: RequestInit) =>
        new Response(
          JSON.stringify(
            request.method === "POST"
              ? { approval_id: 4, is_approved: true, case_id: 7, case_status: "RESOLVED" }
              : /\/cases\/\d+$/.test(url)
                ? CASE
                : list,
          ),
        ),
      ),
    );
    const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    render(createElement(Approvals));
    await tick(0);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await tick(0);
    expect(screen.queryByRole("table")).toBeNull();

    // The next poll confirms the decided request is gone
    list = [];
    await tick(2000);
    expect(screen.getByText("No pending approvals.")).toBeTruthy();

    // The demo was reset, so the sequence restarted and the new request has ID 4 again
    list = [{ ...PENDING, case_id: 9 }];
    await tick(2000);
    expect(screen.getByRole("link", { name: "9" }).getAttribute("href")).toBe("/cases/9");
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("reports a failed execution in red with a link to the case, and drops the row", async () => {
    stubFetch([PENDING], {
      body: { approval_id: 4, is_approved: true, case_id: 7, case_status: "FAILED" },
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Approval 4 was saved, but case 7 failed during execution. Check the case timeline.",
    );
    expect(alert.className).toContain("text-red-700");
    expect(screen.queryByText(/approved\. Case/)).toBeNull();
    const link = screen.getByRole("link", { name: "case timeline" });
    expect(link.getAttribute("href")).toBe("/cases/7");
    // The decision was saved, so the request leaves the list
    expect(screen.queryByRole("table")).toBeNull();
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
