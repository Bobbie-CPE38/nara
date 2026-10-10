import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, createDemoApi } from "../../../src/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("sends the golden-path actions with the correct actors and JSON", async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({ status: "ok" })),
    );
    vi.stubGlobal("fetch", fetchMock);
    const actions = [
      { staff: 105, path: "/events", json: { event_type: "STAFF_UNAVAILABLE", shift_id: 1 } },
      { staff: 201, path: "/demo/line-sim/respond", json: { outreach_id: 1, response: "ACCEPT" } },
      { staff: 900, path: "/approvals/1/decision", json: { approved: true } },
    ];
    for (const action of actions) {
      expect(await createDemoApi(action.staff)(action.path, {
        method: "POST", json: action.json, headers: { "X-Request-ID": "demo" },
      })).toEqual({ status: "ok" });
      const [url, request] = fetchMock.mock.calls.at(-1)!;
      expect(url).toContain(action.path);
      expect(request.method).toBe("POST");
      expect(request.headers.get("X-Demo-User")).toBe(String(action.staff));
      expect(request.headers.get("Content-Type")).toBe("application/json");
      expect(request.headers.get("X-Request-ID")).toBe("demo");
      expect(JSON.parse(request.body)).toEqual(action.json);
    }
  });

  it("supports public reads and forwards cancellation without caching", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    await apiRequest("/health", { signal: controller.signal });
    const request = fetchMock.mock.calls[0][1];
    expect(request.headers.has("X-Demo-User")).toBe(false);
    expect(request.signal).toBe(controller.signal);
    expect(request.cache).toBe("no-store");
    expect(request.body).toBeUndefined();
  });

  it("reports backend errors with status and details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response('{"detail":"Not authorized"}', { status: 401 }),
    ));
    const error = await apiRequest("/approvals").catch(error => error);
    expect(error).toBeInstanceOf(ApiError);
    if (!(error instanceof ApiError)) throw new Error("Expected an ApiError");
    expect(error.status).toBe(401);
    expect(error.message).toBe("Not authorized");
    expect(error.body).toEqual({ detail: "Not authorized" });
  });

  it("handles empty responses and non-JSON error responses", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response("Service unavailable", { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await apiRequest("/demo/reset", { method: "POST" })).toBeUndefined();
    await expect(apiRequest("/health")).rejects.toMatchObject({
      status: 503, message: "Service unavailable",
    });
  });

  it("rejects invalid identities and external paths before sending a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const demoUser of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
      await expect(apiRequest("/events", { demoUser })).rejects.toThrow("staff ID");
    }
    for (const path of ["events", "//example.com", "https://example.com"]) {
      await expect(apiRequest(path)).rejects.toThrow("single slash");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
