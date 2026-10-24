// @vitest-environment jsdom
// Round 6 PR EV7 (docs/workflow.md 6.37): the page guard of each role, the password that can be
// shown, the bell of the work that waits, and the top of the case page. The Backend is a stub of
// fetch; the provider, the gate and the API layer are the real ones.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthGate, AuthProvider, useAuth } from "@/components/AuthProvider";
import { CaseOverviewCard } from "@/components/case/CaseOverviewCard";
import { Alerts, newAlertGeneration } from "@/components/layout/Alerts";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { setSessionMode } from "@/lib/api";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import { roleMayOpen } from "@/lib/routeAccess";
import type { CaseOverview } from "@/lib/types/case";

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
let routes: Record<string, () => Reply> = {};

const STAFF = { staff_id: 201, role: "staff", home_ward_id: 1, must_change_password: false };
const HEAD = { staff_id: 900, role: "head_nurse", home_ward_id: 1, must_change_password: false };

function session(me: unknown, extra: Record<string, () => Reply> = {}) {
  routes = {
    "GET /auth/config": () => ({ status: 200, body: { auth_mode: "session" } }),
    "GET /auth/me": () => ({ status: 200, body: me }),
    ...extra,
  };
}

beforeEach(() => {
  replace.mockReset();
  pathname = "/";
  window.sessionStorage.clear();
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      const handler = routes[`${init.method ?? "GET"} ${url.pathname}`];
      if (!handler) return new Response(JSON.stringify({ detail: "no stub" }), { status: 599 });
      const reply = handler();
      return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), { status: reply.status });
    }),
  );
});
afterEach(() => {
  cleanup();
  setSessionMode(false);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function app(element: ReactElement) {
  return render(
    <LanguageProvider initial="en">
      <AuthProvider>{element}</AuthProvider>
    </LanguageProvider>,
  );
}

describe("pages each role may open", () => {
  it.each([
    ["/approvals", "staff", false],
    ["/handoff", "staff", false],
    ["/demo/control", "staff", false],
    ["/demo/test-runs/", "staff", false],
    ["/admin/staff", "head_nurse", false],
    ["/admin/staff", "supervisor", true],
    ["/handoff", "head_nurse", true],
    ["/cases/7", "staff", true],
    // Round 6 PR EV8: a nurse has the cases, the roster, their offers and their leave only
    ["/demo/line-sim", "staff", false],
    ["/", "staff", false],
    ["/gap", "staff", false],
    ["/roster", "staff", true],
    ["/me/offers", "staff", true],
    ["/me/leave", "staff", true],
    ["/status", "staff", true],
    ["/", "head_nurse", true],
    ["/demo/line-sim", "supervisor", true],
  ] as const)("%s for %s: %s", (path, role, allowed) => {
    expect(roleMayOpen(path, role)).toBe(allowed);
  });

  it("sends a nurse who types the address of Approvals back to their offers, without a word", async () => {
    session(STAFF);
    pathname = "/approvals";
    app(
      <AuthGate>
        <p>approvals page</p>
      </AuthGate>,
    );

    // A nurse has no Dashboard: their home page is My offers (round 6 PR EV8)
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/me/offers"));
    expect(screen.queryByText("approvals page")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("lets a head nurse open the Handoff page", async () => {
    session(HEAD);
    pathname = "/handoff";
    app(
      <AuthGate>
        <p>handoff page</p>
      </AuthGate>,
    );

    expect(await screen.findByText("handoff page")).toBeTruthy();
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("a password that can be shown", () => {
  it("shows what was typed and hides it again", () => {
    render(
      <LanguageProvider initial="en">
        <label htmlFor="pw">Password</label>
        <PasswordInput id="pw" defaultValue="secret value" />
      </LanguageProvider>,
    );
    const field = screen.getByLabelText<HTMLInputElement>("Password");
    expect(field.type).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "Show the password" }));
    expect(field.type).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "Hide the password" }));
    expect(field.type).toBe("password");
  });
});

describe("the bell of the work that waits", () => {
  const handoff = {
    id: 7,
    status: "MANUAL_HANDOFF",
    shift_id: 1,
    ward_id: 1,
    ward_name: "ICU",
    created_at: "2026-10-09T21:00:00+07:00",
  };
  const page = (items: unknown[], total = items.length) => ({
    status: 200,
    body: { items, total, page: 1, page_size: 20 },
  });
  const wait = () =>
    act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

  it("counts the handed-off cases and the approvals, and pops a toast once", async () => {
    session(HEAD, {
      "GET /cases/search": () => ({ status: 200, body: { items: [handoff], total: 1, page: 1, page_size: 20 } }),
      "GET /approvals": () => ({
        status: 200,
        body: [{ id: 3, case_id: 8, staff_id: 201, requested_at: "2026-10-09T21:02:00+07:00" }],
      }),
    });
    app(<Alerts />);

    const bell = await screen.findByRole("button", { name: "Work waiting for you: 2" });
    expect(within(bell).getByText("2")).toBeTruthy();
    const toasts = await screen.findAllByRole("status");
    expect(toasts.map((toast) => toast.textContent)).toEqual([
      "Case 7 needs a person: nobody could be found✕",
      "Staff 201 waits for your approval (case 8)✕",
    ]);
    fireEvent.click(bell);
    expect(screen.getAllByRole("link", { name: /Case 7 needs a person/ })[0].getAttribute("href")).toBe("/cases/7");

    // The same alerts pop up only once in a tab
    cleanup();
    app(<Alerts />);
    await screen.findByRole("button", { name: "Work waiting for you: 2" });
    await wait();
    expect(screen.queryAllByRole("status")).toEqual([]);
  });

  it("pops a toast again for a reused case ID after a reset", async () => {
    session(HEAD, { "GET /cases/search": () => page([handoff]), "GET /approvals": () => ({ status: 200, body: [] }) });
    app(<Alerts />);
    expect(await screen.findAllByRole("status")).toHaveLength(1);

    // A reset starts the IDs again, and the clock is at the same time: case 7 is a new case
    cleanup();
    newAlertGeneration();
    app(<Alerts />);
    expect(await screen.findAllByRole("status")).toHaveLength(1);
  });

  it("watches the newest handed-off cases and links to the full lists", async () => {
    const search = vi.fn(() => page([handoff], 25));
    session(HEAD, { "GET /cases/search": search, "GET /approvals": () => ({ status: 200, body: [] }) });
    app(<Alerts />);

    fireEvent.click(await screen.findByRole("button", { name: "Work waiting for you: 25" }));
    const calls = vi.mocked(fetch).mock.calls.map(([input]) => String(input));
    expect(calls.some((url) => url.includes("/cases/search?") && url.includes("sort=newest"))).toBe(true);
    expect(screen.getByRole("link", { name: "All handed-off cases (25)" }).getAttribute("href")).toBe("/handoff");
    expect(screen.getByRole("link", { name: "All approvals (0)" }).getAttribute("href")).toBe("/approvals");
  });

  it("leaves nothing of the account before after a logout and another login", async () => {
    const OTHER = { ...HEAD, staff_id: 902, home_ward_id: 2 };
    let me: unknown = HEAD;
    let items: unknown[] = [handoff];
    session(HEAD, {
      "GET /auth/me": () => ({ status: 200, body: me }),
      "POST /auth/logout": () => ({ status: 204 }),
      "POST /auth/login": () => ({ status: 200, body: OTHER }),
      "GET /cases/search": () => page(items),
      "GET /approvals": () => ({ status: 200, body: [] }),
    });
    let auth: ReturnType<typeof useAuth> | undefined;
    function Grab() {
      auth = useAuth();
      return null;
    }
    app(
      <>
        <Grab />
        <Alerts />
      </>,
    );
    expect(await screen.findAllByRole("status")).toHaveLength(1);

    // 902 has nothing waiting: the toast of 900 must not stay on the screen
    items = [];
    me = OTHER;
    await act(async () => {
      await auth?.logout();
    });
    await act(async () => {
      await auth?.login(902, "a password of 902");
    });
    await screen.findByRole("button", { name: "Work waiting for you: 0" });
    await wait();
    expect(screen.queryAllByRole("status")).toEqual([]);

    // The cases 900 saw are new to 902: the seen list is each account's own
    items = [handoff];
    cleanup();
    app(<Alerts />);
    expect(await screen.findAllByRole("status")).toHaveLength(1);
  });

  it("is not there for a nurse", async () => {
    session(STAFF);
    app(<Alerts />);

    await wait();
    expect(screen.queryByRole("button", { name: /Work waiting/ })).toBeNull();
  });
});

describe("the top of the case page", () => {
  const person = (staff_id: number, name: string, role: string, ward: string) => ({
    staff_id,
    name,
    role,
    ward_name: ward,
  });
  const overview: CaseOverview = {
    events: [
      { event_id: 4, event_type: "STAFF_UNAVAILABLE", staff: person(105, "Sudarat Demo", "RN", "ICU"), occurred_at: "2026-10-09T21:00:00+07:00" },
    ],
    replacements: [{ staff: person(301, "Niran Demo", "RN", "Medicine"), how: "TRANSFERRED", at: "2026-10-09T21:05:00+07:00" }],
    decisions: [
      { kind: "APPROVED", by: person(900, "Malai Demo", "HEAD_NURSE", "ICU"), ward_name: "ICU", side: "DESTINATION", candidate: person(301, "Niran Demo", "RN", "Medicine"), reason: null, at: "2026-10-09T21:03:00+07:00" },
      { kind: "APPROVED", by: person(902, "Ratana Demo", "HEAD_NURSE", "Medicine"), ward_name: "Medicine", side: "SOURCE", candidate: person(301, "Niran Demo", "RN", "Medicine"), reason: null, at: "2026-10-09T21:04:00+07:00" },
    ],
    outcome: null,
  };

  it("says who left, who came, and who decided for each ward", () => {
    render(
      <LanguageProvider initial="en">
        <CaseOverviewCard
          caseStatus="RESOLVED"
          overview={{
            ...overview,
            shift: { shift_id: 1, ward_id: 1, ward_name: "ICU", shift_type: "NIGHT", start_at: "2026-10-09T23:00:00+07:00", end_at: "2026-10-10T07:00:00+07:00" },
            requests: [
              {
                approval_id: 3,
                candidate: person(301, "Niran Demo", "RN", "Medicine"),
                destination_ward_name: "ICU",
                moved_from: { shift_id: 21, ward_name: "Medicine", start_at: "2026-10-09T23:00:00+07:00", end_at: "2026-10-10T07:00:00+07:00" },
                status: "APPROVED",
                approval_mode: "MANUAL",
                assigned: true,
                requested_at: "2026-10-09T21:02:00+07:00",
                sides: [
                  { side: "DESTINATION", ward_name: "ICU", status: "APPROVED", by: person(900, "Malai Demo", "HEAD_NURSE", "ICU"), decided_as: "HEAD_NURSE", reason: null, at: "2026-10-09T21:03:00+07:00", waiting_for: [], supervisor_from: null },
                  { side: "SOURCE", ward_name: "Medicine", status: "APPROVED", by: person(902, "Ratana Demo", "HEAD_NURSE", "Medicine"), decided_as: "HEAD_NURSE", reason: null, at: "2026-10-09T21:04:00+07:00", waiting_for: [], supervisor_from: null },
                ],
              },
            ],
          }}
        />
      </LanguageProvider>,
    );

    // Round 6 PR EV8: the replacement summary, in three parts
    const card = within(screen.getByRole("region", { name: "Replacement summary" }));
    const what = card.getByRole("region", { name: "What happened" }).textContent ?? "";
    expect(what).toContain("Sudarat Demo");
    expect(what).toContain("ID 105");
    expect(what).toContain("reported being unable to work the shift");
    expect(what).toContain("Night shift");
    const came = card.getByRole("region", { name: "Who came instead" }).textContent ?? "";
    expect(came).toContain("Niran Demo");
    expect(came).toContain("Home ward Medicine");
    expect(came).toContain("Helping ICU");
    expect(came).toContain("Moved off Medicine shift 21");
    expect(came).toContain("Moved, approved by both wards");
    const approved = within(card.getByRole("region", { name: "Who approved" }));
    const rows = approved.getAllByRole("listitem").map((item) => item.textContent ?? "");
    expect(rows[0]).toContain("Head nurse of the destination ward · ICU");
    expect(rows[0]).toContain("Malai Demo");
    expect(rows[0]).toContain("ID 900");
    expect(rows[0]).toContain("Approved");
    expect(rows[1]).toContain("Head nurse of the source ward · Medicine");
    expect(rows[1]).toContain("Ratana Demo");
  });

  it("says why a case stopped, with the reason in words", () => {
    render(
      <LanguageProvider initial="th">
        <CaseOverviewCard
          caseStatus="MANUAL_HANDOFF"
          overview={{
            ...overview,
            replacements: [],
            decisions: [],
            outcome: { kind: "MANUAL_HANDOFF", reason: "WAVE_LIMIT_REACHED", by: null, at: "2026-10-09T22:00:00+07:00" },
          }}
        />
      </LanguageProvider>,
    );

    const why = screen.getByRole("region", { name: "เหตุที่เคสหยุด" }).textContent ?? "";
    expect(why).toContain("ส่งต่อให้คนจัดการ: ส่ง Offer ครบรอบสุดท้ายที่อนุญาตแล้ว");
    // Nobody came: the step the case is at, and the way to its candidates
    const came = within(screen.getByRole("region", { name: "ใครมาแทน" }));
    expect(came.getByText("รอหัวหน้าหอหรือ Supervisor จัดคนเอง")).toBeTruthy();
    expect(came.getByRole("link", { name: "ดูผู้สมัคร" }).getAttribute("href")).toBe("#candidates");
  });
});
