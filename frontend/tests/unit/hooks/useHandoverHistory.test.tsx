// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useHandoverHistory, type HandoverPage } from "@/hooks/useHandoverHistory";
import type { HandoverView } from "@/lib/types/case";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ createDemoApi: () => request }));
const row = (id: number, active = false): HandoverView => ({
  handover_id: id, roster_assignment_id: id, active,
  generated_at: "2026-10-09T21:00:00+07:00", content: {},
});
const page = (ids: number[], cursor: string | null, active = [row(40, true)]): HandoverPage => ({
  active, history: ids.map((id) => row(id)), next_cursor: cursor,
});

beforeEach(() => { vi.useFakeTimers(); request.mockReset(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

it("polls only page one after loading three pages and merges fresh rows without duplicates", async () => {
  let fresh = false;
  request.mockImplementation(async (path: string) => {
    if (path === "/me/handovers") return fresh ? page([40, 30], "second", []) : page([30], "second");
    if (path.endsWith("second")) return page([20], "third");
    if (path.endsWith("third")) return page([10], null);
    throw new Error(path);
  });
  const { result } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  await act(async () => { await result.current.loadMore(); });
  await act(async () => { await result.current.loadMore(); });
  expect(result.current.data?.history.map((r) => r.handover_id)).toEqual([30, 20, 10]);
  request.mockClear();
  fresh = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
  expect(request.mock.calls.map(([path]) => path)).toEqual([
    "/me/handovers", "/me/handovers", "/me/handovers",
  ]);
  expect(result.current.data?.active).toEqual([]);
  expect(result.current.data?.history.map((r) => r.handover_id)).toEqual([40, 30, 20, 10]);
  expect(result.current.data?.next_cursor).toBeNull();
});

it("a failed next page leaves the cursor unchanged; polling does not retry it and a click retries it once", async () => {
  let fail = true;
  request.mockImplementation(async (path: string) => {
    if (path === "/me/handovers") return page([30], "second");
    if (fail) throw new Error("offline");
    return page([20], "third");
  });
  const { result } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  await act(async () => { await result.current.loadMore(); });
  expect(result.current.error?.message).toBe("offline");
  expect(result.current.data?.next_cursor).toBe("second");
  request.mockClear();
  await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
  expect(request.mock.calls.map(([path]) => path)).toEqual(["/me/handovers", "/me/handovers"]);
  // Successful page-one polls do not claim the failed older page was retried.
  expect(result.current.loadMoreError?.message).toBe("offline");
  fail = false;
  await act(async () => { await result.current.loadMore(); });
  expect(request.mock.calls.at(-1)?.[0]).toBe("/me/handovers?cursor=second");
  expect(result.current.data?.history.map((r) => r.handover_id)).toEqual([30, 20]);
  expect(result.current.data?.next_cursor).toBe("third");
  expect(result.current.error).toBeNull();
});

it("validates later pages and retains the list and cursor on a malformed response", async () => {
  request.mockImplementation(async (path: string) => path === "/me/handovers"
    ? page([30], "second") : { active: [], history: null, next_cursor: null });
  const { result } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  await act(async () => { await result.current.loadMore(); });
  expect(result.current.error?.message).toBe("Invalid handover page");
  expect(result.current.data?.history.map((r) => r.handover_id)).toEqual([30]);
  expect(result.current.data?.next_cursor).toBe("second");
});

it("cancels an older page on sign-out", async () => {
  let signal: AbortSignal | undefined;
  request.mockImplementation(async (path: string, options: { signal: AbortSignal }) => {
    if (path === "/me/handovers") return page([30], "second");
    signal = options.signal;
    return new Promise(() => {});
  });
  const { result, unmount } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  act(() => { void result.current.loadMore(); });
  unmount();
  expect(signal?.aborted).toBe(true);
});

it("bounds a hanging older-page read independently while page-one polling continues", async () => {
  request.mockImplementation(async (path: string) => path === "/me/handovers"
    ? page([30], "second") : new Promise(() => {}));
  const { result } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  act(() => { void result.current.loadMore(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(result.current.loadingMore).toBe(false);
  expect(result.current.error?.message).toContain("timed out");
  expect(result.current.data?.next_cursor).toBe("second");
  expect(request.mock.calls.filter(([path]) => path.includes("cursor="))).toHaveLength(1);
  expect(request.mock.calls.filter(([path]) => path === "/me/handovers")).toHaveLength(6);
});

it("does not restore an obsolete active list when a slow older page follows a newer poll", async () => {
  let finish: (value: HandoverPage) => void = () => {};
  let fresh = false;
  request.mockImplementation(async (path: string) => path === "/me/handovers"
    ? page([30], "second", fresh ? [] : [row(40, true)])
    : new Promise<HandoverPage>((resolve) => { finish = resolve; }));
  const { result } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  act(() => { void result.current.loadMore(); });
  fresh = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  await act(async () => { finish(page([20], null)); });
  expect(result.current.data?.active).toEqual([]);
  expect(result.current.data?.history.map((r) => r.handover_id)).toEqual([30, 20]);
});

it("discards cached older history when page one becomes complete after a reset", async () => {
  let reset = false;
  request.mockImplementation(async (path: string) => path === "/me/handovers"
    ? page(reset ? [] : [30], reset ? null : "second", []) : page([20], null, []));
  const { result } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  await act(async () => { await result.current.loadMore(); });
  reset = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(result.current.data).toEqual({ active: [], history: [], next_cursor: null });
});


it("does not turn a deleted active row into history while older pages remain cached", async () => {
  let deleted = false;
  request.mockImplementation(async (path: string) => path === "/me/handovers"
    ? page([30], "second", deleted ? [] : [row(40, true)])
    : page([20], "third"));
  const { result } = renderHook(() => useHandoverHistory(201));
  await act(async () => {});
  await act(async () => { await result.current.loadMore(); });
  deleted = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(result.current.data?.active).toEqual([]);
  expect(result.current.data?.history.map((r) => r.handover_id)).toEqual([30, 20]);
  expect(result.current.data?.next_cursor).toBe("third");
});
