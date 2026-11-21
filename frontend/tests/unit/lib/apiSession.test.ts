// The API layer in session mode (round 6 PR AU3, docs/workflow.md 6.33.3)
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiRequest,
  authCode,
  createDemoApi,
  setAuthProblemHandler,
  setSessionMode,
} from "@/lib/api";
import { describeError } from "@/lib/errors";
import { translator } from "@/lib/i18n";

const fetchMock = vi.fn();

function answer(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce(new Response(body === undefined ? null : JSON.stringify(body), { status }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  setSessionMode(false);
  setAuthProblemHandler(null);
  vi.unstubAllGlobals();
});

describe("demo mode (the default)", () => {
  it("sends X-Demo-User and no credentials, as before the login", async () => {
    answer(200, []);
    await createDemoApi(105)("/me/offers");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("X-Demo-User")).toBe("105");
    expect(init.credentials).toBeUndefined();
  });
});

describe("session mode", () => {
  beforeEach(() => setSessionMode(true));

  it("sends the cookie and never X-Demo-User", async () => {
    answer(200, []);
    await createDemoApi(105)("/me/offers");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).has("X-Demo-User")).toBe(false);
    expect(init.credentials).toBe("include");
  });

  it("tells the handler to log in again on 401 AUTH_REQUIRED, and still throws", async () => {
    const handler = vi.fn();
    setAuthProblemHandler(handler);
    answer(401, { detail: "AUTH_REQUIRED" });
    await expect(apiRequest("/cases")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledWith("login");
  });

  it("tells the handler to change the password on 403 AUTH_PASSWORD_CHANGE_REQUIRED", async () => {
    const handler = vi.fn();
    setAuthProblemHandler(handler);
    answer(403, { detail: "AUTH_PASSWORD_CHANGE_REQUIRED" });
    await expect(apiRequest("/cases")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledWith("change-password");
  });

  it("does not treat a wrong password, a 403 of rights or a 404 as a lost session", async () => {
    const handler = vi.fn();
    setAuthProblemHandler(handler);
    answer(401, { detail: "AUTH_INVALID_CREDENTIALS" });
    await expect(apiRequest("/auth/login", { method: "POST", json: {} })).rejects.toBeInstanceOf(ApiError);
    answer(403, { detail: "AUTH_FORBIDDEN" });
    await expect(apiRequest("/cases/1")).rejects.toBeInstanceOf(ApiError);
    answer(404, { detail: "Case not found" });
    await expect(apiRequest("/cases/2")).rejects.toBeInstanceOf(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("demo mode ignores the auth codes", () => {
  it("does not call the handler on a 401 in demo mode", async () => {
    const handler = vi.fn();
    setAuthProblemHandler(handler);
    answer(401, { detail: "AUTH_REQUIRED" });
    await expect(apiRequest("/cases")).rejects.toBeInstanceOf(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("auth error codes in words", () => {
  const codes = [
    "AUTH_REQUIRED",
    "AUTH_FORBIDDEN",
    "AUTH_INVALID_CREDENTIALS",
    "AUTH_INVALID_PASSWORD",
    "AUTH_INVALID_REGISTRATION",
    "AUTH_RATE_LIMITED",
    "AUTH_ORIGIN_FORBIDDEN",
    "AUTH_PASSWORD_CHANGE_REQUIRED",
  ];

  it("reads the code of an API error, and only an AUTH_ one", () => {
    expect(authCode(new ApiError(401, { detail: "AUTH_REQUIRED" }))).toBe("AUTH_REQUIRED");
    expect(authCode(new ApiError(404, { detail: "Case not found" }))).toBeUndefined();
    expect(authCode(new Error("AUTH_REQUIRED"))).toBeUndefined();
  });

  it.each(codes)("%s is a sentence in both languages, never the code", (code) => {
    const error = new ApiError(400, { detail: code });
    const en = describeError(error, translator("en"));
    const th = describeError(error, translator("th"));
    expect(en).not.toContain("AUTH_");
    expect(th).not.toContain("AUTH_");
    expect(th).not.toBe(en);
    expect(th).toMatch(/[ก-๙]/);
  });

  it("leaves the sentence of any other API error as the API sent it", () => {
    expect(describeError(new ApiError(404, { detail: "Case not found" }), translator("th"))).toBe("Case not found");
  });
});
