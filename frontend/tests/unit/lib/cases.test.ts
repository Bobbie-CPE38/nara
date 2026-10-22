import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../src/lib/api";
import { collectSkips, explanationRequestKey, isCaseId, loadCase } from "../../../src/lib/cases";
import type { CaseDetail } from "../../../src/lib/types/case";
import { auditEntry, caseDetail, waitingResponseAudit } from "../../fixtures/case";

afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

/** A case whose first candidate carries the given raw score. */
const withScore = (score: unknown) =>
  ({ ...caseDetail(), candidates: [{ ...caseDetail().candidates[0], score }] });

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
    ["a candidate without a score", withScore(undefined), []],
    ["a candidate with a string score", withScore("1005"), []],
    ["a candidate with a score without terms", withScore({ total: 1005, first_wave: true }), []],
    ["a candidate with score terms that are not records", withScore({ total: 1005, first_wave: true, terms: [1] }), []],
    ["a score term with an object name", withScore({ total: 1005, first_wave: true, terms: [{ name: {}, value: 1, weight: 1, points: 1 }] }), []],
    ["a score term without a name", withScore({ total: 1005, first_wave: true, terms: [{ value: 1, weight: 1, points: 1 }] }), []],
    ["a score term with a string value", withScore({ total: 1005, first_wave: true, terms: [{ name: "t", value: "1", weight: 1, points: 1 }] }), []],
    ["a score term with a null weight", withScore({ total: 1005, first_wave: true, terms: [{ name: "t", value: 1, weight: null, points: 1 }] }), []],
    ["a score term without points", withScore({ total: 1005, first_wave: true, terms: [{ name: "t", value: 1, weight: 1 }] }), []],
    ["a candidate with a string score total", withScore({ total: "1005", first_wave: true, terms: [] }), []],
    ["a missing summary key", { ...caseDetail(), summary: undefined }, []],
    ["a malformed summary", { ...caseDetail(), summary: { current: {}, history: [] } }, []],
    ["a non-record summary", { ...caseDetail(), summary: "READY" }, []],
    ["a missing explanation key", { ...caseDetail(), explanation: undefined }, []],
    ["an explanation with an unknown status", { ...caseDetail(), explanation: { status: "DONE", text: null, provider: null, model_id: null, can_request: false, request_blocked_reason: null } }, []],
    ["a READY explanation without text", { ...caseDetail(), explanation: { status: "READY", text: null, provider: "fake", model_id: null, can_request: false, request_blocked_reason: null } }, []],
    ["a READY explanation with an empty text", { ...caseDetail(), explanation: { status: "READY", text: "", provider: "fake", model_id: null, can_request: false, request_blocked_reason: null } }, []],
    ["a READY explanation with an unknown provider", { ...caseDetail(), explanation: { status: "READY", text: "x", provider: "other", model_id: null, can_request: false, request_blocked_reason: null } }, []],
    ["an explanation without can_request", { ...caseDetail(), explanation: { status: "NOT_REQUESTED", text: null, provider: null, model_id: null, request_blocked_reason: null } }, []],
    ["an explanation with a string can_request", { ...caseDetail(), explanation: { status: "NOT_REQUESTED", text: null, provider: null, model_id: null, can_request: "true", request_blocked_reason: null } }, []],
    ["an explanation without request_blocked_reason", { ...caseDetail(), explanation: { status: "NOT_REQUESTED", text: null, provider: null, model_id: null, can_request: true } }, []],
    ["an explanation with an unknown blocked reason", { ...caseDetail(), explanation: { status: "NOT_REQUESTED", text: null, provider: null, model_id: null, can_request: false, request_blocked_reason: "TOMORROW" } }, []],
    ["a string explanation", { ...caseDetail(), explanation: "READY" }, []],
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

  it("accepts a score term with a name it does not know", async () => {
    const terms = [{ name: "A_TERM_ADDED_LATER", value: 1, weight: 1, points: 1 }];
    const detail = withScore({ total: 1005, first_wave: true, terms });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => json(url.endsWith("/audit") ? [] : detail)));
    expect(await loadCase("1", new AbortController().signal)).toEqual({ detail, audit: [] });
  });

  it("accepts a candidate whose score is null", async () => {
    const detail = caseDetail({ candidates: [{ ...caseDetail().candidates[0], score: null }] });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => json(url.endsWith("/audit") ? [] : detail)));
    expect(await loadCase("1", new AbortController().signal)).toEqual({ detail, audit: [] });
  });

  it.each([
    ["null", null],
    ["PENDING", { status: "PENDING", text: null, provider: null, model_id: null, can_request: false, request_blocked_reason: "PENDING" }],
    ["UNAVAILABLE", { status: "UNAVAILABLE", text: null, provider: null, model_id: null, can_request: true, request_blocked_reason: null }],
    ["NOT_REQUESTED (PR E1)", { status: "NOT_REQUESTED", text: null, provider: null, model_id: null, can_request: true, request_blocked_reason: null }],
    ["QUOTA_EXHAUSTED (PR E1)", { status: "QUOTA_EXHAUSTED", text: null, provider: null, model_id: null, can_request: false, request_blocked_reason: "QUOTA_EXHAUSTED" }],
    ["READY from fake", { status: "READY", text: "[fake] x", provider: "fake", model_id: null, can_request: false, request_blocked_reason: "ALREADY_READY" }],
    ["READY from lambda (PR B3)", { status: "READY", text: "x", provider: "lambda", model_id: "m-1", can_request: false, request_blocked_reason: "ALREADY_READY" }],
    ["READY from bedrock", { status: "READY", text: "x", provider: "bedrock", model_id: "m-1", can_request: false, request_blocked_reason: "ALREADY_READY" }],
  ])("accepts an explanation that is %s", async (_name, explanation) => {
    const detail = caseDetail({ explanation } as Partial<CaseDetail>);
    vi.stubGlobal("fetch", vi.fn(async (url: string) => json(url.endsWith("/audit") ? [] : detail)));
    expect(await loadCase("1", new AbortController().signal)).toEqual({ detail, audit: [] });
  });

  it("accepts a case that has no gap, candidates or audit rows yet", async () => {
    const early = caseDetail({ status: "OPEN", gap: null, candidates: [] });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => json(url.endsWith("/audit") ? [] : early)));
    expect(await loadCase("1", new AbortController().signal)).toEqual({ detail: early, audit: [] });
  });
});

describe("collectSkips", () => {
  const skip = (staff_id: number, reason: string) => ({ staff_id, reason });

  it("keeps the audit order across entries", () => {
    expect(collectSkips([
      auditEntry(1, "OFFER_SENT", { payload: { wave: 1, skipped: [skip(202, "UNAVAILABLE")] } }),
      auditEntry(2, "OFFER_SENT", { payload: { wave: 1 } }),
      auditEntry(3, "OFFER_SENT", { payload: { wave: 2, skipped: [skip(203, "SHIFT_CONFLICT"), skip(204, "ROLE_MISMATCH")] } }),
      auditEntry(4, "MANUAL_HANDOFF", { payload: { skipped: [skip(205, "OFFER_LIMIT_REACHED")] } }),
    ])).toEqual([
      { key: "1-0", origin: "Wave 1", staffId: 202, reason: "UNAVAILABLE" },
      { key: "3-0", origin: "Wave 2", staffId: 203, reason: "SHIFT_CONFLICT" },
      { key: "3-1", origin: "Wave 2", staffId: 204, reason: "ROLE_MISMATCH" },
      { key: "4-0", origin: "Handoff", staffId: 205, reason: "OFFER_LIMIT_REACHED" },
    ]);
  });

  it("names an offer without a numeric wave just Wave", () => {
    expect(collectSkips([
      auditEntry(1, "OFFER_SENT", { payload: { wave: "2", skipped: [skip(202, "UNAVAILABLE")] } }),
    ])[0].origin).toBe("Wave");
  });

  it("ignores skipped lists on other actions", () => {
    expect(collectSkips([
      auditEntry(1, "SOLVER_EXECUTED", { payload: { skipped: [skip(202, "UNAVAILABLE")] } }),
    ])).toEqual([]);
  });

  it("ignores a skipped value that is not a list and malformed elements", () => {
    expect(collectSkips([
      auditEntry(1, "OFFER_SENT", { payload: { skipped: "UNAVAILABLE" } }),
      auditEntry(2, "OFFER_SENT", {
        payload: { skipped: [null, 5, [], { staff_id: "202", reason: "X" }, { staff_id: 202 }, skip(203, "UNAVAILABLE")] },
      }),
    ])).toEqual([{ key: "2-5", origin: "Wave", staffId: 203, reason: "UNAVAILABLE" }]);
  });

  it("returns nothing for an empty audit", () => {
    expect(collectSkips([])).toEqual([]);
  });
});

describe("explanationRequestKey", () => {
  const refused = (status: number, code: string) =>
    new ApiError(status, { detail: { code, message: "words from the server" } });

  it.each([
    [429, "LLM_QUOTA_EXHAUSTED", "ai.blockedQuota"],
    [409, "LLM_ATTEMPTS_EXHAUSTED", "ai.blockedAttempts"],
    [409, "LLM_UNAVAILABLE", "ai.refused"],
    [404, "CASE_NOT_FOUND", "ai.notFound"],
  ])("maps %s %s to the text %s, never to the words of the server", (status, code, key) => {
    expect(explanationRequestKey(refused(status, code))).toBe(key);
  });

  it.each([
    ["an unknown code", refused(500, "SOMETHING")],
    ["an error without a body", new ApiError(502, undefined)],
    ["a network error", new TypeError("Failed to fetch")],
  ])("uses the general text for %s", (_name, error) => {
    expect(explanationRequestKey(error)).toBe("ai.requestFailed");
  });
});
