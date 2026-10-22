// @vitest-environment jsdom
// The pages that used to ask "who are you acting as" in session mode (round 6 PR AU3,
// docs/workflow.md 6.33): the person is the one logged in, the choice is gone, and no
// X-Demo-User travels. The Backend is a stub of fetch; the pages and the API layer are real.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Approvals from "@/app/approvals/page";
import LineSimulator from "@/app/demo/line-sim/page";
import Home from "@/app/page";
import MyOffers from "@/app/me/offers/page";
import { AuthGate, AuthProvider } from "@/components/AuthProvider";
import { setSessionMode } from "@/lib/api";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import { dashboard, withCounts } from "../../fixtures/dashboard";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

const calls: { path: string; headers: Headers; credentials?: RequestCredentials }[] = [];

const PENDING = {
  id: 4,
  case_id: 7,
  candidate_item_id: 11,
  required_approver_role: 2,
  approval_mode: "MANUAL",
  is_pending: true,
  staff_id: 201,
  proposed_shift_id: 1,
  requested_at: "2026-10-09T21:00:00+07:00",
  expires_at: "2026-10-09T21:15:00+07:00",
  home_ward_id: 1,
  source_ward_id: null,
  wards: [{ ward_id: 1, side: "DESTINATION", status: "PENDING" }],
  supervisor_from: "2026-10-09T21:10:00+07:00",
};

function login(me: { staff_id: number; role: string; home_ward_id: number }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      calls.push({ path: url.pathname + url.search, headers: new Headers(init.headers), credentials: init.credentials });
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url.pathname === "/auth/config") return json({ auth_mode: "session" });
      if (url.pathname === "/auth/me") return json({ ...me, must_change_password: false });
      if (url.pathname === "/clock") return json({ now: "2026-10-22T09:00:00+07:00", frozen: false, date: "2026-10-22" });
      if (url.pathname === "/health") return json({ status: "ok", database: "ok" });
      if (url.pathname === "/dashboard") {
        return json(dashboard({ wards: [me.home_ward_id], cases_by_status: withCounts({}), pending_approvals: [] }));
      }
      if (url.pathname === "/approvals") return json([PENDING]);
      if (url.pathname === "/approvals/auto") return json([]);
      if (/^\/cases\/\d+$/.test(url.pathname)) return json({ id: 7, gap: { headcount_gap: 2 }, assigned_count: 1 });
      if (url.pathname === "/me/handovers") return json({ active: [], history: [], next_cursor: null });
      if (url.pathname === "/roster") return json({ staff: {}, assignments: [] });
      return json([]);
    }),
  );
}

/** As the root layout has it: the page is held back until the Backend said who the user is. */
function app(element: ReactElement) {
  return render(
    <LanguageProvider initial="en">
      <AuthProvider>
        <AuthGate>{element}</AuthGate>
      </AuthProvider>
    </LanguageProvider>,
  );
}

beforeEach(() => {
  calls.length = 0;
});
afterEach(() => {
  cleanup();
  setSessionMode(false);
  vi.unstubAllGlobals();
});

const pageCalls = () => calls.filter((call) => !["/auth/config", "/auth/me", "/clock", "/health"].includes(call.path));

describe("Dashboard with a login", () => {
  it("reads as the person logged in, shows no 'Viewing as' choice and sends no X-Demo-User", async () => {
    login({ staff_id: 900, role: "head_nurse", home_ward_id: 1 });
    app(<Home />);
    await waitFor(() => expect(calls.some((call) => call.path === "/dashboard")).toBe(true));
    expect(screen.queryByLabelText(/Viewing as/)).toBeNull();
    const read = calls.find((call) => call.path === "/dashboard")!;
    expect(read.headers.has("X-Demo-User")).toBe(false);
    expect(read.credentials).toBe("include");
  });
});

describe("Approvals with a login", () => {
  it("lets a head nurse decide a side of their own ward", async () => {
    login({ staff_id: 900, role: "head_nurse", home_ward_id: 1 });
    app(<Approvals />);
    const approve = await screen.findByRole<HTMLButtonElement>("button", { name: "Approve" });
    expect(approve.disabled).toBe(false);
    expect(screen.queryByLabelText(/Acting as/)).toBeNull();
  });

  it("shows a head nurse of another ward the request with its buttons off", async () => {
    login({ staff_id: 902, role: "head_nurse", home_ward_id: 2 });
    app(<Approvals />);
    await screen.findByRole("link", { name: "7" });
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Approve" }).disabled).toBe(true);
  });

  it("lets a supervisor decide any ward", async () => {
    login({ staff_id: 950, role: "supervisor", home_ward_id: 3 });
    app(<Approvals />);
    const approve = await screen.findByRole<HTMLButtonElement>("button", { name: "Approve" });
    expect(approve.disabled).toBe(false);
  });
});

describe("My offers with a login", () => {
  it("opens as the person logged in, with no demo sign-in and no demo sign-out", async () => {
    login({ staff_id: 201, role: "staff", home_ward_id: 1 });
    app(<MyOffers />);
    await waitFor(() => expect(calls.some((call) => call.path === "/me/offers")).toBe(true));
    expect(screen.queryByText(/Demo sign-in/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
    for (const call of pageCalls()) expect(call.headers.has("X-Demo-User")).toBe(false);
  });

  it("takes the shifts to check in to from the roster of the person", async () => {
    login({ staff_id: 201, role: "staff", home_ward_id: 1 });
    app(<MyOffers />);
    await waitFor(() => expect(calls.some((call) => call.path === "/roster?staff_id=201")).toBe(true));
    expect(await screen.findByText("You have no shift to check in to.")).toBeTruthy();
  });
});

describe("LINE simulator with a login", () => {
  it("answers only as the person logged in: no choice of staff, the staff_id is their own", async () => {
    login({ staff_id: 201, role: "staff", home_ward_id: 1 });
    app(<LineSimulator />);
    await waitFor(() => expect(calls.some((call) => call.path === "/demo/line-sim/offers?staff_id=201")).toBe(true));
    expect(screen.queryByLabelText("Staff member")).toBeNull();
    expect(screen.getByText("You answer as the person who is logged in.")).toBeTruthy();
    expect(calls.find((call) => call.path.startsWith("/demo/line-sim"))!.headers.has("X-Demo-User")).toBe(false);
  });
});
