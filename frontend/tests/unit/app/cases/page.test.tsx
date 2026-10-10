// @vitest-environment jsdom

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CasePage from "../../../../src/app/cases/[id]/page";
import { caseDetail } from "../../../fixtures/case";

const fetchMock = vi.fn(async (url: string) =>
  new Response(JSON.stringify(url.endsWith("/audit") ? [] : caseDetail({ id: 7 }))));

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("cases/[id] page", () => {
  it("awaits the route params and shows that case", async () => {
    render(await CasePage({ params: Promise.resolve({ id: "7" }) }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Case 7");
    expect(fetchMock.mock.calls.map(([url]) => new URL(url).pathname)).toEqual([
      "/cases/7", "/cases/7/audit",
    ]);
    expect(screen.getByText("Status:").textContent).toContain("WAITING_RESPONSE");
  });

  it("passes a bad route segment through to the invalid ID message", async () => {
    render(await CasePage({ params: Promise.resolve({ id: "abc" }) }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText("Invalid case ID.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
