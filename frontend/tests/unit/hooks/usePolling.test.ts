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
  await act(async () => {
    await Promise.resolve();
  });
}

describe("usePolling", () => {
  it("aborts a stalled read, retains data and runs the queued refresh", async () => {
    let finishLate!: (value: string) => void;
    const load = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockResolvedValueOnce("initial")
      .mockImplementationOnce(
        () =>
          new Promise<string>((resolve) => {
            finishLate = resolve;
          }),
      )
      .mockResolvedValue("refreshed");
    const { result } = renderHook(() => usePolling(load, { timeoutMs: 500 }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    const signal = load.mock.calls[1][0];
    act(() => result.current.refresh());
    expect(result.current.data).toBe("initial");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(signal.aborted).toBe(true);
    expect(load).toHaveBeenCalledTimes(3);
    expect(result.current.data).toBe("refreshed");
    await act(async () => finishLate("stale"));
    expect(result.current.data).toBe("refreshed");
  });

  it("shows a timeout error and retries", async () => {
    const load = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockImplementationOnce(() => new Promise<string>(() => {}))
      .mockResolvedValue("recovered");
    const { result } = renderHook(() => usePolling(load, { timeoutMs: 500 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.error?.message).toBe(
      "Polling request timed out after 500 ms",
    );
    expect(result.current.isLoading).toBe(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.data).toBe("recovered");
    expect(result.current.error).toBeNull();
  });
  it("refreshes without clearing data or flashing initial loading", async () => {
    let finish!: (value: string) => void;
    const load = vi
      .fn()
      .mockResolvedValueOnce("old")
      .mockImplementation(
        () =>
          new Promise<string>((resolve) => {
            finish = resolve;
          }),
      );
    const { result } = renderHook(() => usePolling(load));
    await flush();
    act(() => result.current.refresh());
    expect(result.current.data).toBe("old");
    expect(result.current.isLoading).toBe(false);
    await act(async () => finish("new"));
    expect(result.current.data).toBe("new");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("coalesces refreshes while a request is pending and cancels on unmount", async () => {
    let finish!: (value: string) => void;
    const load = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          finish = resolve;
        }),
    );
    const { result, unmount } = renderHook(() => usePolling(load));
    act(() => {
      result.current.refresh();
      result.current.refresh();
    });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => finish("first"));
    expect(load).toHaveBeenCalledTimes(2);
    act(() => result.current.refresh());
    unmount();
    await act(async () => finish("late"));
    await vi.advanceTimersByTimeAsync(10000);
    expect(load).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not refresh while disabled", () => {
    const load = vi.fn();
    const { result } = renderHook(() => usePolling(load, { enabled: false }));
    act(() => result.current.refresh());
    expect(load).not.toHaveBeenCalled();
  });
  it("loads immediately and observes the golden-path states every two seconds", async () => {
    const load = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockResolvedValueOnce("WAITING_RESPONSE")
      .mockResolvedValueOnce("WAITING_APPROVAL")
      .mockResolvedValue("RESOLVED");
    const { result } = renderHook(() => usePolling(load));
    expect(result.current.isLoading).toBe(true);
    await flush();
    expect(result.current.data).toBe("WAITING_RESPONSE");
    expect(result.current.isLoading).toBe(false);
    for (const status of ["WAITING_APPROVAL", "RESOLVED"]) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(result.current.data).toBe(status);
    }
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("waits for a slow request to finish before scheduling another", async () => {
    let resolve!: (value: string) => void;
    const load = vi.fn(
      () =>
        new Promise<string>((done) => {
          resolve = done;
        }),
    );
    renderHook(() => usePolling(load, { timeoutMs: 20000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolve("ready");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1999);
    });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("retains successful data on failure and recovers on the next poll", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce("waiting")
      .mockRejectedValueOnce(new Error("Offline"))
      .mockResolvedValue("resolved");
    const { result } = renderHook(() => usePolling(load));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.data).toBe("waiting");
    expect(result.current.error?.message).toBe("Offline");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.data).toBe("resolved");
    expect(result.current.error).toBeNull();
  });

  it("can be enabled, disabled, and restarted with a custom interval", async () => {
    const load = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockResolvedValue("ready");
    const { result, rerender } = renderHook(
      ({ enabled }) => usePolling(load, { enabled, intervalMs: 500 }),
      { initialProps: { enabled: false } },
    );
    expect(load).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    rerender({ enabled: true });
    await flush();
    load.mockImplementationOnce(() => new Promise<string>(() => {}));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(load).toHaveBeenCalledTimes(2);
    const signal = load.mock.calls[1][0];
    rerender({ enabled: false });
    expect(signal.aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(load).toHaveBeenCalledTimes(2);
    rerender({ enabled: true });
    await flush();
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("ignores stale responses when the case loader changes", async () => {
    let resolveOld!: (value: string) => void;
    const oldLoad = vi.fn(
      (signal: AbortSignal) =>
        new Promise<string>((resolve) => {
          resolveOld = resolve;
        }),
    );
    const newLoad = vi.fn().mockResolvedValue("new case");
    const { result, rerender } = renderHook(({ load }) => usePolling(load), {
      initialProps: { load: oldLoad },
    });
    rerender({ load: newLoad });
    await flush();
    expect(oldLoad.mock.calls[0][0].aborted).toBe(true);
    await act(async () => {
      resolveOld("old case");
    });
    expect(result.current.data).toBe("new case");
  });

  it("cancels requests and timers when unmounted", async () => {
    const load = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockResolvedValue("ready");
    const { unmount } = renderHook(() => usePolling(load));
    await flush();
    unmount();
    expect(load.mock.calls[0][0].aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(10000);
    expect(load).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
