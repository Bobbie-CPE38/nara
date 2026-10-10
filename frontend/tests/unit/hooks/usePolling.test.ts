// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "../../../src/hooks/usePolling";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function flush() {
  await act(async () => { await Promise.resolve(); });
}

describe("usePolling", () => {
  it("loads immediately and observes the golden-path states every two seconds", async () => {
    const load = vi.fn<(signal: AbortSignal) => Promise<string>>()
      .mockResolvedValueOnce("WAITING_RESPONSE")
      .mockResolvedValueOnce("WAITING_APPROVAL")
      .mockResolvedValue("RESOLVED");
    const { result } = renderHook(() => usePolling(load));
    expect(result.current.isLoading).toBe(true);
    await flush();
    expect(result.current.data).toBe("WAITING_RESPONSE");
    expect(result.current.isLoading).toBe(false);
    for (const status of ["WAITING_APPROVAL", "RESOLVED"]) {
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      expect(result.current.data).toBe(status);
    }
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("waits for a slow request to finish before scheduling another", async () => {
    let resolve!: (value: string) => void;
    const load = vi.fn(() => new Promise<string>(done => { resolve = done; }));
    renderHook(() => usePolling(load));
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => { resolve("ready"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1999); });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("retains successful data on failure and recovers on the next poll", async () => {
    const load = vi.fn().mockResolvedValueOnce("waiting")
      .mockRejectedValueOnce(new Error("Offline"))
      .mockResolvedValue("resolved");
    const { result } = renderHook(() => usePolling(load));
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.data).toBe("waiting");
    expect(result.current.error?.message).toBe("Offline");
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.data).toBe("resolved");
    expect(result.current.error).toBeNull();
  });

  it("can be enabled, disabled, and restarted with a custom interval", async () => {
    const load = vi.fn<(signal: AbortSignal) => Promise<string>>().mockResolvedValue("ready");
    const { result, rerender } = renderHook(
      ({ enabled }) => usePolling(load, { enabled, intervalMs: 500 }),
      { initialProps: { enabled: false } },
    );
    expect(load).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    rerender({ enabled: true });
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(load).toHaveBeenCalledTimes(2);
    const signal = load.mock.calls[0][0];
    rerender({ enabled: false });
    expect(signal.aborted).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(load).toHaveBeenCalledTimes(2);
    rerender({ enabled: true });
    await flush();
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("ignores stale responses when the case loader changes", async () => {
    let resolveOld!: (value: string) => void;
    const oldLoad = vi.fn((signal: AbortSignal) => new Promise<string>(resolve => {
      resolveOld = resolve;
    }));
    const newLoad = vi.fn().mockResolvedValue("new case");
    const { result, rerender } = renderHook(({ load }) => usePolling(load), {
      initialProps: { load: oldLoad },
    });
    rerender({ load: newLoad });
    await flush();
    expect(oldLoad.mock.calls[0][0].aborted).toBe(true);
    await act(async () => { resolveOld("old case"); });
    expect(result.current.data).toBe("new case");
  });

  it("stops after a result that stopOnData accepts and keeps the data", async () => {
    const load = vi.fn<(signal: AbortSignal) => Promise<string>>()
      .mockResolvedValueOnce("WAITING_APPROVAL")
      .mockResolvedValue("RESOLVED");
    // An inline callback is a new function on every render and must not restart polling.
    const { result } = renderHook(() => usePolling(load, {
      stopOnData: status => status === "RESOLVED",
    }));
    await flush();
    expect(vi.getTimerCount()).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.data).toBe("RESOLVED");
    expect(vi.getTimerCount()).toBe(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(load).toHaveBeenCalledTimes(2);
    expect(result.current).toMatchObject({ data: "RESOLVED", error: null, isLoading: false });
  });

  it("stops after an error that stopOnError accepts and retries the others", async () => {
    const gone = new Error("Gone");
    const load = vi.fn().mockResolvedValueOnce("waiting")
      .mockRejectedValueOnce(new Error("Offline"))
      .mockRejectedValueOnce(gone)
      .mockResolvedValue("back");
    const { result } = renderHook(() => usePolling(load, { stopOnError: error => error === gone }));
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.error?.message).toBe("Offline");
    expect(vi.getTimerCount()).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current).toMatchObject({ data: "waiting", error: gone, isLoading: false });
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(load).toHaveBeenCalledTimes(3);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops on the first load when it already is final or gone", async () => {
    const final = vi.fn<(signal: AbortSignal) => Promise<string>>().mockResolvedValue("RESOLVED");
    const first = renderHook(() => usePolling(final, { stopOnData: () => true }));
    await flush();
    expect(first.result.current).toMatchObject({ data: "RESOLVED", isLoading: false });

    const missing = vi.fn().mockRejectedValue(new Error("Not found"));
    const second = renderHook(() => usePolling(missing, { stopOnError: () => true }));
    await flush();
    expect(second.result.current).toMatchObject({ data: undefined, isLoading: false });
    expect(second.result.current.error?.message).toBe("Not found");

    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(final).toHaveBeenCalledTimes(1);
    expect(missing).toHaveBeenCalledTimes(1);
  });

  it("polls again when the loader changes after a stop", async () => {
    const stopOnData = (status: string) => status === "RESOLVED";
    const first = vi.fn<(signal: AbortSignal) => Promise<string>>().mockResolvedValue("RESOLVED");
    const second = vi.fn<(signal: AbortSignal) => Promise<string>>().mockResolvedValue("WAITING_RESPONSE");
    const { result, rerender } = renderHook(({ load }) => usePolling(load, { stopOnData }), {
      initialProps: { load: first },
    });
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(first).toHaveBeenCalledTimes(1);
    rerender({ load: second });
    expect(result.current.data).toBeUndefined();
    await flush();
    expect(result.current.data).toBe("WAITING_RESPONSE");
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(second).toHaveBeenCalledTimes(2);
  });

  it("uses the newest stop callback without restarting", async () => {
    const load = vi.fn<(signal: AbortSignal) => Promise<string>>().mockResolvedValue("ready");
    const { rerender } = renderHook(({ stop }) => usePolling(load, { stopOnData: () => stop }), {
      initialProps: { stop: false },
    });
    await flush();
    rerender({ stop: true });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("cancels requests and timers when unmounted", async () => {
    const load = vi.fn<(signal: AbortSignal) => Promise<string>>().mockResolvedValue("ready");
    const { unmount } = renderHook(() => usePolling(load));
    await flush();
    unmount();
    expect(load.mock.calls[0][0].aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(10000);
    expect(load).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
