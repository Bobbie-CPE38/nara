import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../src/lib/api";
import { isCaseId, loadCase } from "../../../src/lib/cases";
import { caseDetail, waitingResponseAudit } from "../../fixtures/case";

afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("isCaseId", () => {
  it.each(["1", "42", "9223372036854775807", "9999999999999999999"])("accepts %j", value => {
    expect(isCaseId(value)).toBe(true);
  });

  it.each([
    "", "0", "-1", "+1", "1.5", "01", "abc", "1e3", " 1", "1 ", "1\n", "１",
    "12345678901234567890", "1/../demo", "1?x=1",
  ])("rejects %j", value => {
    expect(isCaseId(value)).toBe(false);
  });
});

describe("loadCase", () => {
  it("reads the case and its audit as public requests with the caller's signal", async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) =>
      json(url.endsWith("/audit") ? waitingResponseAudit() : caseDetail()));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    const snapshot = await loadCase("1", controller.signal);
    expect(snapshot).toEqual({ detail: caseDetail(), audit: waitingResponseAudit() });
    expect(fetchMock.mock.calls.map(([url]) => new URL(url).pathname)).toEqual([
      "/cases/1", "/cases/1/audit",
    ]);
    for (const [, init] of fetchMock.mock.calls) {
      expect(init?.signal).toBe(controller.signal);
      expect(init?.method).toBeUndefined();
      expect(new Headers(init?.headers).has("X-Demo-User")).toBe(false);
    }
  });

  it("requests the audit only after the case has answered", async () => {
    let answerCase!: (response: Response) => void;
    const fetchMock = vi.fn((url: string) => url.endsWith("/audit")
      ? Promise.resolve(json([]))
      : new Promise<Response>(resolve => { answerCase = resolve; }));
    vi.stubGlobal("fetch", fetchMock);

    const pending = loadCase("1", new AbortController().signal);
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    answerCase(json(caseDetail()));
    await pending;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps a 19-digit ID exact in the path", async () => {
    const fetchMock = vi.fn(async (url: string) => json(url.endsWith("/audit") ? [] : caseDetail()));
    vi.stubGlobal("fetch", fetchMock);
    await loadCase("9223372036854775807", new AbortController().signal);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/cases\/9223372036854775807$/);
  });

  it("fails with the API error and skips the audit when the case is missing", async () => {
    const fetchMock = vi.fn(async () => json({ detail: "No case 7" }, 404));
    vi.stubGlobal("fetch", fetchMock);
    const error = await loadCase("7", new AbortController().signal).catch(error => error);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, message: "No case 7" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each(["abc", "0", "1/../demo"])("rejects the ID %j before sending a request", async caseId => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(loadCase(caseId, new AbortController().signal)).rejects.toThrow("Invalid case ID");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["an empty body", undefined, []],
    ["text instead of JSON", "<html></html>", []],
    ["a list as the case", [], []],
    ["a case without a status", { ...caseDetail(), status: undefined }, []],
    ["a case without candidates", { ...caseDetail(), candidates: undefined }, []],
    ["a null candidate", { ...caseDetail(), candidates: [null] }, []],
    ["a gap without its lists", { ...caseDetail(), gap: { id: 1, headcount_gap: 1 } }, []],
    ["a missing gap key", { ...caseDetail(), gap: undefined }, []],
    ["a wrapped audit list", caseDetail(), { items: [] }],
    ["a null audit row", caseDetail(), [null]],
    ["an audit row without a payload", caseDetail(), [{ id: 1, action: "CASE_OPENED" }]],
    ["an audit row with a list payload", caseDetail(), [{ id: 1, action: "CASE_OPENED", payload: [] }]],
  ])("rejects %s", async (_name, detail, audit) => {
    const body = (value: unknown) =>
      new Response(typeof value === "string" ? value : JSON.stringify(value));
    vi.stubGlobal("fetch", vi.fn(async (url: string) => body(url.endsWith("/audit") ? audit : detail)));
    await expect(loadCase("1", new AbortController().signal)).rejects.toThrow(
      "Unexpected response from the API",
    );
  });

  it("accepts a case that has no gap, candidates or audit rows yet", async () => {
    const early = caseDetail({ status: "OPEN", gap: null, candidates: [] });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => json(url.endsWith("/audit") ? [] : early)));
    expect(await loadCase("1", new AbortController().signal)).toEqual({ detail: early, audit: [] });
  });
});
