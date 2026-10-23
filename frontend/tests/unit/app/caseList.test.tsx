// @vitest-environment jsdom
// The case list of round 6 PR EV6 (docs/workflow.md 6.36.6): search, a status filter and pages.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CaseList from "@/app/cases/page";
import { apiRequest } from "@/lib/api";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
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

const item = (id: number, status: string) => ({
  id,
  status,
  shift_id: 21,
  ward_id: 2,
  ward_name: "Medicine",
  shift_type: "NIGHT",
  shift_start_at: "2026-10-09T23:00:00+07:00",
  required_replacement_time: "2026-10-09T23:00:00+07:00",
  created_at: "2026-10-09T21:00:00+07:00",
  headcount_gap: 2,
  assigned_count: 1,
  can_manage: status === "MANUAL_HANDOFF",
});

beforeEach(() => {
  request.mockReset();
  request.mockImplementation(async <T,>(path: string) => {
    const page = Number(new URLSearchParams(path.split("?")[1]).get("page"));
    const items = page === 2 ? [item(3, "FAILED")] : [item(9, "MANUAL_HANDOFF"), item(8, "RESOLVED")];
    return { items, total: 21, page, page_size: 20 } as T;
  });
});
afterEach(() => cleanup());

describe("Case list", () => {
  it("lists the cases newest first with their ward, shift and a link", async () => {
    render(<CaseList />);

    const table = within(await screen.findByRole("table", { name: "Cases" }));
    expect(request).toHaveBeenCalledWith(
      "/cases/search?page=1&page_size=20&sort=newest",
      expect.objectContaining({ demoUser: 900 }),
    );
    expect(table.getByRole("link", { name: "9" }).getAttribute("href")).toBe("/cases/9");
    const cells = within(table.getAllByRole("row")[1]).getAllByRole("cell");
    expect(cells.map((cell) => cell.textContent)).toEqual([
      "9",
      "MANUAL_HANDOFF",
      "Medicine",
      "Shift 21 · NIGHT · 2026-10-09 23:00",
      "1",
      "2026-10-09 21:00:00",
    ]);
    expect(screen.getByText("Page 1 of 2 · 21 in all")).toBeTruthy();
  });

  it("searches on submit, filters by status at once, and goes back to page 1", async () => {
    render(<CaseList />);
    await screen.findByRole("table", { name: "Cases" });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/cases/search?page=2&page_size=20&sort=newest", expect.anything()),
    );
    expect(await screen.findByText("Page 2 of 2 · 21 in all")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText(/^Search/), { target: { value: " medic " } });
    fireEvent.click(screen.getByRole("button", { name: "Find" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "/cases/search?page=1&page_size=20&sort=newest&q=medic",
        expect.anything(),
      ),
    );

    fireEvent.change(screen.getByLabelText(/^Status/), { target: { value: "MANUAL_HANDOFF,FAILED" } });
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "/cases/search?page=1&page_size=20&sort=newest&q=medic&status=MANUAL_HANDOFF%2CFAILED",
        expect.anything(),
      ),
    );
  });

  it("says so when nothing matches", async () => {
    request.mockImplementation(async <T,>() => ({ items: [], total: 0, page: 1, page_size: 20 }) as T);
    render(<CaseList />);

    expect(await screen.findByText("No case matches.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
