// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DemoClock } from "@/components/DemoClock";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DemoClock", () => {
  it("shows the backend clock and that it is frozen", async () => {
    const fetchMock = vi.fn(async (_url: string) =>
      new Response(JSON.stringify({ now: "2026-10-09T23:16:00+07:00", frozen: true })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<DemoClock />);
    const clock = await screen.findByRole("status", { name: "Backend clock" });
    expect(clock.textContent).toContain("2026-10-09 23:16:00");
    expect(clock.textContent).toContain("(demo, frozen)");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/clock$/);
  });

  it("says so when the clock cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500 })));
    render(<DemoClock />);
    expect(await screen.findByText("Clock unavailable")).toBeTruthy();
  });

  it("marks the last clock as outdated while a refresh fails", async () => {
    vi.useFakeTimers();
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        return calls === 1
          ? new Response(JSON.stringify({ now: "2026-10-09T23:16:00+07:00", frozen: true }))
          : new Response("{}", { status: 503 });
      }),
    );
    try {
      render(<DemoClock />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getByRole("status", { name: "Backend clock" }).textContent).not.toContain("outdated");
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      const clock = screen.getByRole("status", { name: "Backend clock" });
      expect(clock.textContent).toContain("2026-10-09 23:16:00");
      expect(clock.textContent).toContain("may be outdated, retrying");
    } finally {
      vi.useRealTimers();
    }
  });
});
