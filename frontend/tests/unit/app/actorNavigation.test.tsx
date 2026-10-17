// @vitest-environment jsdom
// The Dashboard links open the next page for the user the Dashboard was looking as
// (round 6 PR F2 review). The destination is rendered from the link it was given and the
// request it makes is checked: the identity it sends, not only the href.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Approvals from "@/app/approvals/page";
import GapCheck from "@/app/gap/page";
import Handoff from "@/app/handoff/page";
import Home from "@/app/page";
import { apiRequest } from "@/lib/api";
import { dashboard, withCounts } from "../../fixtures/dashboard";

let params = new URLSearchParams();
vi.mock("next/navigation", () => ({ useSearchParams: () => params }));
vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  const apiRequest = vi.fn();
  return {
    ...original,
    apiRequest,
    createDemoApi:
      (demoUser: number) =>
      (path: string, options: Omit<import("@/lib/api").ApiOptions, "demoUser"> = {}) =>
        apiRequest(path, { ...options, demoUser }),
  };
});
const request = vi.mocked(apiRequest);

const HANDED_OFF = {
  id: 7,
  status: "MANUAL_HANDOFF",
  shift_id: 21,
  ward_id: 2,
  required_replacement_time: "2026-10-17T23:00:00+07:00",
  created_at: "2026-10-17T21:00:00+07:00",
  headcount_gap: 1,
  assigned_count: 0,
  can_manage: true,
};

beforeEach(() => {
  request.mockReset();
  params = new URLSearchParams();
  request.mockImplementation(async <T,>(path: string) => {
    if (path === "/health") return { status: "ok", database: "ok" } as T;
    if (path === "/dashboard") {
      return dashboard({
        wards: [1, 2],
        cases_by_status: withCounts({ MANUAL_HANDOFF: 1, FAILED: 1, WAITING_APPROVAL: 1 }),
        pending_approvals: [{ ward_id: 2, count: 1 }],
      }) as T;
    }
    if (path.startsWith("/cases?")) return [HANDED_OFF] as T;
    return [] as T;
  });
});
afterEach(() => cleanup());

/** The Dashboard as `actorId`, and every link it offers to a page that acts or looks as a user. */
async function linksOf(actorId: number): Promise<string[]> {
  render(<Home />);
  fireEvent.change(await screen.findByLabelText(/Viewing as/), { target: { value: String(actorId) } });
  const counts = within(await screen.findByRole("region", { name: "Cases by status" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("/dashboard", expect.objectContaining({ demoUser: actorId })));
  const hrefs = [
    counts.getByRole("link", { name: "MANUAL_HANDOFF" }),
    counts.getByRole("link", { name: "FAILED" }),
    counts.getByRole("link", { name: "WAITING_APPROVAL" }),
    within(await screen.findByRole("region", { name: "Waiting for people" })).getByRole("link", { name: "1" }),
    within(await screen.findByRole("region", { name: "Short shifts" })).getByRole("link", { name: "Gap check" }),
  ].map((link) => link.getAttribute("href") ?? "");
  cleanup();
  return hrefs;
}

const PAGES: Record<string, () => ReactElement> = {
  "/handoff": () => <Handoff />,
  "/approvals": () => <Approvals />,
  "/gap": () => <GapCheck />,
};

/** Open a link the way the browser would: the page gets the query of the link. */
function open(href: string) {
  const url = new URL(href, "http://nara.test");
  params = url.searchParams;
  const page = PAGES[url.pathname];
  if (!page) throw new Error(`No page for ${href}`);
  request.mockClear();
  render(page());
}

describe("Dashboard links keep the user they were opened for", () => {
  it.each([[902], [950]])("opens every destination as user %i", async (actorId) => {
    const hrefs = await linksOf(actorId);
    expect(hrefs).toHaveLength(5);

    for (const href of hrefs) {
      open(href);
      const path = new URL(href, "http://nara.test").pathname;
      await waitFor(() => expect(request).toHaveBeenCalled());
      // Every request of the destination is made as the chosen user, never the default 900
      const users = request.mock.calls.map(([, options]) => (options as { demoUser?: number }).demoUser);
      expect(users.length).toBeGreaterThan(0);
      expect(new Set(users), `${path} for ${actorId}`).toEqual(new Set([actorId]));
      if (path === "/handoff") {
        expect(request).toHaveBeenCalledWith(
          "/cases?status=MANUAL_HANDOFF,FAILED",
          expect.objectContaining({ demoUser: actorId }),
        );
      }
      if (path === "/approvals") {
        expect(request).toHaveBeenCalledWith("/approvals?pending=true", expect.objectContaining({ demoUser: actorId }));
      }
      // The selector shows the same user, so the page does not claim to be someone else
      expect((screen.getByLabelText(/Viewing as|Acting as/) as HTMLSelectElement).value).toBe(String(actorId));
      cleanup();
    }
  });

  it.each([["", 900], ["?as=abc", 900], ["?as=101", 900], ["?as=902", 902]])(
    "Handoff opens as %j for user %i, and only the demo head nurses and Supervisor are accepted",
    async (query, actorId) => {
      params = new URLSearchParams(query);
      render(<Handoff />);
      await waitFor(() =>
        expect(request).toHaveBeenCalledWith(
          "/cases?status=MANUAL_HANDOFF,FAILED",
          expect.objectContaining({ demoUser: actorId }),
        ),
      );
    },
  );

  it("Handoff: changing the user reads that user's list and closes the open case", async () => {
    params = new URLSearchParams("?as=902");
    render(<Handoff />);
    fireEvent.click(await screen.findByRole("button", { name: "Manage" }));
    expect(await screen.findByRole("region", { name: "Manage case 7" })).toBeTruthy();

    request.mockClear();
    fireEvent.change(screen.getByLabelText(/Viewing as/), { target: { value: "950" } });

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "/cases?status=MANUAL_HANDOFF,FAILED",
        expect.objectContaining({ demoUser: 950 }),
      ),
    );
    expect(screen.queryByRole("region", { name: "Manage case 7" })).toBeNull();
    // Nothing of the first user's case is asked for as the new user
    expect(request.mock.calls.some(([path]) => String(path).includes("/handoff/"))).toBe(false);
  });
});
