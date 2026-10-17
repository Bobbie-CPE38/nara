// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  // 900 seconds after the request (docs/workflow.md, section 6.13)
  expires_at: "2026-10-09T21:15:00+07:00",
  home_ward_id: 1,
  source_ward_id: null,
  wards: [{ ward_id: 1, side: "DESTINATION", status: "PENDING" }],
  supervisor_from: "2026-10-09T21:10:00+07:00",
};

/** The part of GET /cases/{id} the page reads: a gap of two with one person assigned. */
const CASE = { id: 7, gap: { headcount_gap: 2 }, assigned_count: 1 };

/** GET answers the list, the case or the auto history; POST answers `decision`. */
function stubFetch(
  list: unknown[],
  decision: { body: unknown; status?: number } | null = null,
  caseAnswer: { body: unknown; status?: number } = { body: CASE },
  auto: unknown[] = [],
) {
  const fetchMock = vi.fn().mockImplementation(async (url: string, request: RequestInit) => {
    if (request.method === "POST" && decision) {
      return new Response(JSON.stringify(decision.body), { status: decision.status ?? 200 });
    }
    if (/\/approvals\/auto$/.test(url)) return new Response(JSON.stringify(auto));
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
    const [url, request] = fetchMock.mock.calls.find(([called]) => /pending=true$/.test(called))!;
    expect(url).toMatch(/\/approvals\?pending=true$/);
    expect(request.headers.get("X-Demo-User")).toBe("900");
  });

  it("shows each deadline in the Decide by cell of its own row, in Bangkok time", async () => {
    // The second deadline arrives in UTC: 14:20Z is 21:20 in Bangkok
    stubFetch([PENDING, { ...PENDING, id: 5, staff_id: 202, expires_at: "2026-10-09T14:20:00Z" }]);
    render(createElement(Approvals));

    await screen.findByRole("columnheader", { name: "Decide by" });
    const [header, ...rows] = screen.getAllByRole("row");
    const headers = within(header).getAllByRole("columnheader").map((cell) => cell.textContent);
    const column = headers.indexOf("Decide by");
    // Right after the request time, and exactly once
    expect(column).toBe(headers.indexOf("Requested at") + 1);
    expect(headers.filter((name) => name === "Decide by")).toHaveLength(1);

    const cellsOf = (row: HTMLElement) => within(row).getAllByRole("cell");
    const byStaff = new Map(
      rows.map((row) => [cellsOf(row)[headers.indexOf("Staff")].textContent, cellsOf(row)]),
    );
    expect(byStaff.get("201")?.[column].textContent).toBe("2026-10-09 21:15:00");
    expect(byStaff.get("202")?.[column].textContent).toBe("2026-10-09 21:20:00");
    // Each deadline appears once: no other column repeats it
    expect(screen.getAllByText("2026-10-09 21:15:00")).toHaveLength(1);
    expect(screen.getAllByText("2026-10-09 21:20:00")).toHaveLength(1);
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
    const [header, row] = screen.getAllByRole("row");
    const column = within(header)
      .getAllByRole("columnheader")
      .map((cell) => cell.textContent)
      .indexOf("Case still needs");
    expect(within(row).getAllByRole("cell")[column].textContent).toBe("—");
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

  it("shows why a head nurse of another ward cannot decide, and keeps the row", async () => {
    // GET /approvals lists every ward; the decision is limited to the shift's ward
    const fetchMock = stubFetch([PENDING], {
      body: { detail: "The staff member is not a head nurse of the shift's ward" },
      status: 403,
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Approval 4: The staff member is not a head nurse of the shift's ward (HTTP 403)",
    );
    expect(posts(fetchMock)).toHaveLength(1);
    expect(screen.getByRole("table")).toBeTruthy();
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
                : /\/approvals\/auto$/.test(url)
                  ? []
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

  describe("a rejection reason being typed", () => {
    // After a demo reset the sequence restarts: same ID, another candidate
    const REUSED = { ...PENDING, case_id: 9, candidate_item_id: 12, staff_id: 203 };
    let list: unknown[];
    const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

    async function openAndType(text: string) {
      vi.useFakeTimers();
      list = [PENDING];
      const fetchMock = vi.fn().mockImplementation(async (url: string) =>
        new Response(
          JSON.stringify(
            /\/cases\/\d+$/.test(url) ? CASE : /\/approvals\/auto$/.test(url) ? [] : list,
          ),
        ),
      );
      vi.stubGlobal("fetch", fetchMock);
      render(createElement(Approvals));
      await tick(0);
      fireEvent.click(screen.getByRole("button", { name: "Reject" }));
      fireEvent.change(screen.getByRole("textbox"), { target: { value: text } });
      return fetchMock;
    }

    function expectNoInheritedReason() {
      expect(screen.queryByRole("textbox")).toBeNull();
      expect(screen.queryByRole("button", { name: "Confirm rejection" })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Reject" }));
      expect(
        screen.getByLabelText<HTMLTextAreaElement>(
          "Reason for rejecting approval 4 (staff 203, case 9)",
        ).value,
      ).toBe("");
    }

    it("stays while the polls still list the same request", async () => {
      await openAndType("Reason intended only for staff 201");
      await tick(4000);

      expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe(
        "Reason intended only for staff 201",
      );
    });

    it("is dropped when the request leaves the list and its ID is used again", async () => {
      const fetchMock = await openAndType("Reason intended only for staff 201");
      list = [];
      await tick(2000);
      expect(screen.queryByRole("textbox")).toBeNull();

      list = [REUSED];
      await tick(2000);

      expectNoInheritedReason();
      expect(posts(fetchMock)).toHaveLength(0);
    });

    it("is dropped when another request takes the ID with no empty list in between", async () => {
      const fetchMock = await openAndType("Reason intended only for staff 201");
      list = [REUSED];
      await tick(2000);

      expectNoInheritedReason();
      expect(posts(fetchMock)).toHaveLength(0);
    });

    it("blocks Reject on the other rows until it is cancelled", async () => {
      await openAndType("Needs rest");
      list = [PENDING, { ...PENDING, id: 5, candidate_item_id: 12, staff_id: 202 }];
      await tick(2000);

      const rejects = () => screen.getAllByRole<HTMLButtonElement>("button", { name: "Reject" });
      expect(rejects().map((button) => button.disabled)).toEqual([true, true]);
      expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("Needs rest");

      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      expect(rejects().map((button) => button.disabled)).toEqual([false, false]);
    });
  });

  it("sends a reason of exactly 500 characters whole", async () => {
    const fetchMock = stubFetch([PENDING], {
      body: { approval_id: 4, is_approved: false, case_id: 7, case_status: "WAITING_RESPONSE" },
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "x".repeat(500) } });
    expect(screen.getByText(/^500 \/ 500\./)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));

    await screen.findByText("Approval 4 rejected. Case 7: WAITING_RESPONSE");
    expect(JSON.parse(posts(fetchMock)[0][1].body).reason).toHaveLength(500);
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
    expect(alert.className).toContain("text-red-800");
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

    // The pending list and the auto history both report it
    expect((await screen.findAllByText("Unknown demo user")).length).toBeGreaterThan(0);
  });
});


it("does not call a first-side approval a rejection or an assignment", async () => {
  stubFetch([PENDING], {
    body: { approval_id: 4, is_approved: null, case_id: 7,
      case_status: "WAITING_APPROVAL", outcome: "WAITING_OTHER_WARD",
      reason: null, failed_rules: [] },
  });
  render(createElement(Approvals));
  fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
  expect(await screen.findByText("Approval 4: ward approved; waiting for the other ward.")).toBeTruthy();
  expect(screen.queryByText(/Approval 4 rejected/)).toBeNull();
});

describe("round 4 (PR U)", () => {
  // A transfer from Medicine (2) to ICU (1); ICU already approved
  const TRANSFER = {
    ...PENDING,
    source_ward_id: 2,
    wards: [
      { ward_id: 1, side: "DESTINATION", status: "APPROVED" },
      { ward_id: 2, side: "SOURCE", status: "PENDING" },
    ],
  };
  const BOTH_WAITING = {
    ...TRANSFER,
    wards: [
      { ward_id: 1, side: "DESTINATION", status: "PENDING" },
      { ward_id: 2, side: "SOURCE", status: "PENDING" },
    ],
  };

  function cell(name: string) {
    const [header, row] = screen.getAllByRole("table")[0].querySelectorAll("tr");
    const column = within(header as HTMLElement)
      .getAllByRole("columnheader")
      .map((item) => item.textContent)
      .indexOf(name);
    return within(row as HTMLElement).getAllByRole("cell")[column].textContent;
  }

  it("shows the home ward, the source ward, each ward's status and the Supervisor time", async () => {
    stubFetch([TRANSFER]);
    render(createElement(Approvals));
    await screen.findByRole("button", { name: "Approve" });

    expect(cell("Home ward")).toBe("ICU");
    expect(cell("Moved from")).toBe("Medicine");
    expect(cell("Wards")).toBe("ICU (destination): approved; Medicine (source): waiting");
    expect(cell("Supervisor from")).toBe("2026-10-09 21:10:00");
  });

  it("acts as the chosen approver and sends no side for a head nurse", async () => {
    const fetchMock = stubFetch([BOTH_WAITING], {
      body: { approval_id: 4, is_approved: null, case_id: 7, case_status: "WAITING_APPROVAL",
        outcome: "WAITING_OTHER_WARD", reason: null, failed_rules: [] },
    });
    render(createElement(Approvals));
    await screen.findByRole("button", { name: "Approve" });
    fireEvent.change(screen.getByLabelText("Acting as"), { target: { value: "902" } });
    await screen.findByRole("button", { name: "Approve" });

    expect(screen.queryByLabelText("Side for approval 4")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await screen.findByText("Approval 4: ward approved; waiting for the other ward.");
    const [[, request]] = posts(fetchMock);
    expect(request.headers.get("X-Demo-User")).toBe("902");
    expect(JSON.parse(request.body)).toEqual({ approved: true });
    // Still listed: the other ward decides next
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("lets the Supervisor pick the side when both wards still wait", async () => {
    const fetchMock = stubFetch([BOTH_WAITING], {
      body: { approval_id: 4, is_approved: null, case_id: 7, case_status: "WAITING_APPROVAL",
        outcome: "WAITING_OTHER_WARD", reason: null, failed_rules: [] },
    });
    render(createElement(Approvals));
    await screen.findByRole("button", { name: "Approve" });
    fireEvent.change(screen.getByLabelText("Acting as"), { target: { value: "950" } });
    const side = await screen.findByLabelText<HTMLSelectElement>("Side for approval 4");
    fireEvent.change(side, { target: { value: "SOURCE" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await screen.findByText("Approval 4: ward approved; waiting for the other ward.");
    const [[, request]] = posts(fetchMock);
    expect(request.headers.get("X-Demo-User")).toBe("950");
    expect(JSON.parse(request.body)).toEqual({ approved: true, side: "SOURCE" });
  });

  it("sends no side when only one ward is left, even for the Supervisor", async () => {
    stubFetch([TRANSFER]);
    render(createElement(Approvals));
    await screen.findByRole("button", { name: "Approve" });
    fireEvent.change(screen.getByLabelText("Acting as"), { target: { value: "950" } });
    await screen.findByRole("button", { name: "Approve" });

    expect(screen.queryByLabelText("Side for approval 4")).toBeNull();
  });

  it("says an approved transfer was cancelled, with the reason and the rules", async () => {
    stubFetch([BOTH_WAITING], {
      body: { approval_id: 4, is_approved: true, case_id: 7, case_status: "WAITING_RESPONSE",
        outcome: "TRANSFER_CANCELLED", reason: "SOURCE_SHIFT_STARTED", failed_rules: ["SHIFT_CONFLICT"] },
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText(
        "Approval 4: approved, but the transfer was cancelled (SOURCE_SHIFT_STARTED: SHIFT_CONFLICT). Case 7: WAITING_RESPONSE.",
      ),
    ).toBeTruthy();
  });

  it("reports EXECUTION_FAILED as a failed execution", async () => {
    stubFetch([PENDING], {
      body: { approval_id: 4, is_approved: true, case_id: 7, case_status: "FAILED",
        outcome: "EXECUTION_FAILED", reason: null, failed_rules: [] },
    });
    render(createElement(Approvals));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect((await screen.findByRole("alert")).textContent).toContain("failed during execution");
  });

  it("lists what the system approved for the current approver", async () => {
    const fetchMock = stubFetch([], null, { body: { ...CASE, status: "RESOLVED" } }, [
      { ...PENDING, id: 8, staff_id: 202, approval_mode: "AUTO", is_pending: false,
        wards: [{ ward_id: 1, side: "DESTINATION", status: "APPROVED" }],
        decided_at: "2026-10-09T21:05:00+07:00" },
    ]);
    render(createElement(Approvals));

    const history = await screen.findByRole("table", { name: "Approved by the system" });
    await waitFor(() => expect(within(history).getByText("RESOLVED")).toBeTruthy());
    const [, row] = within(history).getAllByRole("row");
    expect(within(row).getAllByRole("cell").map((item) => item.textContent)).toEqual([
      "8", "7", "202", "ICU (destination): approved", "2026-10-09 21:05:00", "RESOLVED",
    ]);
    const [, request] = fetchMock.mock.calls.find(([url]) => /\/approvals\/auto$/.test(url))!;
    expect(request.headers.get("X-Demo-User")).toBe("900");
  });

  it("flags an automatic approval whose execution failed (D11)", async () => {
    stubFetch([], null, { body: { ...CASE, status: "FAILED" } }, [
      { ...TRANSFER, id: 8, approval_mode: "AUTO", is_pending: false,
        wards: [
          { ward_id: 1, side: "DESTINATION", status: "APPROVED" },
          { ward_id: 2, side: "SOURCE", status: "APPROVED" },
        ],
        decided_at: "2026-10-09T21:05:00+07:00" },
    ]);
    render(createElement(Approvals));

    const history = await screen.findByRole("table", { name: "Approved by the system" });
    const failed = await within(history).findByText(
      "FAILED: case workflow failed; check assignment outcome",
    );
    expect(failed.className).toContain("text-red-700");
    // Both wards of the request are listed, not only the first
    expect(
      within(history).getByText("ICU (destination): approved; Medicine (source): approved"),
    ).toBeTruthy();
  });

  it("gives a head nurse no buttons on a request of another ward", async () => {
    // Medicine-only request: 900 of ICU sees it in the list but cannot decide it
    const MEDICINE = { ...PENDING, proposed_shift_id: 21,
      wards: [{ ward_id: 2, side: "DESTINATION", status: "PENDING" }] };
    const fetchMock = stubFetch([MEDICINE]);
    render(createElement(Approvals));

    const approve = await screen.findByRole<HTMLButtonElement>("button", { name: "Approve" });
    expect(approve.disabled).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Reject" }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Acting as"), { target: { value: "902" } });
    await waitFor(() => expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "Approve" }).disabled,
    ).toBe(false));
    expect(posts(fetchMock)).toHaveLength(0);
  });

  it("gives a head nurse no buttons once their own ward has approved", async () => {
    stubFetch([TRANSFER]);
    render(createElement(Approvals));

    // 900 is ICU, and the ICU side is already approved; Medicine still waits
    const approve = await screen.findByRole<HTMLButtonElement>("button", { name: "Approve" });
    expect(approve.disabled).toBe(true);
  });
});
