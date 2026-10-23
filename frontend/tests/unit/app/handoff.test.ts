// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Handoff from "../../../src/app/handoff/page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const STOPPED = {
  id: 7,
  status: "MANUAL_HANDOFF",
  shift_id: 1,
  ward_id: 1,
  required_replacement_time: "2026-10-09T23:00:00+07:00",
  created_at: "2026-10-09T21:00:00+07:00",
  headcount_gap: 2,
  assigned_count: 1,
  can_manage: true,
};
const FAILED = { ...STOPPED, id: 8, status: "FAILED", headcount_gap: null, can_manage: false };

const FREE = {
  staff_id: 201,
  first_name: "Arunee",
  last_name: "Demo",
  role_id: 1,
  role_name: "RN",
  blocking_rules: [],
  other_case_ids: [],
};
const ON_SHIFT = { ...FREE, staff_id: 101, first_name: "Pimchanok", blocking_rules: ["ALREADY_ON_SHIFT"] };
const TIRED = { ...FREE, staff_id: 202, first_name: "Phanu", blocking_rules: ["INSUFFICIENT_REST"] };
const OFFERED = { ...FREE, staff_id: 203, first_name: "Chonthicha", other_case_ids: [9] };

type Answer = { body: unknown; status?: number };

/** One page of GET /cases/search with the cases of the old list */
function page(cases: unknown[], total = cases.length) {
  return {
    items: cases.map((row) => ({
      ward_name: "ICU",
      shift_type: "NIGHT",
      shift_start_at: "2026-10-09T23:00:00+07:00",
      ...(row as object),
    })),
    total,
    page: 1,
    page_size: 10,
  };
}

/** GET answers the case list or the candidates; each POST takes the next answer. */
function stubFetch(posts: Answer[] = [], cases: unknown[] = [STOPPED, FAILED]) {
  const queue = [...posts];
  const fetchMock = vi.fn().mockImplementation(async (url: string, request: RequestInit) => {
    if (request.method === "POST") {
      const answer = queue.shift() ?? { body: {} };
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
    }
    if (/\/handoff\/candidates$/.test(url)) {
      return new Response(JSON.stringify([ON_SHIFT, FREE, TIRED, OFFERED]));
    }
    // GET /cases/search answers one page (round 6 PR EV6)
    return new Response(JSON.stringify(page(cases)));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function posts(fetchMock: ReturnType<typeof stubFetch>) {
  return fetchMock.mock.calls.filter(([, request]) => request.method === "POST");
}

async function openCase() {
  fireEvent.click(await screen.findByRole("button", { name: "Manage" }));
  await screen.findByText("Arunee Demo");
}

function rowOf(name: string): HTMLElement {
  const row = screen.getByText(name).closest("tr");
  if (!row) throw new Error(`No row for ${name}`);
  return row;
}

describe("handoff page", () => {
  it("lists the cases of the ward as head nurse 900", async () => {
    const fetchMock = stubFetch();
    render(createElement(Handoff));

    const link = await screen.findByRole("link", { name: "7" });
    expect(link.getAttribute("href")).toBe("/cases/7");
    const [url, request] = fetchMock.mock.calls[0];
    // One page of the search of round 6 PR EV6, the oldest case first
    expect(url).toMatch(/\/cases\/search\?page=1&page_size=10&sort=oldest&status=MANUAL_HANDOFF%2CFAILED$/);
    expect(request.headers.get("X-Demo-User")).toBe("900");
    // A gap of two with one person already assigned: still short of one
    const cells = within(link.closest("tr") as HTMLElement).getAllByRole("cell");
    expect(cells.map((cell) => cell.textContent)).toEqual([
      "7",
      "MANUAL_HANDOFF",
      "ICU",
      "1",
      "1",
      "2026-10-09 21:00:00",
      "Manage",
    ]);
  });

  it("lists a FAILED case without a way to manage it", async () => {
    stubFetch();
    render(createElement(Handoff));

    const failedRow = (await screen.findByRole("link", { name: "8" })).closest("tr") as HTMLElement;
    expect(within(failedRow).getByText("Cannot be managed")).toBeTruthy();
    expect(within(failedRow).queryByRole("button")).toBeNull();
    expect(within(failedRow).getByText("—")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Manage" })).toHaveLength(1);
  });

  it("says so when no case is handed off", async () => {
    stubFetch([], []);
    render(createElement(Handoff));

    expect(await screen.findByText("No handed-off cases.")).toBeTruthy();
  });

  it("shows why each person is blocked and allows no override", async () => {
    stubFetch();
    render(createElement(Handoff));
    await openCase();

    expect(within(rowOf("Pimchanok Demo")).getByText("Already on this shift")).toBeTruthy();
    expect(
      within(rowOf("Phanu Demo")).getByText("Not enough rest before or after the shift"),
    ).toBeTruthy();
    const assignOf = (name: string) =>
      within(rowOf(name)).getByRole<HTMLButtonElement>("button", { name: "Assign" });
    expect(assignOf("Pimchanok Demo").disabled).toBe(true);
    expect(assignOf("Phanu Demo").disabled).toBe(true);
    expect(assignOf("Arunee Demo").disabled).toBe(false);
    expect(within(rowOf("Chonthicha Demo")).getByText(/offer on case 9/)).toBeTruthy();
  });

  it("assigns a free person with the trimmed note and shows the case result", async () => {
    const fetchMock = stubFetch([
      {
        body: {
          manual_assignment_id: 1,
          assignment_id: 30,
          staff_id: 201,
          case_id: 7,
          case_status: "RESOLVED",
          cancelled_outreach_ids: [],
        },
      },
    ]);
    render(createElement(Handoff));
    await openCase();
    fireEvent.change(screen.getByLabelText("Note for the assignment (optional)"), {
      target: { value: "  Called in  " },
    });
    fireEvent.click(within(rowOf("Arunee Demo")).getByRole("button", { name: "Assign" }));

    expect(await screen.findByText("Staff 201 assigned. Case 7: RESOLVED.")).toBeTruthy();
    const [[url, request]] = posts(fetchMock);
    expect(url).toMatch(/\/cases\/7\/handoff\/assignments$/);
    expect(request.headers.get("X-Demo-User")).toBe("900");
    expect(JSON.parse(request.body)).toEqual({ staff_id: 201, reason: "Called in" });
    // A resolved case has nothing left to manage
    expect(screen.queryByRole("dialog", { name: "Manage case 7" })).toBeNull();
  });

  it("asks before cancelling an offer elsewhere, then sends the confirmation", async () => {
    const fetchMock = stubFetch([
      {
        status: 409,
        body: {
          detail: {
            code: "CONFLICTING_OFFERS",
            message: "Staff 203 has an offer on case 9 that this shift rules out.",
            case_ids: [9],
          },
        },
      },
      {
        body: {
          manual_assignment_id: 1,
          assignment_id: 30,
          staff_id: 203,
          case_id: 7,
          case_status: "MANUAL_HANDOFF",
          cancelled_outreach_ids: [41],
        },
      },
    ]);
    render(createElement(Handoff));
    await openCase();
    fireEvent.click(within(rowOf("Chonthicha Demo")).getByRole("button", { name: "Assign" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Staff 203 has an offer on case 9");
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Assign and cancel the other offer" }),
    );

    expect(
      await screen.findByText(
        "Staff 203 assigned. Case 7: MANUAL_HANDOFF. Offers cancelled elsewhere: 41.",
      ),
    ).toBeTruthy();
    const sent = posts(fetchMock).map(([, request]) => JSON.parse(request.body));
    expect(sent).toEqual([{ staff_id: 203 }, { staff_id: 203, confirm_conflicts: true }]);
  });

  it("keeps the other offer when the head nurse declines", async () => {
    const fetchMock = stubFetch([
      {
        status: 409,
        body: { detail: { code: "CONFLICTING_OFFERS", message: "x", case_ids: [9] } },
      },
    ]);
    render(createElement(Handoff));
    await openCase();
    fireEvent.click(within(rowOf("Chonthicha Demo")).getByRole("button", { name: "Assign" }));
    fireEvent.click(await screen.findByRole("button", { name: "Keep the other offer" }));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(fetchMock)).toHaveLength(1);
  });

  it("explains a Hard Rule the server found after the list was read", async () => {
    stubFetch([
      {
        status: 409,
        body: {
          detail: {
            code: "HARD_RULES_FAILED",
            message: "Staff 201 cannot take this shift: WEEKLY_HOURS_EXCEEDED",
            failed_rules: ["WEEKLY_HOURS_EXCEEDED"],
          },
        },
      },
    ]);
    render(createElement(Handoff));
    await openCase();
    fireEvent.click(within(rowOf("Arunee Demo")).getByRole("button", { name: "Assign" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Staff 201 cannot take this shift: Would exceed the weekly hours limit",
    );
  });

  it("closes the case only with a reason, sent trimmed", async () => {
    const fetchMock = stubFetch([{ body: { case_id: 7, case_status: "UNRESOLVED" } }]);
    render(createElement(Handoff));
    await openCase();

    const reason = screen.getByLabelText<HTMLTextAreaElement>(
      "Reason for closing case 7 without a replacement",
    );
    const submit = screen.getByRole<HTMLButtonElement>("button", {
      name: "Close without a replacement",
    });
    expect(reason.maxLength).toBe(500);
    fireEvent.change(reason, { target: { value: "   " } });
    expect(submit.disabled).toBe(true);
    fireEvent.change(reason, { target: { value: "  Nobody can come in  " } });
    fireEvent.click(submit);

    expect(await screen.findByText("Case 7: UNRESOLVED")).toBeTruthy();
    const [[url, request]] = posts(fetchMock);
    expect(url).toMatch(/\/cases\/7\/handoff\/close$/);
    expect(JSON.parse(request.body)).toEqual({ reason: "Nobody can come in" });
  });

  it("shows a refusal of the API with its status", async () => {
    stubFetch([
      { status: 403, body: { detail: "The staff member is not a head nurse of the shift's ward" } },
    ]);
    render(createElement(Handoff));
    await openCase();
    fireEvent.click(within(rowOf("Arunee Demo")).getByRole("button", { name: "Assign" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "The staff member is not a head nurse of the shift's ward (HTTP 403)",
    );
  });

  it("never shows the staff of a case answered late over the case now selected", async () => {
    const OTHER = { ...STOPPED, id: 9, shift_id: 2 };
    const late: Record<number, (rows: unknown[]) => void> = {};
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        const match = /\/cases\/(\d+)\/handoff\/candidates$/.exec(url);
        if (!match) return new Response(JSON.stringify(page([STOPPED, OTHER])));
        // Each case's staff list answers only when the test says so
        const rows = await new Promise<unknown[]>((resolve) => {
          late[Number(match[1])] = resolve;
        });
        return new Response(JSON.stringify(rows));
      }),
    );
    render(createElement(Handoff));
    const [manage7, manage9] = await screen.findAllByRole("button", { name: "Manage" });

    fireEvent.click(manage7);
    fireEvent.click(manage9);
    // Case 9 answers first, then the stale answer of case 7 arrives
    await act(async () => late[9]([{ ...FREE, first_name: "Ninth" }]));
    await act(async () => late[7]([{ ...FREE, first_name: "Seventh" }]));

    expect(screen.getByRole("dialog", { name: "Manage case 9" })).toBeTruthy();
    expect(screen.getByText("Ninth Demo")).toBeTruthy();
    expect(screen.queryByText("Seventh Demo")).toBeNull();
  });

  it("reads the messages of a validation error instead of a generic one", async () => {
    stubFetch([
      {
        status: 422,
        body: { detail: [{ loc: ["body", "staff_id"], msg: "Input should be greater than 0" }] },
      },
    ]);
    render(createElement(Handoff));
    await openCase();
    fireEvent.click(within(rowOf("Arunee Demo")).getByRole("button", { name: "Assign" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Input should be greater than 0 (HTTP 422)",
    );
  });

  it("says so when the case it manages is staffed or closed elsewhere", async () => {
    vi.useFakeTimers();
    let cases: unknown[] = [STOPPED];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) =>
        new Response(
          JSON.stringify(/\/handoff\/candidates$/.test(url) ? [FREE] : page(cases)),
        ),
      ),
    );
    const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    render(createElement(Handoff));
    await tick(0);
    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    await tick(0);
    expect(screen.getByRole("dialog", { name: "Manage case 7" })).toBeTruthy();

    // Another head nurse closed it: the next poll lists it as UNRESOLVED
    cases = [{ ...STOPPED, status: "UNRESOLVED", can_manage: false }];
    await tick(2000);

    expect(screen.queryByRole("dialog", { name: "Manage case 7" })).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(
      "Case 7 can no longer be managed: it is now UNRESOLVED.",
    );
  });
});

describe("handoff list of round 6 PR EV6", () => {
  it("searches, filters by status and pages, oldest case first", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      const pageNumber = Number(new URL(url).searchParams.get("page"));
      return new Response(JSON.stringify({ ...page([STOPPED], 11), page: pageNumber }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(createElement(Handoff));
    await screen.findByRole("link", { name: "7" });
    const urls = () => fetchMock.mock.calls.map(([url]) => new URL(url).search);

    expect(screen.getByText("Page 1 of 2 · 11 in all")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await vi.waitFor(() => expect(urls()).toContain("?page=2&page_size=10&sort=oldest&status=MANUAL_HANDOFF%2CFAILED"));

    fireEvent.change(screen.getByLabelText(/^Status/), { target: { value: "FAILED" } });
    await vi.waitFor(() => expect(urls()).toContain("?page=1&page_size=10&sort=oldest&status=FAILED"));

    fireEvent.change(screen.getByLabelText(/^Search/), { target: { value: "21" } });
    fireEvent.click(screen.getByRole("button", { name: "Find" }));
    await vi.waitFor(() => expect(urls()).toContain("?page=1&page_size=10&sort=oldest&q=21&status=FAILED"));
  });

  it("manages a case in a dialog that closes with its button or Escape", async () => {
    stubFetch();
    render(createElement(Handoff));
    await openCase();

    const dialog = screen.getByRole("dialog", { name: "Manage case 7" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    await openCase();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    // The list stays where it was
    expect(screen.getByRole("link", { name: "7" })).toBeTruthy();
  });
});
