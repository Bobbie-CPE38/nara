// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import GapCheck from "@/app/gap/page";
import { ApiError, apiRequest } from "@/lib/api";
import { dashboard, SHIFT_DETAIL, SHIFT_ROW } from "../../fixtures/dashboard";

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

function replies(handler: (path: string, demoUser: number) => Reply) {
  request.mockImplementation(async <T,>(path: string, options?: { demoUser?: number }) => {
    const result = handler(path, options?.demoUser ?? 0);
    if (result instanceof Error) throw result;
    return result as T;
  });
}

const DAY_LIST = "/gap/shifts?ward_id=1&date=2026-10-17";

beforeEach(() => {
  request.mockReset();
});
afterEach(() => cleanup());

describe("Gap check page", () => {
  it("starts on the Backend Clock day in the user's own ward", async () => {
    replies((path) => (path === "/dashboard" ? dashboard() : path === DAY_LIST ? [SHIFT_ROW] : new Error(`unexpected ${path}`)));
    render(<GapCheck />);
    const table = within(await screen.findByRole("table", { name: "Shifts of the day" }));
    expect((screen.getByLabelText("Day the shift starts") as HTMLInputElement).value).toBe("2026-10-17");
    expect((screen.getByLabelText("Ward") as HTMLSelectElement).value).toBe("1");
    const row = within(table.getAllByRole("row")[1]);
    expect(row.getByText("2026-10-17 23:00:00")).toBeTruthy();
    expect(row.getByRole("link", { name: "7" }).getAttribute("href")).toBe("/cases/7");
  });

  it("offers only the wards the dashboard says the user sees", async () => {
    replies((path) => (path === "/dashboard" ? dashboard({ wards: [1, 2, 3] }) : []));
    render(<GapCheck />);
    await screen.findByText("No shift starts on this day in this ward.");
    const options = within(screen.getByLabelText("Ward")).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["ICU", "Medicine", "Float Pool"]);
  });

  it("shows the gap by slice and the roster with leave and check-in", async () => {
    replies((path) => {
      if (path === "/dashboard") return dashboard();
      if (path === DAY_LIST) return [SHIFT_ROW];
      if (path === "/gap/shifts/1") return SHIFT_DETAIL;
      return new Error(`unexpected ${path}`);
    });
    render(<GapCheck />);
    fireEvent.click(await screen.findByRole("button", { name: "Check shift 1" }));
    const gap = within(await screen.findByRole("table", { name: "Gap by time" }));
    expect(gap.getByText("4 of 5")).toBeTruthy();
    expect(gap.getByText("Short: 1 person, 1 RN, 1 ICU")).toBeTruthy();
    const roster = within(screen.getByRole("table", { name: "Roster" }));
    const cancelled = within(roster.getByText("Pimchanok Demo").closest("tr") as HTMLElement);
    expect(cancelled.getByText("CANCELLED")).toBeTruthy();
    // Leave shows Yes, check-in shows No
    expect(cancelled.getAllByRole("cell").slice(-2).map((cell) => cell.textContent)).toEqual(["Yes", "No"]);
    const present = within(roster.getByText("Thanaphon Demo").closest("tr") as HTMLElement);
    expect(present.getAllByRole("cell").slice(-2).map((cell) => cell.textContent)).toEqual(["No", "Yes"]);
    expect(screen.getByRole("link", { name: "Open case 7" }).getAttribute("href")).toBe("/cases/7");
  });

  it("has no button that creates an event or a case, and only reads", async () => {
    replies((path) => (path === "/dashboard" ? dashboard() : path === DAY_LIST ? [SHIFT_ROW] : SHIFT_DETAIL));
    render(<GapCheck />);
    fireEvent.click(await screen.findByRole("button", { name: "Check shift 1" }));
    await screen.findByRole("table", { name: "Roster" });
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(["Check shift 1"]);
    expect(request.mock.calls.every(([, options]) => (options as { method?: string }).method === undefined)).toBe(true);
  });

  it("says there is no running case when the shift has none", async () => {
    replies((path) => {
      if (path === "/dashboard") return dashboard();
      if (path === DAY_LIST) return [{ ...SHIFT_ROW, case_id: null }];
      return { ...SHIFT_DETAIL, case_id: null, roster: [] };
    });
    render(<GapCheck />);
    fireEvent.click(await screen.findByRole("button", { name: "Check shift 1" }));
    expect(await screen.findByText("No running case on this shift.")).toBeTruthy();
    expect(screen.getByText(/Nobody is on this shift.s roster\./)).toBeTruthy();
  });

  it("shows the API's words when a shift is not set up (409)", async () => {
    replies((path) => {
      if (path === "/dashboard") return dashboard();
      if (path === DAY_LIST) return [SHIFT_ROW];
      return new ApiError(409, { detail: "No staffing requirement for shift 1" });
    });
    render(<GapCheck />);
    fireEvent.click(await screen.findByRole("button", { name: "Check shift 1" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("No staffing requirement for shift 1 (HTTP 409)");
  });

  it("reads another day when the date changes and drops the open shift", async () => {
    replies((path) => {
      if (path === "/dashboard") return dashboard();
      if (path === DAY_LIST) return [SHIFT_ROW];
      if (path === "/gap/shifts/1") return SHIFT_DETAIL;
      if (path === "/gap/shifts?ward_id=1&date=2026-10-18") return [];
      return new Error(`unexpected ${path}`);
    });
    render(<GapCheck />);
    fireEvent.click(await screen.findByRole("button", { name: "Check shift 1" }));
    await screen.findByRole("table", { name: "Roster" });
    fireEvent.change(screen.getByLabelText("Day the shift starts"), { target: { value: "2026-10-18" } });
    await screen.findByText("No shift starts on this day in this ward.");
    expect(screen.queryByRole("table", { name: "Roster" })).toBeNull();
  });

  it("starts over as another user", async () => {
    replies((path, user) => {
      if (path === "/dashboard") return user === 902 ? dashboard({ wards: [2] }) : dashboard();
      if (path === DAY_LIST) return [SHIFT_ROW];
      if (path === "/gap/shifts?ward_id=2&date=2026-10-17") return [];
      return new Error(`unexpected ${path}`);
    });
    render(<GapCheck />);
    await screen.findByRole("table", { name: "Shifts of the day" });
    fireEvent.change(screen.getByLabelText(/Viewing as/), { target: { value: "902" } });
    await screen.findByText("No shift starts on this day in this ward.");
    expect((screen.getByLabelText("Ward") as HTMLSelectElement).value).toBe("2");
    await waitFor(() => expect(screen.queryByRole("table", { name: "Shifts of the day" })).toBeNull());
  });

  it("shows a refused ward (403) as the API said it", async () => {
    replies((path) =>
      path === "/dashboard"
        ? dashboard()
        : new ApiError(403, { detail: "Ward 1 is not visible to this user" }),
    );
    render(<GapCheck />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Ward 1 is not visible to this user (HTTP 403)");
  });
});
