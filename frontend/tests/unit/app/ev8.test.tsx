// @vitest-environment jsdom
// Round 6 PR EV8 (docs/workflow.md 6.38): the Dashboard's cards and charts, the status page, a
// nurse's roster, the two lists of offers, the replacement summary of a case, the columns of
// the candidates and the Manage dialog of the case list. The Backend is a stub of fetch; the
// provider, the gate, the pages and the API layer are the real ones.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CaseList from "@/app/cases/page";
import MyOffers from "@/app/me/offers/page";
import Home from "@/app/page";
import RosterRoute from "@/app/roster/page";
import StatusPage from "@/app/status/page";
import { AuthGate, AuthProvider } from "@/components/AuthProvider";
import { CandidateTable } from "@/components/candidate/CandidateTable";
import { CaseOverviewCard } from "@/components/case/CaseOverviewCard";
import { waitingForText } from "@/components/dashboard/DashboardView";
import { OFFERS_PAGE_SIZE, OfferList } from "@/components/outreach/OfferList";
import { setSessionMode } from "@/lib/api";
import { translator } from "@/lib/i18n";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import type { CandidateView, CaseOverview, OverviewPerson, OverviewSide } from "@/lib/types/case";
import type { Offer } from "@/lib/types/outreach";
import { caseDetail } from "../../fixtures/case";
import { dashboard, withCounts } from "../../fixtures/dashboard";

const replace = vi.fn();
let pathname = "/";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

type Reply = { status: number; body?: unknown };
/** "GET /path" to its answer; the handler sees the whole URL, so it can read the query */
let routes: Record<string, (url: URL, body: unknown) => Reply> = {};
const seen: string[] = [];

const STAFF = { staff_id: 201, role: "staff", home_ward_id: 1, must_change_password: false };
const HEAD = { staff_id: 900, role: "head_nurse", home_ward_id: 1, must_change_password: false };
const ok = (body: unknown): Reply => ({ status: 200, body });

function session(me: unknown, extra: Record<string, (url: URL, body: unknown) => Reply> = {}) {
  routes = {
    "GET /auth/config": () => ok({ auth_mode: "session" }),
    "GET /auth/me": () => ok(me),
    "GET /clock": () => ok({ now: "2026-10-24T21:00:00+07:00", frozen: true }),
    ...extra,
  };
}

beforeEach(() => {
  replace.mockReset();
  pathname = "/";
  seen.length = 0;
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      seen.push(`${init.method ?? "GET"} ${url.pathname}${url.search}`);
      const handler = routes[`${init.method ?? "GET"} ${url.pathname}`];
      if (!handler) return new Response(JSON.stringify({ detail: "no stub" }), { status: 599 });
      const reply = handler(url, init.body ? JSON.parse(String(init.body)) : undefined);
      return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), { status: reply.status });
    }),
  );
});
afterEach(() => {
  cleanup();
  setSessionMode(false);
  vi.unstubAllGlobals();
});

function app(element: ReactElement, lang: "en" | "th" = "en") {
  return render(
    <LanguageProvider initial={lang}>
      <AuthProvider>
        <AuthGate>{element}</AuthGate>
      </AuthProvider>
    </LanguageProvider>,
  );
}

const shortage = (shift_id: number, ward_id: number, gap: number, in_progress: boolean) => ({
  shift_id,
  ward_id,
  start_at: in_progress ? "2026-10-24T15:00:00+07:00" : "2026-10-25T07:00:00+07:00",
  end_at: in_progress ? "2026-10-24T23:00:00+07:00" : "2026-10-25T15:00:00+07:00",
  headcount_gap: gap,
  role_gaps: [{ name: "RN", gap_count: gap }],
  skill_gaps: [{ name: "BLS", gap_count: 1 }],
  case_id: shift_id === 11 ? 7 : null,
  in_progress,
});

function board(wardId: number | null) {
  const all = [shortage(11, 1, 2, true), shortage(12, 2, 1, false), shortage(13, 1, 1, false)];
  const shortages = wardId === null ? all : all.filter((row) => row.ward_id === wardId);
  return dashboard({
    wards: wardId === null ? [1, 2] : [wardId],
    ward_options: [
      { id: 1, name: "Surgery" },
      { id: 2, name: "Pediatrics" },
    ],
    window_hours: 24,
    demo_data: true,
    summary: {
      short_shifts: shortages.length,
      missing_positions: shortages.reduce((sum, row) => sum + row.headcount_gap, 0),
      pending_approvals: 3,
      pending_approvals_later: 2,
      handoff_cases: 1,
    },
    cases_by_status: withCounts({ WAITING_RESPONSE: 2, ASSESSING: 1, RESOLVED: 4, MANUAL_HANDOFF: 1, UNRESOLVED: 1 }),
    shortages,
    shortage_by_ward:
      wardId === 2
        ? [{ ward_id: 2, missing_positions: 1, short_shifts: 1 }]
        : wardId === 1
          ? [{ ward_id: 1, missing_positions: 3, short_shifts: 2 }]
          : [
              { ward_id: 1, missing_positions: 3, short_shifts: 2 },
              { ward_id: 2, missing_positions: 1, short_shifts: 1 },
            ],
    pending_approvals: [
      { ward_id: 1, count: 1, head_nurses: [{ staff_id: 200001, name: "Jintana C." }], supervisor: false },
      { ward_id: 2, count: 2, head_nurses: [{ staff_id: 200301, name: "Usa W." }], supervisor: true },
    ],
  });
}

describe("the Dashboard of round 6 PR EV8", () => {
  beforeEach(() => {
    session(HEAD, {
      "GET /dashboard": (url) => {
        const ward = url.searchParams.get("ward_id");
        return ok(board(ward === null ? null : Number(ward)));
      },
    });
  });

  it("leads with four cards that open their lists, and marks demo data", async () => {
    app(<Home />);
    const cards = within(await screen.findByRole("region", { name: "Summary" }));
    const links = cards.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      expect.stringContaining("Short shifts within 24 h3"),
      expect.stringContaining("Positions still missing4"),
      expect.stringContaining("Requests waiting for approval3"),
      expect.stringContaining("Cases waiting for a person1"),
    ]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "#urgent-shifts",
      "#shortage-by-ward",
      "/approvals?as=900",
      "/handoff?as=900",
    ]);
    // Positions over shifts are not people, and every part says the time it covers
    expect(links[1].textContent).toContain("not people");
    // The card counts what the user may decide now, like the page it opens (review of #147)
    expect(links[2].textContent).toContain(
      "That you may decide now; 2 more wait for head nurses until the Supervisor's time",
    );
    expect(screen.getByText("Simulated data (Demo)")).toBeTruthy();
    expect(screen.getByText(/A position is counted on each shift it is missing from/)).toBeTruthy();
    expect(screen.getByText("Every case of the wards shown, by its status now")).toBeTruthy();
    expect(screen.getByText(/^From now until 2026-10-18 21:00 \(the next 24 hours\)$/)).toBeTruthy();
  });

  it("charts the missing positions by ward, and a bar narrows the whole page to its ward", async () => {
    app(<Home />);
    const chart = within(await screen.findByRole("region", { name: "Positions still missing by ward" }));
    const bars = chart.getAllByRole("button");
    expect(bars.map((bar) => bar.getAttribute("aria-label"))).toEqual([
      "Surgery: 3 positions missing over 2 shifts. Show this ward",
      "Pediatrics: 1 positions missing over 1 shifts. Show this ward",
    ]);
    fireEvent.click(bars[1]);
    await waitFor(() => expect(seen).toContain("GET /dashboard?ward_id=2"));
    const table = within(await screen.findByRole("table", { name: "Short shifts, most urgent first" }));
    await waitFor(() => expect(table.getAllByRole("row")).toHaveLength(2));
    expect(table.getByText("Pediatrics")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show ward" }).textContent).toContain("Pediatrics");
  });

  it("lists running shifts first with a mark, the roles and skills short, and a link to the case", async () => {
    app(<Home />);
    const table = within(await screen.findByRole("table", { name: "Short shifts, most urgent first" }));
    const [, first, second] = table.getAllByRole("row");
    expect(within(first).getByText("In progress")).toBeTruthy();
    expect(first.textContent).toContain("2026-10-24 15:00 – 23:00");
    expect(within(first).getByRole("link", { name: "Case 7" }).getAttribute("href")).toBe("/cases/7");
    expect(within(first).getByText("2 RN")).toBeTruthy();
    expect(within(first).getByText("1 BLS")).toBeTruthy();
    expect(within(second).queryByText("In progress")).toBeNull();
  });

  it("counts the cases by group, with every step in a part that opens", async () => {
    app(<Home />);
    const chart = within(await screen.findByRole("region", { name: "Cases by status" }));
    const groups = chart.getAllByRole("listitem").slice(0, 5).map((item) => item.textContent);
    expect(groups).toEqual(["In progress3", "Staffed4", "Waiting for a person1", "Closed still short1", "System failed0"]);
    const details = chart.getByText("Every status, step by step").closest("details")!;
    expect(within(details).getByText("ASSESSING")).toBeTruthy();
    expect(within(details).getByText("SAFETY_VALIDATION")).toBeTruthy();
  });

  it("says who each ward's approvals wait for: the head nurse by ID, and the Supervisor once allowed", async () => {
    app(<Home />);
    const waiting = within(await screen.findByRole("region", { name: "Waiting for people" }));
    const rows = waiting.getAllByRole("listitem").map((item) => item.textContent);
    expect(rows).toEqual([
      "Surgery: 1 (waiting for approval from Head nurse (200001))",
      "Pediatrics: 2 (waiting for approval from Head nurse (200301) or Supervisor)",
    ]);
  });

  it("speaks Thai, with the Supervisor without an ID", async () => {
    app(<Home />, "th");
    const waiting = within(await screen.findByRole("region", { name: "สิ่งที่รอคนตอบ" }));
    expect(waiting.getAllByRole("listitem")[1].textContent).toContain("(รออนุมัติจากหัวหน้าหอ (200301) หรือ Supervisor)");
    expect(screen.getByText("ข้อมูลจำลอง (Demo)")).toBeTruthy();
    expect(screen.getByText("เวรที่ขาดคนภายใน 24 ชั่วโมง")).toBeTruthy();
  });
});

describe("who an approval waits for", () => {
  const t = translator("en");
  it.each([
    [{ ward_id: 1, count: 1, head_nurses: [], supervisor: true }, "waiting for approval from Supervisor"],
    [{ ward_id: 1, count: 1, head_nurses: [], supervisor: false }, "this ward has no head nurse; the Supervisor decides once allowed"],
    [
      { ward_id: 1, count: 1, head_nurses: [{ staff_id: 1, name: "A" }, { staff_id: 2, name: "B" }], supervisor: false },
      "waiting for approval from Head nurse (1, 2)",
    ],
    // An older Backend names nobody: no words are added
    [{ ward_id: 1, count: 1 }, null],
  ])("%o", (row, text) => {
    expect(waitingForText(row, t)).toBe(text);
  });
});

describe("the status page", () => {
  it("shows the API and the database to a visitor, even when the login cannot be checked", async () => {
    pathname = "/status";
    routes = {
      "GET /auth/config": () => ({ status: 500, body: { detail: "down" } }),
      "GET /health": () => ok({ status: "ok", database: "ok" }),
    };
    app(<StatusPage />);
    const status = within(await screen.findByRole("region", { name: "System check" }));
    expect(await status.findAllByText("ok")).toHaveLength(2);
    expect(replace).not.toHaveBeenCalled();
  });
});

const assignment = (id: number, shift: number, start: string, status = "ASSIGNED") => ({
  id,
  status,
  assignment_type: "REGULAR",
  is_unavailable: false,
  shift: {
    id: shift,
    ward_id: 1,
    ward_name: "Surgery",
    shift_type: "DAY",
    start_at: start,
    end_at: start.replace("07:00", "15:00"),
    is_active: true,
  },
});

describe("a nurse's roster", () => {
  it("lists only their own shifts, newest first, and shows everyone on the one picked", async () => {
    pathname = "/roster";
    session(STAFF, {
      "GET /roster": (url) => {
        if (url.searchParams.get("staff_id") === "201") {
          return ok({
            staff: { id: 201 },
            assignments: [
              assignment(1, 31, "2026-10-23T07:00:00+07:00", "COMPLETED"),
              assignment(2, 32, "2026-10-25T07:00:00+07:00"),
            ],
          });
        }
        const shiftId = Number(url.searchParams.get("shift_id"));
        return ok({
          shift: { id: shiftId, ward_id: 1, ward_name: "Surgery", shift_type: "DAY", start_at: "2026-10-25T07:00:00+07:00", end_at: "2026-10-25T15:00:00+07:00", is_active: true },
          assignments: [],
        });
      },
    });
    app(<RosterRoute />);
    const select = (await screen.findByLabelText("Shift")) as HTMLSelectElement;
    expect([...select.options].map((option) => option.textContent)).toEqual([
      "Surgery · shift 32 · 2026-10-25 07:00–15:00 (on the shift)",
      "Surgery · shift 31 · 2026-10-23 07:00–15:00 (completed)",
    ]);
    await waitFor(() => expect(seen).toContain("GET /roster?shift_id=32"));
    fireEvent.change(select, { target: { value: "31" } });
    await waitFor(() => expect(seen).toContain("GET /roster?shift_id=31"));
    // No ward picker: the Dashboard and the gap check are not a nurse's
    expect(seen.some((call) => call.startsWith("GET /dashboard") || call.startsWith("GET /gap"))).toBe(false);
  });
});

function offer(id: number, minute: number, status = "SENT", canAnswer = true): Offer {
  return {
    id,
    case_id: 7,
    candidate_item_id: id,
    staff_id: 201,
    proposed_shift_id: 1,
    status,
    case_status: "WAITING_RESPONSE",
    channel: "LINE",
    sent_at: `2026-10-24T20:${String(minute).padStart(2, "0")}:00+07:00`,
    response_at: null,
    expires_at: "2026-10-24T21:30:00+07:00",
    ward_id: 1,
    ward_name: "Surgery",
    shift_start_at: "2026-10-24T23:00:00+07:00",
    shift_end_at: "2026-10-25T07:00:00+07:00",
    can_accept: canAnswer,
    can_reject: canAnswer,
    blocked_reason: null,
    final_outcome: null,
    final_message: null,
    final_delivery_status: null,
    is_reserve: false,
    is_assigned: false,
    cancellation_reason: null,
  } as unknown as Offer;
}

describe("the two lists of offers", () => {
  function list(offers: Offer[]) {
    render(
      <LanguageProvider initial="en">
        <OfferList
          staffId={201}
          emptyText="none"
          api={{ load: async () => offers, respond: async () => ({}) as never }}
        />
      </LanguageProvider>,
    );
  }
  const ids = () =>
    screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0].textContent);

  it("shows the newest offer first and the ones that may still be answered apart, a page at a time", async () => {
    const open = Array.from({ length: OFFERS_PAGE_SIZE + 2 }, (_, index) => offer(index + 1, index));
    list([...open, offer(50, 59, "REJECTED", false), offer(51, 58, "TIMEOUT", false)]);
    const answerable = await screen.findByRole("button", { name: "Can answer (12)" });
    expect(answerable.getAttribute("aria-pressed")).toBe("true");
    expect(ids()).toEqual(["12", "11", "10", "9", "8", "7", "6", "5", "4", "3"]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(ids()).toEqual(["2", "1"]);
    fireEvent.click(screen.getByRole("button", { name: "Can no longer answer (2)" }));
    expect(ids()).toEqual(["50", "51"]);
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
  });

  it("opens on the history when nothing waits for an answer", async () => {
    list([offer(1, 1, "ACCEPTED", false)]);
    expect((await screen.findByRole("button", { name: "Can no longer answer (1)" })).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Can answer (0)" }));
    expect(screen.getByText("No offer is waiting for your answer.")).toBeTruthy();
  });

  it("puts the check-in above the offers on My offers", async () => {
    pathname = "/me/offers";
    session(STAFF, {
      "GET /me/offers": () => ok([offer(1, 1)]),
      "GET /me/handovers": () => ok({ active: [], history: [], next_cursor: null }),
      "GET /roster": () => ok({ staff: { id: 201 }, assignments: [] }),
    });
    app(<MyOffers />);
    const checkIn = await screen.findByRole("heading", { name: "Check in" });
    const offers = await screen.findByRole("region", { name: "Offers" });
    expect(checkIn.compareDocumentPosition(offers) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("the candidates' columns", () => {
  const headers = () => screen.getAllByRole("columnheader").map((cell) => cell.textContent);
  const base = caseDetail().candidates;

  function table(candidates: CandidateView[]) {
    render(
      <LanguageProvider initial="en">
        <CandidateTable candidates={candidates} />
      </LanguageProvider>,
    );
  }

  it("leaves out Covers and Moved from when every candidate covers the whole shift from nowhere", () => {
    table(base);
    expect(headers()).not.toContain("Covers");
    expect(headers()).not.toContain("Moved from");
  });

  it("shows Moved from as soon as one candidate is moved off a shift", () => {
    table([{ ...base[0], source_assignment: { assignment_id: 4, shift_id: 21, ward_id: 2, ward_name: "Medicine" } }, ...base.slice(1)]);
    expect(headers()).toContain("Moved from");
    expect(headers()).not.toContain("Covers");
  });
});

const person = (staff_id: number, name: string, role: string, ward: string): OverviewPerson => ({
  staff_id,
  name,
  role,
  ward_name: ward,
});
const side = (overrides: Partial<OverviewSide>): OverviewSide => ({
  side: "DESTINATION",
  ward_name: "Pediatrics",
  status: "PENDING",
  by: null,
  decided_as: null,
  reason: null,
  at: null,
  waiting_for: [],
  supervisor_from: null,
  ...overrides,
});
const moved = { shift_id: 55, ward_name: "Emergency", start_at: "2026-10-25T07:00:00+07:00", end_at: "2026-10-25T15:00:00+07:00" };

function overview(overrides: Partial<CaseOverview>): CaseOverview {
  return {
    events: [
      { event_id: 1, event_type: "STAFF_UNAVAILABLE", staff: person(200102, "Achara S.", "RN", "Pediatrics"), occurred_at: "2026-10-24T21:00:00+07:00", reason: "NO_SHOW" },
    ],
    replacements: [],
    decisions: [],
    outcome: null,
    shift: { shift_id: 34, ward_id: 2, ward_name: "Pediatrics", shift_type: "DAY", start_at: "2026-10-25T07:00:00+07:00", end_at: "2026-10-25T15:00:00+07:00" },
    requests: [],
    open_offers: 0,
    ...overrides,
  };
}

function summary(data: CaseOverview, caseStatus: string) {
  render(
    <LanguageProvider initial="en">
      <CaseOverviewCard overview={data} caseStatus={caseStatus} />
    </LanguageProvider>,
  );
  return {
    part: (name: string) => within(screen.getByRole("region", { name })),
    text: (name: string) => screen.getByRole("region", { name }).textContent ?? "",
  };
}

describe("the replacement summary", () => {
  it("says a no-show in words and waits for both wards of a move, each on its own row", () => {
    const view = summary(
      overview({
        requests: [
          {
            approval_id: 3,
            candidate: person(200202, "Tawan S.", "RN", "Emergency"),
            destination_ward_name: "Pediatrics",
            moved_from: moved,
            status: "PENDING",
            approval_mode: "MANUAL",
            assigned: false,
            requested_at: "2026-10-24T21:00:00+07:00",
            sides: [
              side({ waiting_for: [person(200101, "Nattapong W.", "HEAD_NURSE", "Pediatrics")], supervisor_from: "2026-10-24T21:10:00+07:00" }),
              side({ side: "SOURCE", ward_name: "Emergency", waiting_for: [person(200201, "Saowanee S.", "HEAD_NURSE", "Emergency")], supervisor_from: "2026-10-24T21:10:00+07:00" }),
            ],
          },
        ],
      }),
      "WAITING_APPROVAL",
    );
    expect(view.text("What happened")).toContain("Achara S.ID 200102");
    expect(view.text("What happened")).toContain("did not come to the shift");
    expect(view.text("What happened")).toContain("Day shift");
    const came = view.text("Who came instead");
    expect(came).toContain("Home ward Emergency→Helping Pediatrics");
    expect(came).toContain("Moved off Emergency shift 55 (07:00–15:00)");
    expect(came).toContain("Accepted, waiting for approval");
    const rows = view.part("Who approved").getAllByRole("listitem").map((row) => row.textContent ?? "");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("Head nurse of the destination ward · Pediatrics");
    expect(rows[0]).toContain("Waiting for Nattapong W. (200101) or the Supervisor from 2026-10-24 21:10");
    expect(rows[1]).toContain("Head nurse of the source ward · Emergency");
    expect(rows[1]).toContain("Waiting for Saowanee S. (200201)");
    expect(view.text("Who approved")).toContain("Two wards must approve");
  });

  it("names one Supervisor once when they decided both wards", () => {
    const supervisor = person(950, "Supa S.", "SUPERVISOR", "ICU");
    const decided = { status: "APPROVED" as const, by: supervisor, decided_as: "SUPERVISOR" as const, at: "2026-10-24T21:12:00+07:00" };
    const view = summary(
      overview({
        replacements: [{ staff: person(200202, "Tawan S.", "RN", "Emergency"), how: "TRANSFERRED", at: "2026-10-24T21:12:00+07:00" }],
        requests: [
          {
            approval_id: 3,
            candidate: person(200202, "Tawan S.", "RN", "Emergency"),
            destination_ward_name: "Pediatrics",
            moved_from: moved,
            status: "APPROVED",
            approval_mode: "MANUAL",
            assigned: true,
            requested_at: "2026-10-24T21:00:00+07:00",
            sides: [side(decided), side({ ...decided, side: "SOURCE", ward_name: "Emergency" })],
          },
        ],
      }),
      "RESOLVED",
    );
    const rows = view.part("Who approved").getAllByRole("listitem").map((row) => row.textContent ?? "");
    expect(rows).toHaveLength(1);
    expect(rows[0]).toContain("Both wards, decided by one person");
    expect(rows[0]).toContain("Supa S.ID 950Supervisor");
    expect(view.text("Who came instead")).toContain("Moved, approved by both wards");
  });

  it("keeps two replacements apart, each with its own approval, and a refused move with its reason", () => {
    const head = person(200101, "Nattapong W.", "HEAD_NURSE", "Pediatrics");
    const view = summary(
      overview({
        replacements: [
          { staff: person(200112, "Kamon P.", "RN", "Pediatrics"), how: "APPROVED", at: "2026-10-24T21:05:00+07:00" },
          { staff: person(200304, "Manee T.", "RN", "Orthopedics"), how: "MANUAL", at: "2026-10-24T21:20:00+07:00" },
        ],
        decisions: [
          { kind: "MANUAL_ASSIGNMENT", by: head, ward_name: null, side: null, candidate: person(200304, "Manee T.", "RN", "Orthopedics"), reason: "Called in", at: "2026-10-24T21:20:00+07:00" },
        ],
        requests: [
          {
            approval_id: 4,
            candidate: person(200409, "Wilai B.", "RN", "Cardiology"),
            destination_ward_name: "Pediatrics",
            moved_from: { ...moved, ward_name: "Cardiology" },
            status: "REJECTED",
            approval_mode: "MANUAL",
            assigned: false,
            requested_at: "2026-10-24T21:00:00+07:00",
            sides: [
              side({ status: "APPROVED", by: head, decided_as: "HEAD_NURSE", at: "2026-10-24T21:01:00+07:00" }),
              side({ side: "SOURCE", ward_name: "Cardiology", status: "REJECTED", by: person(200401, "Boonmee S.", "HEAD_NURSE", "Cardiology"), decided_as: "HEAD_NURSE", reason: "We cannot spare a nurse", at: "2026-10-24T21:02:00+07:00" }),
            ],
          },
          {
            approval_id: 5,
            candidate: person(200112, "Kamon P.", "RN", "Pediatrics"),
            destination_ward_name: "Pediatrics",
            moved_from: null,
            status: "APPROVED",
            approval_mode: "MANUAL",
            assigned: true,
            requested_at: "2026-10-24T21:03:00+07:00",
            sides: [side({ status: "APPROVED", by: head, decided_as: "HEAD_NURSE", at: "2026-10-24T21:05:00+07:00" })],
          },
        ],
      }),
      "RESOLVED",
    );
    const came = view.part("Who came instead");
    expect(came.getAllByText(/Accepted and approved|Put on the shift by hand/).map((badge) => badge.textContent)).toEqual([
      "Accepted and approved",
      "Put on the shift by hand",
    ]);
    // A nurse of the ward helps their own ward: no route, and "moved" only for a real move
    expect(view.text("Who came instead")).not.toContain("Helping Pediatrics→");
    expect(view.text("Who came instead")).toContain("Helping Pediatrics");
    expect(view.text("Who came instead")).not.toContain("Moved off");
    const approvals = view.text("Who approved");
    expect(approvals).toContain("Wilai B.ID 200409");
    expect(approvals).toContain("“We cannot spare a nurse”");
    expect(approvals).toContain("Not approved");
    expect(approvals).toContain("Head nurse of Pediatrics");
    expect(approvals).toContain("put Manee T. (200304) on the shift");
  });

  it("says what the case does while nobody came, and why a closed case stopped", () => {
    const first = summary(overview({ open_offers: 3 }), "WAITING_RESPONSE");
    expect(first.text("Who came instead")).toContain("Offers sent to 3 people, waiting for their answers");
    expect(first.part("Who came instead").getByRole("link", { name: "See the candidates" }).getAttribute("href")).toBe("#candidates");
    cleanup();
    const closed = summary(
      overview({
        outcome: { kind: "CLOSED_UNRESOLVED", reason: "Nobody could come", by: person(200201, "Saowanee S.", "HEAD_NURSE", "Emergency"), at: "2026-10-24T21:30:00+07:00" },
      }),
      "UNRESOLVED",
    );
    const why = closed.part("Why it stopped");
    expect(why.getByText(/Closed without a replacement/).textContent).toContain("“Nobody could come”");
    expect(why.getByText("Details").closest("details")?.open).toBe(false);
    expect(closed.part("Who came instead").queryByRole("link", { name: "See the candidates" })).toBeNull();
  });
});

describe("Manage on the case list", () => {
  const row = (id: number, status: string) => ({
    id,
    status,
    shift_id: 21,
    ward_id: 1,
    ward_name: "Surgery",
    shift_type: "NIGHT",
    shift_start_at: "2026-10-24T23:00:00+07:00",
    required_replacement_time: "2026-10-24T23:00:00+07:00",
    created_at: "2026-10-24T21:00:00+07:00",
    headcount_gap: 1,
    assigned_count: 0,
    can_manage: status === "MANUAL_HANDOFF",
  });

  it("opens the dialog of the Handoff page, staffs the case and says so on the list", async () => {
    pathname = "/cases";
    let staffed = false;
    session(HEAD, {
      "GET /cases/search": () => ok({ items: [row(9, staffed ? "RESOLVED" : "MANUAL_HANDOFF"), row(8, "RESOLVED")], total: 2, page: 1, page_size: 20 }),
      "GET /cases/9/handoff/candidates": () =>
        ok([{ staff_id: 202, first_name: "Phanu", last_name: "Demo", role_name: "RN", blocking_rules: [], other_case_ids: [] }]),
      "POST /cases/9/handoff/assignments": (_, body) => {
        staffed = true;
        expect(body).toEqual({ staff_id: 202 });
        return ok({ case_id: 9, staff_id: 202, case_status: "RESOLVED", cancelled_outreach_ids: [] });
      },
    });
    app(<CaseList />);
    const table = within(await screen.findByRole("table", { name: "Cases" }));
    fireEvent.click(table.getByRole("button", { name: "Manage" }));
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.click(await dialog.findByRole("button", { name: "Assign" }));
    expect(await screen.findByText(/Staff 202 assigned. Case 9: RESOLVED/)).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the dialog open when newer cases push its case to the next page (review of #147)", async () => {
    pathname = "/cases";
    // Newer cases arrive: case 9 is no longer on the first page, but still MANUAL_HANDOFF
    let pushedOff = false;
    let resolved = false;
    session(HEAD, {
      "GET /cases/search": (url) => {
        if (url.searchParams.get("q") === "9") {
          // The case's own row, read by its ID
          return ok({ items: [row(9, resolved ? "RESOLVED" : "MANUAL_HANDOFF")], total: 1, page: 1, page_size: 100 });
        }
        const items = pushedOff ? [row(31, "WAITING_RESPONSE"), row(30, "WAITING_RESPONSE")] : [row(9, "MANUAL_HANDOFF")];
        return ok({ items, total: pushedOff ? 22 : 1, page: 1, page_size: 20 });
      },
      "GET /cases/9/handoff/candidates": () =>
        ok([{ staff_id: 202, first_name: "Phanu", last_name: "Demo", role_name: "RN", blocking_rules: [], other_case_ids: [] }]),
    });
    app(<CaseList />);
    fireEvent.click(await screen.findByRole("button", { name: "Manage" }));
    const dialog = await screen.findByRole("dialog", { name: "Manage case 9" });
    fireEvent.change(within(dialog).getByLabelText("Note for the assignment (optional)"), { target: { value: "kept" } });

    pushedOff = true;
    await waitFor(() => expect(seen).toContain("GET /cases/search?q=9&page=1&page_size=100"), { timeout: 5000 });
    await waitFor(() => expect(screen.getByRole("table", { name: "Cases" }).textContent).toContain("31"), { timeout: 5000 });
    // Still open, with what was typed: the row of case 9 says it can be managed
    expect(screen.getByRole("dialog", { name: "Manage case 9" })).toBeTruthy();
    expect((screen.getByLabelText("Note for the assignment (optional)") as HTMLInputElement).value).toBe("kept");
    expect(screen.queryByText("Case 9 is no longer handed off.")).toBeNull();

    // Someone else staffed it: its own row says so, and only then the dialog closes
    resolved = true;
    expect(await screen.findByText("Case 9 can no longer be managed: it is now RESOLVED.", {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers no Manage button to a nurse", async () => {
    pathname = "/cases";
    session(STAFF, {
      "GET /cases/search": () => ok({ items: [row(9, "MANUAL_HANDOFF")], total: 1, page: 1, page_size: 20 }),
    });
    app(<CaseList />);
    const table = within(await screen.findByRole("table", { name: "Cases" }));
    expect(table.queryByRole("button", { name: "Manage" })).toBeNull();
    expect(table.getByRole("link", { name: "See details" })).toBeTruthy();
  });
});
