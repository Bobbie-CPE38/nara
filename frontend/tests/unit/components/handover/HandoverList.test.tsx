// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HandoverList } from "@/components/handover/HandoverList";
import type { HandoverView } from "@/lib/types/case";

afterEach(() => cleanup());

function handover(id: number, active: boolean, shiftId: number): HandoverView {
  return {
    handover_id: id,
    roster_assignment_id: 10 + id,
    active,
    generated_at: "2026-10-09T21:05:00+07:00",
    content: {
      version: 1,
      shift: { id: shiftId, ward_id: 1, ward_name: "ICU", start_at: "2026-10-09T23:00:00+07:00", end_at: "2026-10-10T07:00:00+07:00" },
      cover_start_at: "2026-10-09T23:00:00+07:00",
      cover_end_at: "2026-10-10T07:00:00+07:00",
      reason: "NO_SHOW",
      patient_count: 8,
      requirement: { roles: [], skills: [] },
      co_workers: [{ staff_id: 101, name: "Anong", role_name: "RN" }],
      case_id: 7,
    },
  };
}

describe("HandoverList", () => {
  it("lists active handovers before history and shows the snapshot", () => {
    render(<HandoverList handovers={[handover(1, false, 1), handover(2, true, 2)]} emptyText="none" linkCase />);
    const items = screen.getAllByRole("listitem");
    expect(items[0].textContent).toContain("Shift 2 (ICU)");
    expect(items[1].textContent).toContain("history, no longer active");
    expect(items[0].textContent).toContain("No-show");
    expect(items[0].textContent).toContain("Anong (RN)");
    expect(screen.getAllByRole("link", { name: "7" })).toHaveLength(2);
  });

  it("shows the empty text and skips items that are not handovers", () => {
    render(<HandoverList handovers={[{ id: 1, status: "SENT" }]} emptyText="You have no handovers." />);
    expect(screen.getByText("You have no handovers.")).toBeTruthy();
  });

  it("keeps the known keys when a field is missing", () => {
    const row = handover(3, true, 1);
    row.content = { version: 2, shift: { id: 1 } };
    render(<HandoverList handovers={[row]} emptyText="none" />);
    expect(screen.getByRole("listitem").textContent).toContain("Shift 1 (—)");
    expect(screen.queryByRole("link")).toBeNull();
  });
});
