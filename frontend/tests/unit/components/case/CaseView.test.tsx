// @vitest-environment jsdom

import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CaseView } from "../../../../src/components/case/CaseView";
import {
  auditEntry,
  caseDetail,
  DEMO_TIME,
  resolvedAudit,
  score,
  statusChange,
  waitingApprovalAudit,
  waitingResponseAudit,
} from "../../../fixtures/case";

type Reply = () => Response | Promise<Response>;

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

// The fake backend. A test swaps what the two routes answer between polls.
let backend: { detail: Reply; audit: Reply; post?: Reply };
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  // Like the real fetch, it sends nothing for a request that is already aborted.
  if (init?.signal?.aborted) throw new DOMException("The operation was aborted.", "AbortError");
  if (init?.method === "POST") {
    // Like the real fetch, a request that is given up rejects with an AbortError
    return new Promise<Response>((resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("The operation was aborted.", "AbortError")));
      Promise.resolve((backend.post ?? (() => json({}, 500)))()).then(resolve, reject);
    });
  }
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

function posts() {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
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
    expect(screen.getByText("Waiting for candidates to reply")).toBeTruthy();
    expect(screen.getByText("Updating every 2 seconds.")).toBeTruthy();
    expect(screen.getByText("Headcount:").textContent).toContain("Short by 1");
    expect(rows("Gap")).toEqual([
      ["Role", "RN", "5", "4", "Short by 1"],
      ["Skill", "ICU", "2", "2", "OK"],
    ]);
    expect(rows("Candidates")).toEqual([
      ["1", "201", "Arunee Demo", "SAME_WARD", "Offer sent, waiting for reply", "1005", "ICU", "Whole shift", "—"],
      ["2", "202", "Phanu Demo", "SAME_WARD", "Not contacted", "1013", "ICU", "Whole shift", "—"],
      ["3", "203", "Chonthicha Demo", "SAME_WARD", "Not contacted", "1020", "ICU", "Whole shift", "—"],
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
    expect(screen.getByText("No candidates.")).toBeTruthy();
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
        id: 1, effective_minimum: 5, headcount_gap: 0, computed_at: DEMO_TIME,
        roles: [{ id: 1, name: "RN", required_count: 5, current_count: 5, gap_count: 0 }],
        skills: [{ id: 1, name: "ICU", required_count: 2, current_count: 1, gap_count: 1 }],
        evaluated_from: null, intervals: [],
      },
    }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText("Headcount:").textContent).toBe("Headcount: OKMinimum 5Computed 2026-10-09 21:00:00");
    expect(rows("Gap")).toEqual([
      ["Role", "RN", "5", "5", "OK"],
      ["Skill", "ICU", "2", "1", "Short by 1"],
    ]);
  });

  it("never adds the headcount, role and skill gaps together", async () => {
    serve(caseDetail({
      gap: {
        id: 1, effective_minimum: 5, headcount_gap: 1, computed_at: DEMO_TIME,
        roles: [{ id: 1, name: "RN", required_count: 5, current_count: 4, gap_count: 1 }],
        skills: [{ id: 1, name: "ICU", required_count: 2, current_count: 1, gap_count: 1 }],
        evaluated_from: null, intervals: [],
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
    expect(rows("Candidates")).toEqual([["1", "202", "Phanu Demo", "SAME_WARD", "Offer sent, waiting for reply", "1005", "ICU", "Whole shift", "—"]]);
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

  it.each([
    ["NOT_CONTACTED", "Not contacted"],
    ["OFFER_PENDING", "Offer queued"],
    ["OFFER_SENT", "Offer sent, waiting for reply"],
    ["OFFER_REJECTED", "Declined the offer"],
    ["OFFER_TIMEOUT", "Did not reply in time"],
    ["OFFER_FAILED", "Offer could not be delivered"],
    ["OFFER_CANCELLED", "Offer cancelled"],
    ["ACCEPTED", "Accepted, on reserve"],
    ["SAFETY_FAILED", "Accepted, failed the safety check"],
    ["WAITING_APPROVAL", "Accepted, waiting for approval"],
    ["APPROVAL_REJECTED", "Not approved"],
    ["APPROVAL_TIMEOUT", "Approval timed out"],
    ["APPROVED", "Approved, not on the roster"],
    ["ASSIGNED", "Assigned to the shift"],
  ])("shows the candidate stage %s as %j", async (stage, label) => {
    const [first] = caseDetail().candidates;
    serve(caseDetail({ candidates: [{ ...first, stage }] }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(rows("Candidates")[0][4]).toBe(label);
  });

  it("shows an unknown candidate stage as it is", async () => {
    const [first] = caseDetail().candidates;
    serve(caseDetail({ candidates: [{ ...first, stage: "A_STAGE_ADDED_LATER" }] }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(rows("Candidates")[0][4]).toBe("A_STAGE_ADDED_LATER");
  });

  it("shows the headcount minimum and how many are on the shift", async () => {
    render(<CaseView caseId="1" />);
    await tick();
    const text = screen.getByText("Headcount:").textContent;
    expect(text).toContain("Short by 1");
    expect(text).toContain("Minimum 5, 4 on shift when assessed");
  });

  it("lists every event of the case", async () => {
    serve(caseDetail({ event_ids: [1, 2] }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText("1, 2")).toBeTruthy();
  });

  it("shows no skipped table when nobody was skipped", async () => {
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.queryByRole("table", { name: "Skipped" })).toBeNull();
  });

  it("lists the skipped candidates of a wave and of the handoff, and keeps polling", async () => {
    serve(caseDetail({ status: "MANUAL_HANDOFF" }), [
      auditEntry(1, "OFFER_SENT", {
        entity_type: "CANDIDATE_OUTREACH",
        payload: {
          outreach_id: 1, staff_id: 201, channel: "LINE", wave: 2,
          skipped: [{ staff_id: 202, reason: "OFFER_LIMIT_REACHED" }],
        },
      }),
      auditEntry(2, "MANUAL_HANDOFF", {
        payload: {
          reason: "NO_CANDIDATE_LEFT",
          skipped: [{ staff_id: 204, reason: "A_REASON_ADDED_LATER" }],
        },
      }),
    ]);
    render(<CaseView caseId="1" />);
    await tick();
    expect(rows("Skipped")).toEqual([
      ["Wave 2", "202", "Phanu Demo", "OFFER_LIMIT_REACHEDAlready holds the maximum number of open offers"],
      ["Handoff", "204", "—", "A_REASON_ADDED_LATER"],
    ]);
    await tick(4000);
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("lists skipped people without names when the case stopped without a plan", async () => {
    serve(caseDetail({ status: "MANUAL_HANDOFF", candidates: [] }), [
      auditEntry(1, "MANUAL_HANDOFF", {
        payload: {
          reason: "NO_FEASIBLE_PLAN",
          skipped: [
            { staff_id: 201, reason: "STAFF_NOT_ACTIVE" },
            { staff_id: 202, reason: "STAFF_NOT_ACTIVE" },
          ],
        },
      }),
    ]);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText("No candidates.")).toBeTruthy();
    expect(screen.queryByText("No candidates yet.")).toBeNull();
    const skipped = screen.getByRole("table", { name: "Skipped" });
    expect(within(skipped).queryByRole("columnheader", { name: "Name" })).toBeNull();
    expect(rows("Skipped")).toEqual([
      ["Handoff", "201", "STAFF_NOT_ACTIVENot an active staff member"],
      ["Handoff", "202", "STAFF_NOT_ACTIVENot an active staff member"],
    ]);
  });

  it("shows an unknown status as it is, without a meaning", async () => {
    serve(caseDetail({ status: "A_STATUS_ADDED_LATER" }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText("Status:").textContent).toBe("Status: A_STATUS_ADDED_LATER");
    expect(screen.getByText("Updating every 2 seconds.")).toBeTruthy();
  });

  describe("score breakdown", () => {
    /** The term name of each row, without the reason text. */
    const termNames = (table: string) => within(screen.getByRole("table", { name: table })).getAllByRole("row")
      .slice(1).map(row => row.querySelector("td")?.firstChild?.textContent);

    it("says points decide the first wave on a normal plan", async () => {
      render(<CaseView caseId="1" />);
      await tick();
      expect(screen.getByText(/^Points decide which group becomes the first wave/)).toBeTruthy();
      expect(screen.queryByText(/Coverage decides first/)).toBeNull();
    });

    it("says coverage decides first on a partial plan", async () => {
      serve(caseDetail({ partial_plan: true }), []);
      render(<CaseView caseId="1" />);
      await tick();
      expect(screen.getByText(/^Coverage decides first: no group could cover every target/)).toBeTruthy();
      expect(screen.queryByText(/Points decide which group/)).toBeNull();
    });

    it("shows each score table with terms sorted by points and the fixed reasons", async () => {
      render(<CaseView caseId="1" />);
      await tick();

      expect(screen.getByRole("heading", { name: "Score breakdown" })).toBeTruthy();
      expect(screen.getByText(/^Points decide which group becomes the first wave/)).toBeTruthy();
      expect(screen.queryByText(/Fewer points is better/)).toBeNull();
      for (const staff of [201, 202, 203]) {
        expect(screen.getByRole("table", { name: `Score of staff ${staff}` })).toBeTruthy();
      }
      expect(rows("Score of staff 202")).toEqual([
        ["candidate_countSame for everyone: each person called in adds this", "1", "1000", "1000"],
        ["workload_imbalanceCommitted roster hours this week when the plan was created", "8", "1", "8"],
        ["consecutive_shiftShifts in a row with this shift added", "1", "5", "5"],
        ["projected_overtimeOvertime hours already worked this week", "0", "2", "0"],
        ["candidate_sourcePosition of their source in the source priority, 0 is the closest", "0", "200", "0"],
      ]);
      expect(screen.getByRole("heading", { name: "Rank 2 · Phanu Demo (202) · 1013 points" })).toBeTruthy();
      expect(screen.getByText("First wave: chosen to fill the gap")).toBeTruthy();
      expect(screen.getAllByText("Reserve: ranked after the first wave")).toHaveLength(2);
    });

    it("keeps the API rank when a higher rank has more points", async () => {
      const [a, b, c] = caseDetail().candidates;
      serve(caseDetail({
        candidates: [{ ...a, score: score(1020, true, [1, 4, 0, 0, 0]) }, { ...b, score: score(1013, true, [1, 1, 8, 0, 0]) }, c],
      }), waitingResponseAudit());
      render(<CaseView caseId="1" />);
      await tick();

      expect(rows("Candidates").slice(0, 2).map(cells => [cells[1], cells[5]])).toEqual([["201", "1020"], ["202", "1013"]]);
      const headings = screen.getAllByRole("heading", { level: 4 }).map(heading => heading.textContent ?? "");
      expect(headings[0].startsWith("Rank 1")).toBe(true);
      expect(headings[1].startsWith("Rank 2")).toBe(true);
    });

    it("keeps the API order for terms with equal points", async () => {
      render(<CaseView caseId="1" />);
      await tick();
      expect(termNames("Score of staff 201")).toEqual([
        "candidate_count", "consecutive_shift", "workload_imbalance", "projected_overtime", "candidate_source",
      ]);
    });

    it("shows a dash and no table or reason for a candidate without a score", async () => {
      const [a, b, c] = caseDetail().candidates;
      serve(caseDetail({ candidates: [a, b, { ...c, score: null }] }), waitingResponseAudit());
      render(<CaseView caseId="1" />);
      await tick();

      expect(rows("Candidates").map(cells => cells[5])).toEqual(["1005", "1013", "—"]);
      expect(screen.queryByRole("table", { name: "Score of staff 203" })).toBeNull();
      expect(screen.getByRole("table", { name: "Score of staff 201" })).toBeTruthy();
      expect(screen.getByRole("table", { name: "Score of staff 202" })).toBeTruthy();
      expect(screen.queryByText(/\(203\)/)).toBeNull();
    });

    describe("ranking explanation", () => {
      const sentence = "[fake] อันดับ 1 อยู่ในกลุ่มแรก";
      const ready = (provider: "fake" | "bedrock", modelId: string | null) => caseDetail({
        explanation: { status: "READY", text: sentence, provider, model_id: modelId, can_request: false, request_blocked_reason: "ALREADY_READY" },
      });
      const section = () => screen.getByRole("region", { name: "Ranking explanation" });
      const notReady = "คำอธิบายยังไม่พร้อม";
      const unrequested = (status: string, extra: Record<string, unknown> = {}) => ({
        status, text: null, provider: null, model_id: null, can_request: false, request_blocked_reason: null, ...extra,
      });

      it("shows a fake sentence with the source note and the fake note", async () => {
        serve(ready("fake", null), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();

        expect(within(section()).getByText(sentence)).toBeTruthy();
        expect(within(section()).getByText(/^Generated by an LLM from the numbers below/)).toBeTruthy();
        expect(within(section()).getByText(/^Test text from the fake LLM adapter/)).toBeTruthy();
        expect(within(section()).queryByText(notReady)).toBeNull();
      });

      it("shows a bedrock sentence with its model and no fake note", async () => {
        serve(ready("bedrock", "model-1"), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();

        expect(within(section()).getByText(sentence)).toBeTruthy();
        expect(within(section()).getByText("Model: model-1")).toBeTruthy();
        expect(within(section()).queryByText(/fake LLM adapter/)).toBeNull();
      });

      it.each([
        ["PENDING", unrequested("PENDING", { request_blocked_reason: "PENDING" }), "กำลังสร้างคำอธิบายจาก AI"],
        ["UNAVAILABLE", unrequested("UNAVAILABLE", { can_request: true }), "สร้างคำอธิบายจาก AI ไม่สำเร็จ"],
        ["NOT_REQUESTED", unrequested("NOT_REQUESTED", { can_request: true }), "ยังไม่ได้ขอคำอธิบายจาก AI"],
        ["null", null, notReady],
      ])("shows the status text for %s, never a sentence", async (_name, explanation, text) => {
        serve(caseDetail({ explanation } as Parameters<typeof caseDetail>[0]), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();

        expect(within(section()).getByText(text)).toBeTruthy();
        expect(within(section()).queryByText(/^Generated by an LLM/)).toBeNull();
        expect(screen.getByRole("table", { name: "Score of staff 201" })).toBeTruthy();
      });

      it("picks up a sentence that turns READY on the next poll", async () => {
        serve(caseDetail({ explanation: unrequested("PENDING", { request_blocked_reason: "PENDING" }) } as Parameters<typeof caseDetail>[0]), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();
        expect(within(section()).getByText("กำลังสร้างคำอธิบายจาก AI")).toBeTruthy();

        serve(ready("fake", null), waitingResponseAudit());
        await tick(2000);
        expect(within(section()).getByText(sentence)).toBeTruthy();
        expect(within(section()).queryByText("กำลังสร้างคำอธิบายจาก AI")).toBeNull();
      });

      describe("when the case is already final", () => {
        const pending = unrequested("PENDING", { request_blocked_reason: "PENDING" }) as never;
        const unavailable = unrequested("UNAVAILABLE", { request_blocked_reason: "INVALID_INPUT" }) as never;

        it("keeps polling while PENDING, then shows the sentence and stops", async () => {
          serve(caseDetail({ status: "RESOLVED", explanation: pending }), resolvedAudit());
          render(<CaseView caseId="1" />);
          await tick();
          expect(within(section()).getByText("กำลังสร้างคำอธิบายจาก AI")).toBeTruthy();
          expect(screen.getByText(/^Final status\. Still updating/)).toBeTruthy();

          await tick(30000);
          expect(fetchMock.mock.calls.length).toBeGreaterThan(2);

          serve(caseDetail({ status: "RESOLVED", explanation: ready("fake", null).explanation }), resolvedAudit());
          await tick(2000);
          expect(within(section()).getByText(sentence)).toBeTruthy();
          expect(screen.getByText("Final status. Updates stopped.")).toBeTruthy();

          const calls = fetchMock.mock.calls.length;
          await tick(10000);
          expect(fetchMock).toHaveBeenCalledTimes(calls);
          expect(vi.getTimerCount()).toBe(0);
        });

        it("stops when PENDING turns UNAVAILABLE", async () => {
          serve(caseDetail({ status: "UNRESOLVED", explanation: pending }), []);
          render(<CaseView caseId="1" />);
          await tick();

          serve(caseDetail({ status: "UNRESOLVED", explanation: unavailable }), []);
          await tick(2000);
          expect(within(section()).getByText("สร้างคำอธิบายจาก AI ไม่สำเร็จ")).toBeTruthy();
          expect(screen.getByText("Final status. Updates stopped.")).toBeTruthy();

          const calls = fetchMock.mock.calls.length;
          await tick(10000);
          expect(fetchMock).toHaveBeenCalledTimes(calls);
          expect(vi.getTimerCount()).toBe(0);
        });

        it.each([["RESOLVED"], ["FAILED"]])("stops at once with no explanation row (%s)", async final => {
          serve(caseDetail({ status: final, explanation: null }), []);
          render(<CaseView caseId="1" />);
          await tick();
          await tick(10000);

          expect(fetchMock).toHaveBeenCalledTimes(2);
          expect(screen.getByText("Final status. Updates stopped.")).toBeTruthy();
          expect(vi.getTimerCount()).toBe(0);
        });
      });
    });

    describe("asking for the AI explanation (round 6 PR E2)", () => {
      const section = () => screen.getByRole("region", { name: "Ranking explanation" });
      const button = () => within(section()).queryByRole("button", { name: "หน้าสรุปด้วย AI" }) as HTMLButtonElement | null;
      const view = (status: string, extra: Record<string, unknown> = {}) => ({
        status, text: null, provider: null, model_id: null, can_request: false, request_blocked_reason: null, ...extra,
      });
      const withExplanation = (explanation: unknown, status = "WAITING_RESPONSE") =>
        caseDetail({ status, explanation } as Parameters<typeof caseDetail>[0]);
      const ready = () => ({ ...view("READY", { request_blocked_reason: "ALREADY_READY" }), text: "[fake] x", provider: "fake" });
      const quotaMessage = "ใช้โควตาคำอธิบายจาก AI ครบแล้วในวันนี้ กรุณาลองใหม่ในวันถัดไป คุณยังดูอันดับและดำเนินการจัดเวรต่อได้ตามปกติ";
      const click = async () => {
        await act(async () => { button()?.click(); });
        await tick();
      };

      it("opens the button when can_request is true and sends nothing until it is pressed", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();

        expect(button()?.disabled).toBe(false);
        expect(posts()).toHaveLength(0);
      });

      it("posts once with no identity header, reads the case again and shows PENDING", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();

        const before = fetchMock.mock.calls.length;
        serve(withExplanation(view("PENDING", { request_blocked_reason: "PENDING" })), waitingResponseAudit());
        backend.post = () => json(view("PENDING", { request_blocked_reason: "PENDING" }));
        await click();

        const [[url, init]] = posts();
        expect(new URL(url).pathname).toBe("/cases/1/explanation");
        expect(new Headers(init?.headers).has("X-Demo-User")).toBe(false);
        expect(fetchMock.mock.calls.length).toBeGreaterThan(before + 1);
        expect(within(section()).getByText("กำลังสร้างคำอธิบายจาก AI")).toBeTruthy();
        expect(button()).toBeNull();
      });

      it("makes one request for two clicks in a row", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        let release: (response: Response) => void = () => {};
        backend.post = () => new Promise<Response>(resolve => { release = resolve; });
        render(<CaseView caseId="1" />);
        await tick();

        await act(async () => { button()?.click(); button()?.click(); });
        expect(button()?.disabled).toBe(true);
        expect(posts()).toHaveLength(1);

        await act(async () => { release(json(view("PENDING"))); });
        await tick();
        expect(posts()).toHaveLength(1);
      });

      it("works on a final case whose polling already stopped, and polls again while PENDING", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true }), "RESOLVED"), resolvedAudit());
        render(<CaseView caseId="1" />);
        await tick();
        await tick(10000);
        expect(screen.getByText("Final status. Updates stopped.")).toBeTruthy();

        serve(withExplanation(view("PENDING", { request_blocked_reason: "PENDING" }), "RESOLVED"), resolvedAudit());
        backend.post = () => json(view("PENDING"));
        await click();
        expect(screen.getByText(/^Final status\. Still updating/)).toBeTruthy();

        serve(withExplanation(ready(), "RESOLVED"), resolvedAudit());
        await tick(2000);
        expect(within(section()).getByText("[fake] x")).toBeTruthy();
        expect(screen.getByText("Final status. Updates stopped.")).toBeTruthy();
      });

      it("closes the button at the daily cap with the contract text, and a READY sentence stays readable", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { request_blocked_reason: "QUOTA_EXHAUSTED" })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();
        expect(button()?.disabled).toBe(true);
        expect(within(section()).getByText(quotaMessage)).toBeTruthy();
        cleanup();

        serve(withExplanation(ready()), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();
        expect(within(section()).getByText("[fake] x")).toBeTruthy();
        expect(button()).toBeNull();
        expect(screen.queryByText(quotaMessage)).toBeNull();
      });

      it.each([
        ["NOT_CONFIGURED", "ยังไม่เปิดใช้คำอธิบายจาก AI"],
        ["INVALID_INPUT", "สร้างคำอธิบายจาก AI ของแผนนี้ไม่ได้"],
        ["ATTEMPTS_EXHAUSTED", "ขอคำอธิบายจาก AI ของแผนนี้ครบจำนวนครั้งที่กำหนดแล้ว"],
      ])("closes the button with its own text for %s", async (reason, text) => {
        serve(withExplanation(view("UNAVAILABLE", { request_blocked_reason: reason })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();

        expect(button()?.disabled).toBe(true);
        expect(within(section()).getByText(new RegExp(`^${text}`))).toBeTruthy();
        expect(posts()).toHaveLength(0);
      });

      it("lets the user ask again after a failure that can be asked again", async () => {
        serve(withExplanation(view("UNAVAILABLE", { can_request: true })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();

        expect(within(section()).getByText("สร้างคำอธิบายจาก AI ไม่สำเร็จ")).toBeTruthy();
        expect(button()?.disabled).toBe(false);
      });

      const attemptsMessage = "ขอคำอธิบายจาก AI ของแผนนี้ครบจำนวนครั้งที่กำหนดแล้ว";
      const notConfiguredMessage = "ยังไม่เปิดใช้คำอธิบายจาก AI";
      const invalidMessage = "สร้างคำอธิบายจาก AI ของแผนนี้ไม่ได้";
      const neutral = "ตอนนี้ขอคำอธิบายจาก AI ไม่ได้";
      it.each([
        // status, code, what the case says when read again, texts shown, texts not shown
        [429, "LLM_QUOTA_EXHAUSTED", "QUOTA_EXHAUSTED", [quotaMessage], [neutral]],
        [409, "LLM_ATTEMPTS_EXHAUSTED", "ATTEMPTS_EXHAUSTED", [attemptsMessage], [neutral]],
        // One code for two causes: the page says the cause the case reports, never the other one
        [409, "LLM_UNAVAILABLE", "INVALID_INPUT", [invalidMessage], [notConfiguredMessage, neutral]],
        [409, "LLM_UNAVAILABLE", "NOT_CONFIGURED", [notConfiguredMessage], [invalidMessage, neutral]],
      ])("after a refusal (%s %s, case now %s) says the cause once, from the case, not the server", async (status, code, now, shown, hidden) => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();
        serve(withExplanation(view("NOT_REQUESTED", { request_blocked_reason: now })), waitingResponseAudit());
        backend.post = () => json({ detail: { code, message: "SERVER WORDS" } }, status);
        await click();

        for (const text of shown as string[]) {
          expect(within(section()).getAllByText(new RegExp(`^${text}`))).toHaveLength(1);
        }
        for (const text of hidden as string[]) expect(screen.queryByText(new RegExp(`^${text}`))).toBeNull();
        expect(screen.queryByText(/SERVER WORDS/)).toBeNull();
        expect(within(section()).queryByRole("alert")).toBeNull();
        expect(button()?.disabled).toBe(true);
      });

      it.each([
        [409, "LLM_UNAVAILABLE", neutral],
        [404, "CASE_NOT_FOUND", "ไม่พบเคสนี้แล้ว"],
      ])("shows a message of its own for a refusal (%s %s) the case does not explain", async (status, code, text) => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();
        backend.post = () => json({ detail: { code, message: "SERVER WORDS" } }, status);
        await click();

        expect(within(section()).getByRole("alert").textContent).toBe(text);
        expect(screen.queryByText(/SERVER WORDS/)).toBeNull();
        expect(button()?.disabled).toBe(false);
      });

      it("gives up a request that never answers, frees the button and says to try again", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        backend.post = () => new Promise<Response>(() => {});
        render(<CaseView caseId="1" />);
        await tick();

        await act(async () => { button()?.click(); });
        await tick(9000);
        expect(button()?.disabled).toBe(true);

        await tick(1500);
        expect(within(section()).getByRole("alert").textContent).toBe("ส่งคำขอไม่สำเร็จ กรุณาลองใหม่");
        expect(button()?.disabled).toBe(false);
        expect(vi.getTimerCount()).toBeGreaterThan(0);
        // The case is read again after giving up: a request that timed out may still have been accepted
        serve(withExplanation(view("PENDING", { request_blocked_reason: "PENDING" })), waitingResponseAudit());
        await tick(2000);
        expect(within(section()).getByText("กำลังสร้างคำอธิบายจาก AI")).toBeTruthy();
        expect(within(section()).queryByRole("alert")).toBeNull();
      });

      it("drops an old message when the explanation changes", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();
        backend.post = () => { throw new TypeError("Failed to fetch"); };
        await click();
        expect(within(section()).getByRole("alert")).toBeTruthy();

        serve(withExplanation(view("UNAVAILABLE", { can_request: true })), waitingResponseAudit());
        await tick(2000);
        expect(within(section()).getByText("สร้างคำอธิบายจาก AI ไม่สำเร็จ")).toBeTruthy();
        expect(within(section()).queryByRole("alert")).toBeNull();
      });

      it("cancels the request and does not read the case again when the page is left", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        backend.post = () => new Promise<Response>(() => {});
        const { unmount } = render(<CaseView caseId="1" />);
        await tick();
        await act(async () => { button()?.click(); });
        const calls = fetchMock.mock.calls.length;

        unmount();
        await tick(20000);
        expect(fetchMock).toHaveBeenCalledTimes(calls);
        expect(vi.getTimerCount()).toBe(0);
      });

      it("says the request failed when the server cannot be reached, and lets the user try again", async () => {
        serve(withExplanation(view("NOT_REQUESTED", { can_request: true })), waitingResponseAudit());
        render(<CaseView caseId="1" />);
        await tick();
        backend.post = () => { throw new TypeError("Failed to fetch"); };
        await click();

        expect(within(section()).getByRole("alert").textContent).toBe("ส่งคำขอไม่สำเร็จ กรุณาลองใหม่");
        expect(button()?.disabled).toBe(false);
      });
    });

    it("shows no explanation section when no candidate has a score", async () => {
      const candidates = caseDetail().candidates.map(candidate => ({ ...candidate, score: null }));
      serve(caseDetail({ candidates }), waitingResponseAudit());
      render(<CaseView caseId="1" />);
      await tick();

      expect(screen.queryByRole("heading", { name: "Score breakdown" })).toBeNull();
      expect(screen.queryByRole("region", { name: "Ranking explanation" })).toBeNull();
      expect(screen.queryByText("คำอธิบายยังไม่พร้อม")).toBeNull();
      expect(screen.queryByRole("table", { name: /^Score of staff/ })).toBeNull();
      expect(rows("Candidates")).toEqual([
        ["1", "201", "Arunee Demo", "SAME_WARD", "Offer sent, waiting for reply", "—", "ICU", "Whole shift", "—"],
        ["2", "202", "Phanu Demo", "SAME_WARD", "Not contacted", "—", "ICU", "Whole shift", "—"],
        ["3", "203", "Chonthicha Demo", "SAME_WARD", "Not contacted", "—", "ICU", "Whole shift", "—"],
      ]);
    });

    it("shows the numbers as given without re-summing or exact decimals", async () => {
      const [a, ...rest] = caseDetail().candidates;
      const odd = score(999, true, [1, 1, 0, 0, 0]);
      odd.terms[2] = { ...odd.terms[2], value: 0.3333333333333333, points: 0.3333333333333333 };
      serve(caseDetail({ candidates: [{ ...a, score: odd }, ...rest] }), waitingResponseAudit());
      render(<CaseView caseId="1" />);
      await tick();

      expect(rows("Candidates")[0][5]).toBe("999");
      expect(screen.getByRole("heading", { name: "Rank 1 · Arunee Demo (201) · 999 points" })).toBeTruthy();
      expect(rows("Score of staff 201").find(cells => cells[0].startsWith("workload_imbalance")))
        .toEqual(["workload_imbalanceCommitted roster hours this week when the plan was created", "0.33", "1", "0.33"]);
    });

    it("shows a term name it does not know as it is, without a reason", async () => {
      const [a, ...rest] = caseDetail().candidates;
      const extra = score(1005, true, [1, 1, 0, 0, 0]);
      extra.terms.push({ name: "A_TERM_ADDED_LATER", value: 1, weight: 1, points: 1 });
      serve(caseDetail({ candidates: [{ ...a, score: extra }, ...rest] }), waitingResponseAudit());
      render(<CaseView caseId="1" />);
      await tick();

      expect(rows("Score of staff 201").find(cells => cells[0].includes("A_TERM_ADDED_LATER")))
        .toEqual(["A_TERM_ADDED_LATER", "1", "1", "1"]);
      expect(termNames("Score of staff 201")[2]).toBe("A_TERM_ADDED_LATER");
    });
  });

  it.each([
    ["a page that is not JSON", () => new Response("<html>proxy error</html>"), () => json([])],
    ["a case without candidates", () => json({ id: 1, status: "OPEN", gap: null }), () => json([])],
    ["a wrapped audit list", () => json(caseDetail()), () => json({ items: [] })],
    ["an audit row without a payload", () => json(caseDetail()), () => json([{ id: 1, action: "CASE_OPENED" }])],
    [
      "a candidate with a malformed score",
      () => json(caseDetail({ candidates: [{ ...caseDetail().candidates[0], score: "1005" as unknown as null }] })),
      () => json([]),
    ],
    [
      "a candidate with a score term whose name is an object",
      () => {
        const bad = score(1005, true, [1, 1, 0, 0, 0]);
        bad.terms[0] = { ...bad.terms[0], name: { invalid: true } as unknown as string };
        return json(caseDetail({ candidates: [{ ...caseDetail().candidates[0], score: bad }] }));
      },
      () => json([]),
    ],
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

  describe("round 4 (PR U)", () => {
    const slice = (start: string, end: string, gap: number) => ({
      start_at: start,
      end_at: end,
      headcount: { required_count: 5, current_count: 5 - gap, gap_count: gap },
      roles: [{ id: 1, name: "RN", required_count: 5, current_count: 5 - gap, gap_count: gap }],
      skills: [],
    });

    it("shows the gap by time slice when the shortage changes during the shift", async () => {
      const base = caseDetail();
      serve(
        caseDetail({
          gap: {
            ...base.gap!,
            intervals: [
              slice("2026-10-09T23:00:00+07:00", "2026-10-10T03:00:00+07:00", 0),
              slice("2026-10-10T03:00:00+07:00", "2026-10-10T07:00:00+07:00", 1),
            ],
          },
        }),
        waitingResponseAudit(),
      );
      render(<CaseView caseId="1" />);
      await tick();

      expect(rows("Gap by time")).toEqual([
        ["2026-10-09 23:00:00", "2026-10-10 03:00:00", "5 of 5", "Covered"],
        ["2026-10-10 03:00:00", "2026-10-10 07:00:00", "4 of 5", "Short: 1 person, 1 RN"],
      ]);
    });

    it("shows the bounds of a single slice: a started shift is measured from the assessment", async () => {
      // A 23:00-07:00 shift assessed at 03:00 has one slice, 03:00-07:00 (review of #86)
      const base = caseDetail();
      serve(
        caseDetail({
          gap: {
            ...base.gap!,
            evaluated_from: "2026-10-10T03:00:00+07:00",
            intervals: [slice("2026-10-10T03:00:00+07:00", "2026-10-10T07:00:00+07:00", 1)],
          },
        }),
        waitingResponseAudit(),
      );
      render(<CaseView caseId="1" />);
      await tick();

      expect(rows("Gap by time")).toEqual([
        ["2026-10-10 03:00:00", "2026-10-10 07:00:00", "4 of 5", "Short: 1 person, 1 RN"],
      ]);
    });

    it("shows no slice table for a gap written before round 4", async () => {
      render(<CaseView caseId="1" />);
      await tick();

      expect(caseDetail().gap!.intervals).toEqual([]);
      expect(screen.queryByRole("table", { name: "Gap by time" })).toBeNull();
    });

    it("shows the home ward, the cover window and the source shift of a candidate", async () => {
      const [first, ...others] = caseDetail().candidates;
      serve(
        caseDetail({
          candidates: [
            {
              ...first,
              source: "CROSS_WARD",
              home_ward_id: 2,
              home_ward_name: "Medicine",
              cover_start_at: "2026-10-10T03:00:00+07:00",
              cover_end_at: null,
              source_assignment: { assignment_id: 40, shift_id: 21, ward_id: 2, ward_name: "Medicine" },
            },
            ...others,
          ],
        }),
        waitingResponseAudit(),
      );
      render(<CaseView caseId="1" />);
      await tick();

      expect(rows("Candidates")[0].slice(6)).toEqual([
        "Medicine",
        "2026-10-10 03:00:00 – shift end",
        "Medicine, shift 21",
      ]);
    });
  });

  it("shows the handovers of the case", async () => {
    serve(
      caseDetail({
        status: "RESOLVED",
        handovers: [
          {
            handover_id: 5,
            roster_assignment_id: 40,
            active: true,
            generated_at: "2026-10-09T21:05:00+07:00",
            content: { version: 1, shift: { id: 1, ward_name: "ICU" }, reason: "UNPLANNED_LEAVE", co_workers: [] },
          },
        ],
      }),
      [],
    );
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByRole("heading", { name: "Handovers" })).toBeTruthy();
    expect(screen.getByText(/Shift 1 \(ICU\)/)).toBeTruthy();
    expect(screen.getByText("Unplanned leave")).toBeTruthy();
  });

  it("keeps reading a resolved case while a handover is active and shows it as history later", async () => {
    const card = (active: boolean) => ({
      handover_id: 6,
      roster_assignment_id: 41,
      active,
      generated_at: "2026-10-09T21:05:00+07:00",
      content: {
        version: 1,
        shift: { id: 1, ward_name: "ICU" },
        requirement: { roles: [{ role_id: 1, name: "RN", required_count: 4 }], skills: [{ skill_id: 2, name: "ICU", required_count: 2 }] },
        co_workers: [],
      },
    });
    serve(caseDetail({ status: "RESOLVED", handovers: [card(true)] }), []);
    render(<CaseView caseId="1" />);
    await tick();
    expect(screen.getByText(/while a handover is active/)).toBeTruthy();
    expect(screen.getByText("RN × 4")).toBeTruthy();
    expect(screen.getByText("ICU × 2")).toBeTruthy();
    serve(caseDetail({ status: "RESOLVED", handovers: [card(false)] }), []);
    await tick(2000);
    expect(screen.getByText(/history, no longer active/)).toBeTruthy();
    expect(screen.getByText("Final status. Updates stopped.")).toBeTruthy();
    const calls = fetchMock.mock.calls.length;
    await tick(10000);
    expect(fetchMock.mock.calls.length).toBe(calls);
  });
});
