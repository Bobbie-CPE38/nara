// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { ApiError, apiRequest } from "@/lib/api";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import { dashboard, withCounts } from "../../fixtures/dashboard";

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  const apiRequest = vi.fn();
  return {
    ...original,
    apiRequest,
    createDemoApi:
      (demoUser: number) =>
      (path: string, options: Omit<import("@/lib/api").ApiOptions, "demoUser"> = {}) =>
        apiRequest(path, { ...options, demoUser }),
  };
});
const request = vi.mocked(apiRequest);

type Reply = unknown | Error;

/** /dashboard answers `board`; /health answers ok */
function replies(board: () => Reply) {
  request.mockImplementation(async <T,>(path: string) => {
    if (path === "/health") return { status: "ok", database: "ok" } as T;
    const result = board();
    if (result instanceof Error) throw result;
    return result as T;
  });
}

beforeEach(() => {
  request.mockReset();
});
afterEach(() => cleanup());

const inScrollBox = (table: HTMLElement) =>
  // A table wider than a phone scrolls inside its box, not the whole page (round 6 PR F3)
  expect(table.parentElement?.className, table.getAttribute("aria-label") ?? "table").toContain("overflow-x-auto");

describe("Dashboard page", () => {
  it("shows the clock, modes and the wards the numbers cover", async () => {
    replies(() => dashboard({ wards: [1, 2, 3] }));
    render(<Home />);
    expect(await screen.findByText(/Backend Clock 2026-10-17 21:00:00/)).toBeTruthy();
    expect(screen.getByText(/LINE: simulation/)).toBeTruthy();
    expect(screen.getByText(/LLM: off/)).toBeTruthy();
    expect(screen.getByText(/Wards: ICU, Medicine, Float Pool/)).toBeTruthy();
  });

  it("lists every status, and links the ones that have a page", async () => {
    replies(() =>
      dashboard({
        cases_by_status: withCounts({ MANUAL_HANDOFF: 2, FAILED: 1, WAITING_APPROVAL: 3, OUTREACH: 4 }),
      }),
    );
    render(<Home />);
    const list = within(await screen.findByRole("region", { name: "Cases by status" }));
    expect(list.getAllByRole("listitem")).toHaveLength(12);
    expect(list.getByRole("link", { name: "MANUAL_HANDOFF" }).getAttribute("href")).toBe("/handoff?as=900");
    expect(list.getByRole("link", { name: "FAILED" }).getAttribute("href")).toBe("/handoff?as=900");
    expect(list.getByRole("link", { name: "WAITING_APPROVAL" }).getAttribute("href")).toBe("/approvals?as=900");
    // OUTREACH has no list page, so it is a count only
    expect(list.queryByRole("link", { name: "OUTREACH" })).toBeNull();
    expect(list.getByText("OUTREACH: 4")).toBeTruthy();
    // A status that needs a person stands out only while it has cases
    expect(list.getByText(/MANUAL_HANDOFF/).closest("li")?.className).toContain("font-semibold");
    expect(list.getByText("RESOLVED: 0").closest("li")?.className ?? "").not.toContain("font-semibold");
  });

  it("keeps the short shifts and the no-shows in boxes that scroll sideways on a phone", async () => {
    replies(() =>
      dashboard({
        shortages: [
          {
            shift_id: 1,
            ward_id: 1,
            start_at: "2026-10-17T23:00:00+07:00",
            end_at: "2026-10-18T07:00:00+07:00",
            headcount_gap: 1,
            role_gaps: [{ name: "RN", gap_count: 1 }],
            skill_gaps: [{ name: "ICU", gap_count: 1 }],
            case_id: 7,
          },
        ],
        recent_no_show: [{ event_id: 9, shift_id: 1, staff_id: 104, created_at: "2026-10-18T00:00:00+07:00" }],
      }),
    );
    render(<Home />);
    const tables = [await screen.findByRole("table", { name: "Short shifts" }), screen.getByRole("table", { name: "Recent no-shows" })];
    tables.forEach(inScrollBox);
  });

  it("speaks Thai when the language is Thai, and keeps the codes and names as the API sent them", async () => {
    replies(() =>
      dashboard({
        wards: [1, 2],
        cases_by_status: withCounts({ MANUAL_HANDOFF: 2, OUTREACH: 4 }),
        shortages: [
          {
            shift_id: 1, ward_id: 1, start_at: "2026-10-17T23:00:00+07:00", end_at: "2026-10-18T07:00:00+07:00",
            headcount_gap: 1, role_gaps: [{ name: "RN", gap_count: 1 }], skill_gaps: [], case_id: 7,
          },
        ],
      }),
    );
    render(<LanguageProvider initial="th"><Home /></LanguageProvider>);

    expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("แดชบอร์ด");
    expect(screen.getByLabelText("ดูในฐานะ")).toBeTruthy();
    expect(screen.getByRole("option", { name: "902 — หัวหน้าหอ, Medicine" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "950 — ผู้ควบคุมดูแล, ทุกหอ" })).toBeTruthy();
    const counts = within(screen.getByRole("region", { name: "เคสตามสถานะ" }));
    // The status codes are the Backend's words
    expect(counts.getByRole("link", { name: "MANUAL_HANDOFF" })).toBeTruthy();
    expect(counts.getByText("OUTREACH: 4")).toBeTruthy();
    const shifts = within(screen.getByRole("region", { name: "เวรที่ขาดคน" }));
    expect(shifts.getByRole("link", { name: "เคส 7" }).getAttribute("href")).toBe("/cases/7");
    expect(shifts.getByText("1 RN")).toBeTruthy();
    expect(screen.getByText(/นาฬิกา Backend 2026-10-17 21:00:00/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "ตรวจระบบ" })).toBeTruthy();
    // Nothing of the English page is left
    expect(screen.queryByText("Short shifts")).toBeNull();
    expect(screen.queryByText("Cases by status")).toBeNull();
  });

  it("lists a short shift with its roles, skills and case", async () => {
    replies(() =>
      dashboard({
        shortages: [
          {
            shift_id: 1,
            ward_id: 1,
            start_at: "2026-10-17T23:00:00+07:00",
            end_at: "2026-10-18T07:00:00+07:00",
            headcount_gap: 1,
            role_gaps: [{ name: "RN", gap_count: 1 }],
            skill_gaps: [{ name: "ICU", gap_count: 1 }],
            case_id: 7,
          },
          {
            shift_id: 2,
            ward_id: 2,
            start_at: "2026-10-18T07:00:00+07:00",
            end_at: "2026-10-18T15:00:00+07:00",
            headcount_gap: 2,
            role_gaps: [],
            skill_gaps: [],
            case_id: null,
          },
        ],
      }),
    );
    render(<Home />);
    const table = within(await screen.findByRole("table", { name: "Short shifts" }));
    const rows = table.getAllByRole("row");
    expect(rows).toHaveLength(3);
    const first = within(rows[1]);
    expect(first.getByText("1 RN")).toBeTruthy();
    expect(first.getByText("1 ICU")).toBeTruthy();
    expect(first.getByRole("link", { name: "Case 7" }).getAttribute("href")).toBe("/cases/7");
    const second = within(rows[2]);
    expect(second.getByText("Medicine")).toBeTruthy();
    expect(second.getByText("No case yet")).toBeTruthy();
  });

  it("says plainly when no shift is short", async () => {
    replies(() => dashboard());
    render(<Home />);
    expect(await screen.findByText("No shift is short.")).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Short shifts" })).toBeNull();
  });

  it("shows open offers, approvals by ward and recent no-shows", async () => {
    replies(() =>
      dashboard({
        open_offers: { count: 2 },
        pending_approvals: [{ ward_id: 1, count: 3 }],
        recent_no_show: [{ event_id: 9, shift_id: 1, staff_id: 104, created_at: "2026-10-18T00:00:00+07:00" }],
      }),
    );
    render(<Home />);
    const waiting = within(await screen.findByRole("region", { name: "Waiting for people" }));
    expect(waiting.getByText(/Offers sent and waiting for a reply: 2/)).toBeTruthy();
    expect(waiting.getByRole("link", { name: "3" }).getAttribute("href")).toBe("/approvals?as=900");
    const noShows = within(screen.getByRole("table", { name: "Recent no-shows" }));
    expect(noShows.getByText("104")).toBeTruthy();
    expect(noShows.getByText("2026-10-18 00:00:00")).toBeTruthy();
  });

  it("hides LLM usage while the API sends none, and warns about unknown costs", async () => {
    replies(() => dashboard());
    const { unmount } = render(<Home />);
    await screen.findByText("No shift is short.");
    expect(screen.queryByRole("region", { name: "LLM usage" })).toBeNull();
    unmount();

    replies(() =>
      dashboard({
        modes: { line_mode: "real", llm_provider: "bedrock", llm_enabled: true },
        llm_usage: {
          date: "2026-10-17",
          used: 100,
          cap: 100,
          month_cost_usd: "20.5",
          month_calls_without_cost: 3,
          budget_usd: "20",
        },
      }),
    );
    render(<Home />);
    const usage = within(await screen.findByRole("region", { name: "LLM usage" }));
    expect(usage.getByText(/Today \(2026-10-17\): 100 of 100 calls/)).toBeTruthy();
    expect(usage.getByText("Daily limit reached")).toBeTruthy();
    expect(usage.getByText(/20\.5 of 20 USD/)).toBeTruthy();
    expect(usage.getByText("Budget reached")).toBeTruthy();
    expect(usage.getByText(/3 calls this month have no known cost/)).toBeTruthy();
    expect(screen.getByText(/LLM: bedrock/)).toBeTruthy();
  });

  it("keeps the last numbers and says so when a later read fails", async () => {
    let calls = 0;
    replies(() => {
      calls += 1;
      return calls === 1 ? dashboard({ open_offers: { count: 5 } }) : new ApiError(500, { detail: "boom" });
    });
    render(<Home />);
    await screen.findByText(/waiting for a reply: 5/);
    // The page reads again every 2 seconds
    const alert = await screen.findByRole("alert", {}, { timeout: 4000 });
    expect(alert.textContent).toContain("boom");
    expect(alert.textContent).toContain("last successful read");
    expect(screen.getByText(/waiting for a reply: 5/)).toBeTruthy();
  });

  it("reads as the chosen user, and the system check stays on the page", async () => {
    replies(() => dashboard());
    render(<Home />);
    await screen.findByText("No shift is short.");
    expect(request).toHaveBeenCalledWith("/dashboard", expect.objectContaining({ demoUser: 900 }));
    fireEvent.change(screen.getByLabelText(/Viewing as/), { target: { value: "950" } });
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dashboard", expect.objectContaining({ demoUser: 950 })),
    );
    const status = within(await screen.findByRole("region", { name: "System check" }));
    expect(await status.findAllByText("ok")).toHaveLength(2);
  });
});
