// @vitest-environment jsdom

import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CaseView } from "../../../../src/components/case/CaseView";
import {
  auditEntry,
  caseDetail,
  DEMO_TIME,
  resolvedAudit,
  statusChange,
  waitingApprovalAudit,
  waitingResponseAudit,
} from "../../../fixtures/case";

type Reply = () => Response | Promise<Response>;

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

// The fake backend. A test swaps what the two routes answer between polls.
let backend: { detail: Reply; audit: Reply };
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  // Like the real fetch, it sends nothing for a request that is already aborted.
  if (init?.signal?.aborted) throw new DOMException("The operation was aborted.", "AbortError");
  return url.endsWith("/audit") ? backend.audit() : backend.detail();
});

function serve(detail: unknown, audit: unknown) {
  backend = { detail: () => json(detail), audit: () => json(audit) };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", fetchMock);
  serve(caseDetail(), waitingResponseAudit());
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function tick(ms = 0) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

function requests() {
  return fetchMock.mock.calls.map(([url]) => new URL(url).pathname);
}

function status() {
  return screen.getByText("Status:").querySelector("strong")?.textContent;
}

/** Body rows of a table as lists of cell texts. */
function rows(table: string) {
  return within(screen.getByRole("table", { name: table })).getAllByRole("row").slice(1)
    .map(row => within(row).getAllByRole("cell").map(cell => cell.textContent));
}

function actions() {
  return rows("Timeline").map(cells => cells[2]);
}

describe("CaseView", () => {
  it("loads the case, then its audit, and shows status, gap, ranked candidates and timeline", async () => {
    render(<CaseView caseId="1" />);
    expect(screen.getByRole("status").textContent).toBe("Loading…");
    await tick();

    expect(requests()).toEqual(["/cases/1", "/cases/1/audit"]);
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init?.headers).has("X-Demo-User")).toBe(false);
    }
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Case 1");
    expect(status()).toBe("WAITING_RESPONSE");
    expect(screen.getByText("Waiting for the candidate to reply")).toBeTruthy();
    expect(screen.getByText("Updating every 2 seconds.")).toBeTruthy();
    expect(screen.getByText("Headcount:").textContent).toContain("Short by 1");
    expect(rows("Gap")).toEqual([
      ["Role", "RN", "5", "4", "Short by 1"],
      ["Skill", "ICU", "2", "2", "OK"],
    ]);
    expect(rows("Candidates")).toEqual([
      ["1", "201", "Arunee Demo", "SAME_WARD", "SENT"],
      ["2", "202", "Phanu Demo", "SAME_WARD", "Not contacted"],
      ["3", "203", "Chonthicha Demo", "SAME_WARD", "Not contacted"],
    ]);
    expect(actions()).toEqual(waitingResponseAudit().map(entry => entry.action));
  });

  it("follows the golden path every two seconds and stops at RESOLVED", async () => {
    render(<CaseView caseId="1" />);
    await tick();
    expect(status()).toBe("WAITING_RESPONSE");

    serve(caseDetail({ status: "WAITING_APPROVAL" }), waitingApprovalAudit());
    await tick(1999);
    expect(status()).toBe("WAITING_RESPONSE");
    await tick(1);
    expect(status()).toBe("WAITING_APPROVAL");
    expect(actions()).toHaveLength(15);

    serve(caseDetail({ status: "RESOLVED" }), resolvedAudit());
    await tick(2000);
    expect(status()).toBe("RESOLVED");
    expect(actions().slice(-2)).toEqual(["CASE_RESOLVED", "CASE_STATUS_CHANGED"]);
    expect(screen.getByText("Final status. Updates stopped.")).toBeTruthy();

    await tick(10000);
    expect(fetchMock).toHaveBeenCalledTimes(6);
    expect(vi.getTimerCount()).toBe(0);
    expect(status()).toBe("RESOLVED");
  });

  it.each(["UNRESOLVED", "FAILED"])("stops polling on the final status %s", async final => {
    serve(caseDetail({ status: final }), []);
    render(<CaseView caseId="1" />);
    await tick();
    await tick(10000);
    expect(status()).toBe(final);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each(["WAITING_APPROVAL", "MANUAL_HANDOFF", "A_STATUS_ADDED_LATER"])(
    "keeps polling on %s, which is not final", async open => {
      serve(caseDetail({ status: open }), []);
      render(<CaseView caseId="1" />);
      await tick();
      await tick(4000);
      expect(status()).toBe(open);
      expect(fetchMock).toHaveBeenCalledTimes(6);
    },
  );

  it("shows the last audit rows when the final status commits while the case is being read", async () => {
    render(<CaseView caseId="1" />);
    await tick();
    // The audit list only grows once the case answer is on its way. A request
    // sent together with the case request would still get the short list.
    backend.detail = async () => {
      await Promise.resolve();
      backend.audit = () => json(resolvedAudit());
      return json(caseDetail({ status: "RESOLVED" }));
    };
    await tick(2000);
    expect(status()).toBe("RESOLVED");
    expect(actions()).toEqual(resolvedAudit().map(entry => entry.action));
    await tick(10000);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("keeps polling when the audit read fails next to a final status", async () => {
    backend = {
      detail: () => json(caseDetail({ status: "RESOLVED" })),
      audit: () => json({ detail: "Internal Server Error" }, 500),
    };
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByRole("alert").textContent).toContain("Retrying…");
    serve(caseDetail({ status: "RESOLVED" }), resolvedAudit());
    await tick(2000);
    expect(status()).toBe("RESOLVED");
    expect(actions()).toHaveLength(20);
  });

  it("shows a case that failed before the gap and the candidates were stored", async () => {
    serve(caseDetail({ status: "FAILED", gap: null, candidates: [] }), [
      auditEntry(1, "CASE_OPENED"),
      statusChange(2, "OPEN", "ASSESSING"),
      statusChange(3, "ASSESSING", "FAILED"),
      auditEntry(4, "WORKFLOW_FAILED", {
        payload: { from: "ASSESSING", failed_at: "ASSESSING", error_type: "NoGapError" },
      }),
    ]);
    render(<CaseView caseId="1" />);
    await tick();
    expect(status()).toBe("FAILED");
    expect(screen.getByText("Failed at ASSESSING: NoGapError")).toBeTruthy();
    expect(screen.getByText("Not assessed yet.")).toBeTruthy();
    expect(screen.getByText("No candidates yet.")).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Gap" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Candidates" })).toBeNull();
  });

  it("shows FAILED without a reason when the audit has no WORKFLOW_FAILED row", async () => {
    serve(caseDetail({ status: "FAILED" }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(status()).toBe("FAILED");
    expect(screen.queryByText(/^Failed at/)).toBeNull();
    expect(screen.getByText("No audit entries yet.")).toBeTruthy();
  });

  it("reports a role or skill shortage on its own when the headcount is enough", async () => {
    serve(caseDetail({
      gap: {
        id: 1, headcount_gap: 0, computed_at: DEMO_TIME,
        roles: [{ id: 1, name: "RN", required_count: 5, current_count: 5, gap_count: 0 }],
        skills: [{ id: 1, name: "ICU", required_count: 2, current_count: 1, gap_count: 1 }],
      },
    }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText("Headcount:").textContent).toBe("Headcount: OKComputed 2026-10-09 21:00:00");
    expect(rows("Gap")).toEqual([
      ["Role", "RN", "5", "5", "OK"],
      ["Skill", "ICU", "2", "1", "Short by 1"],
    ]);
  });

  it("never adds the headcount, role and skill gaps together", async () => {
    serve(caseDetail({
      gap: {
        id: 1, headcount_gap: 1, computed_at: DEMO_TIME,
        roles: [{ id: 1, name: "RN", required_count: 5, current_count: 4, gap_count: 1 }],
        skills: [{ id: 1, name: "ICU", required_count: 2, current_count: 1, gap_count: 1 }],
      },
    }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(document.body.textContent?.match(/Short by \d+/g)).toEqual([
      "Short by 1", "Short by 1", "Short by 1",
    ]);
  });

  it("handles a gap without skills and a gap without any requirement rows", async () => {
    const gap = caseDetail().gap!;
    serve(caseDetail({ gap: { ...gap, skills: [] } }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(rows("Gap")).toEqual([["Role", "RN", "5", "4", "Short by 1"]]);

    serve(caseDetail({ gap: { ...gap, roles: [], skills: [] } }), []);
    await tick(2000);
    expect(screen.getByText("No role or skill requirements.")).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Gap" })).toBeNull();
    expect(screen.getByText("Headcount:").textContent).toContain("Short by 1");
  });

  it("says the case is missing and stops polling on a 404", async () => {
    backend.detail = () => json({ detail: "No case 1" }, 404);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText("Case 1 not found.")).toBeTruthy();
    await tick(10000);
    expect(requests()).toEqual(["/cases/1"]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("drops the case from the screen when it is gone after a demo reset", async () => {
    render(<CaseView caseId="1" />);
    await tick();
    expect(status()).toBe("WAITING_RESPONSE");

    backend.detail = () => json({ detail: "No case 1" }, 404);
    await tick(2000);
    expect(screen.getByText("Case 1 not found.")).toBeTruthy();
    expect(screen.queryByText("Status:")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    await tick(10000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shows only the new rows when the same ID is a different case after a reset", async () => {
    serve(caseDetail({ status: "WAITING_APPROVAL" }), waitingApprovalAudit());
    render(<CaseView caseId="1" />);
    await tick();
    expect(actions()).toHaveLength(15);

    const [first] = caseDetail().candidates;
    serve(
      caseDetail({ candidates: [{ ...first, staff_id: 202, first_name: "Phanu" }] }),
      waitingResponseAudit().slice(0, 4),
    );
    await tick(2000);
    expect(status()).toBe("WAITING_RESPONSE");
    expect(rows("Candidates")).toEqual([["1", "202", "Phanu Demo", "SAME_WARD", "SENT"]]);
    expect(actions()).toEqual(["EVENT_RECEIVED", "UNAVAILABILITY_CREATED", "CASE_OPENED", "CASE_STATUS_CHANGED"]);
  });

  it("keeps the last data with a warning when a poll fails, and clears it on the next", async () => {
    render(<CaseView caseId="1" />);
    await tick();
    const working = backend;

    backend = { ...working, detail: () => { throw new TypeError("Failed to fetch"); } };
    await tick(2000);
    expect(screen.getByRole("alert").textContent).toBe(
      "Last update failed: Cannot reach the API. Check that the backend is running. "
      + "Showing the last known data. Retrying…",
    );
    expect(status()).toBe("WAITING_RESPONSE");
    expect(rows("Candidates")).toHaveLength(3);
    expect(actions()).toHaveLength(10);

    backend = { ...working, audit: () => json({ detail: "Internal Server Error" }, 500) };
    await tick(2000);
    expect(screen.getByRole("alert").textContent).toContain("Last update failed: Internal Server Error");
    expect(actions()).toHaveLength(10);

    backend = working;
    await tick(2000);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(status()).toBe("WAITING_RESPONSE");
  });

  it("shows the error and retries when the first load fails", async () => {
    backend.detail = () => { throw new TypeError("Failed to fetch"); };
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByRole("alert").textContent).toBe(
      "Cannot reach the API. Check that the backend is running. Retrying…",
    );
    expect(screen.queryByRole("status")).toBeNull();

    serve(caseDetail(), waitingResponseAudit());
    await tick(2000);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(status()).toBe("WAITING_RESPONSE");
  });

  it.each(["abc", "0", "-1", "1.5", "01", "", "12345678901234567890", "1/../demo", "1?x=1"])(
    "rejects the ID %j without sending a request", async caseId => {
      render(<CaseView caseId={caseId} />);
      await tick();
      expect(screen.getByText("Invalid case ID.")).toBeTruthy();
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Case");
      await tick(10000);
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("treats a 422 from the API as an invalid ID and stops polling", async () => {
    backend.detail = () => json({ detail: [{ type: "less_than_equal", loc: ["path", "case_id"] }] }, 422);
    render(<CaseView caseId="9999999999999999999" />);
    await tick();
    expect(screen.getByText("Invalid case ID.")).toBeTruthy();
    await tick(10000);
    expect(requests()).toEqual(["/cases/9999999999999999999"]);
  });

  it("keeps the API order of the timeline instead of sorting by time", async () => {
    serve(caseDetail(), [
      auditEntry(1, "EVENT_RECEIVED", { created_at: "2026-10-09T21:00:05+07:00" }),
      auditEntry(2, "CASE_OPENED", { created_at: "2026-10-09T21:00:00+07:00" }),
      auditEntry(3, "GAP_ASSESSED", { created_at: "2026-10-09T21:00:00+07:00" }),
    ]);
    render(<CaseView caseId="1" />);
    await tick();
    expect(rows("Timeline").map(cells => cells.slice(0, 3))).toEqual([
      ["1", "2026-10-09 21:00:05", "EVENT_RECEIVED"],
      ["2", "2026-10-09 21:00:00", "CASE_OPENED"],
      ["3", "2026-10-09 21:00:00", "GAP_ASSESSED"],
    ]);
  });

  it("renders each kind of timeline row", async () => {
    serve(caseDetail(), [
      ...waitingResponseAudit().slice(0, 5),
      auditEntry(6, "APPROVAL_APPROVED", {
        actor_id: 900, actor_name: "900", actor_type: "user",
        entity_type: "APPROVAL_REQUEST", payload: { approval_id: 1, reason: null },
      }),
      auditEntry(7, "AN_ACTION_ADDED_LATER", { entity_id: null, payload: {} }),
    ]);
    render(<CaseView caseId="1" />);
    await tick();
    const timeline = rows("Timeline");
    expect(timeline[0].slice(3)).toEqual([
      "Staff 105", "STAFFING_EVENTS #1", "event_type: STAFF_UNAVAILABLEshift_id: 1staff_id: 105",
    ]);
    expect(timeline[2].slice(3, 5)).toEqual(["workflow_orchestrator", "STAFFING_CASES #1"]);
    expect(timeline[3].slice(2)).toEqual([
      "CASE_STATUS_CHANGED", "workflow_orchestrator", "STAFFING_CASES #1", "OPEN → ASSESSING",
    ]);
    expect(timeline[4][5]).toContain(
      'role_gaps: [{"role_id":1,"required_count":5,"current_count":4,"gap_count":1}]',
    );
    expect(timeline[5][5]).toBe("approval_id: 1reason: —");
    expect(timeline[6].slice(2)).toEqual([
      "AN_ACTION_ADDED_LATER", "workflow_orchestrator", "STAFFING_CASES", "",
    ]);

    // Status changes stay in sequence but lighter than the real steps.
    const tableRows = within(screen.getByRole("table", { name: "Timeline" })).getAllByRole("row").slice(1);
    expect(tableRows.map(row => row.className.includes("text-gray-500"))).toEqual([
      false, false, false, true, false, false, false,
    ]);
  });

  it("shows an unknown status as it is, without a meaning", async () => {
    serve(caseDetail({ status: "A_STATUS_ADDED_LATER" }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText("Status:").textContent).toBe("Status: A_STATUS_ADDED_LATER");
    expect(screen.getByText("Updating every 2 seconds.")).toBeTruthy();
  });

  it.each([
    ["a page that is not JSON", () => new Response("<html>proxy error</html>"), () => json([])],
    ["a case without candidates", () => json({ id: 1, status: "OPEN", gap: null }), () => json([])],
    ["a wrapped audit list", () => json(caseDetail()), () => json({ items: [] })],
    ["an audit row without a payload", () => json(caseDetail()), () => json([{ id: 1, action: "CASE_OPENED" }])],
  ])("shows an error instead of crashing on %s", async (_name, detail, audit) => {
    backend = { detail, audit };
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByRole("alert").textContent).toBe("Unexpected response from the API Retrying…");
  });

  it("loads the other case when the ID changes after polling stopped", async () => {
    serve(caseDetail({ status: "RESOLVED" }), resolvedAudit());
    const { rerender } = render(<CaseView caseId="1" />);
    await tick();
    await tick(10000);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    serve(caseDetail({ id: 2, status: "WAITING_APPROVAL", candidates: [] }), [auditEntry(21, "CASE_OPENED")]);
    rerender(<CaseView caseId="2" />);
    expect(screen.queryByText("Status:")).toBeNull();
    await tick();
    expect(requests().slice(2)).toEqual(["/cases/2", "/cases/2/audit"]);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Case 2");
    expect(status()).toBe("WAITING_APPROVAL");
    expect(actions()).toEqual(["CASE_OPENED"]);
    await tick(2000);
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("stops polling when the page is left", async () => {
    const { unmount } = render(<CaseView caseId="1" />);
    await tick();
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(10000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not read the audit when the page is left while the case is loading", async () => {
    const audit = vi.fn(() => json([]));
    backend.audit = audit;
    render(<CaseView caseId="1" />).unmount();
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(10000);
    expect(audit).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
