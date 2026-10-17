// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MyOffersPage from "@/app/me/offers/page";
import { ApiError, apiRequest } from "@/lib/api";
import { DEMO_SIGNED_IN_STORAGE_KEY } from "@/lib/demo";
import type { Offer } from "@/lib/types/outreach";

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  const apiRequest = vi.fn();
  return {
    ...original,
    apiRequest,
    createDemoApi:
      (demoUser: number) =>
      (
        path: string,
        options: Omit<import("@/lib/api").ApiOptions, "demoUser"> = {},
      ) =>
        apiRequest(path, { ...options, demoUser }),
  };
});
const request = vi.mocked(apiRequest);
const offer: Offer = {
  id: 1,
  case_id: 7,
  candidate_item_id: 2,
  staff_id: 202,
  proposed_shift_id: 1,
  status: "SENT",
  case_status: "WAITING_RESPONSE",
  channel: "LINE",
  sent_at: "2026-10-09T21:00:00+07:00",
  response_at: null,
  expires_at: "2026-10-09T21:05:00+07:00",
  ward_id: 1,
  ward_name: "ICU",
  shift_start_at: "2026-10-09T23:00:00+07:00",
  shift_end_at: "2026-10-10T07:00:00+07:00",
  can_accept: true,
  can_reject: true,
  blocked_reason: null,
  cancellation_reason: null,
  is_assigned: false,
  is_reserve: false,
};

beforeEach(() => {
  request.mockReset();
  window.localStorage.clear();
});
afterEach(() => cleanup());

function replies(handler: (path: string) => unknown) {
  request.mockImplementation(async <T,>(path: string) => {
    const result = handler(path);
    if (result instanceof Error) throw result;
    // Tests concerned with offers/check-in use an empty handover page.
    if (path === "/me/handovers" && Array.isArray(result)) {
      return { active: [], history: [], next_cursor: null } as T;
    }
    return result as T;
  });
}

async function signInAs(staffId: number) {
  fireEvent.change(await screen.findByLabelText("Staff member"), {
    target: { value: String(staffId) },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in (demo)" }));
}

/** Every path this page asked the API for. */
function requestedPaths(): string[] {
  return request.mock.calls.map(([path]) => path);
}

describe("My shift offers", () => {
  it("asks for a demo sign-in first and calls no API before it", async () => {
    replies(() => [offer]);
    render(<MyOffersPage />);
    expect(await screen.findByRole("button", { name: "Sign in (demo)" })).toBeTruthy();
    expect(screen.getByText(/This is not a real login/)).toBeTruthy();
    // The head nurse is not offered as a nurse identity.
    expect(screen.queryByRole("option", { name: "Staff 900" })).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });

  it("reads only its own /me routes as the signed-in nurse, never the simulator or a staff_id", async () => {
    replies(() => [offer]);
    render(<MyOffersPage />);
    await signInAs(202);
    await screen.findByText("SENT");
    expect(request).toHaveBeenCalledWith(
      "/me/offers",
      expect.objectContaining({ demoUser: 202 }),
    );
    // The page also lists the nurse's own handovers (round 5 PR U5)
    for (const path of requestedPaths()) {
      expect(["/me/offers", "/me/handovers"]).toContain(path);
    }
    expect(window.localStorage.getItem(DEMO_SIGNED_IN_STORAGE_KEY)).toBe("202");
    expect(screen.getByText(/Demo mode: signed in as staff 202/)).toBeTruthy();
    // No staff switcher while signed in (the check-in shift picker is not one).
    expect(screen.queryByLabelText("Staff member")).toBeNull();
  });

  it("says that Accept is not a shift assignment", async () => {
    replies(() => [offer]);
    render(<MyOffersPage />);
    await signInAs(202);
    expect(
      await screen.findByText(/Accepting an offer does not put you on the shift/),
    ).toBeTruthy();
  });

  it("answers with only the response in the body, as the signed-in nurse", async () => {
    replies((path) =>
      path === "/me/offers"
        ? [offer]
        : {
            outreach_id: 1,
            outreach_status: "ACCEPTED",
            case_id: 7,
            case_status: "WAITING_APPROVAL",
          },
    );
    render(<MyOffersPage />);
    await signInAs(202);
    fireEvent.click(await screen.findByRole("button", { name: "Accept offer 1" }));
    await screen.findByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL.");
    expect(request).toHaveBeenCalledWith(
      "/me/offers/1/response",
      expect.objectContaining({
        method: "POST",
        json: { response: "ACCEPT" },
        demoUser: 202,
      }),
    );
  });

  it("shows a 409 from another channel and refreshes the list", async () => {
    let reads = 0;
    replies((path) => {
      if (path !== "/me/offers") return new ApiError(409, { detail: "Offer 1 is not open" });
      reads += 1;
      return reads === 1 ? [offer] : [{ ...offer, status: "REJECTED", can_accept: false, can_reject: false }];
    });
    render(<MyOffersPage />);
    await signInAs(202);
    fireEvent.click(await screen.findByRole("button", { name: "Reject offer 1" }));
    expect(await screen.findByText("Offer 1 is not open")).toBeTruthy();
    expect(await screen.findByText("REJECTED")).toBeTruthy();
  });

  it("keeps the sign-in after a reload", async () => {
    window.localStorage.setItem(DEMO_SIGNED_IN_STORAGE_KEY, "203");
    replies(() => []);
    render(<MyOffersPage />);
    expect(await screen.findByText("You have no shift offers.")).toBeTruthy();
    expect(request).toHaveBeenCalledWith(
      "/me/offers",
      expect.objectContaining({ demoUser: 203 }),
    );
  });

  it.each(["900", "999", "abc", "201.5"])(
    "ignores a stored identity that is not a demo nurse (%s)",
    async (stored) => {
      window.localStorage.setItem(DEMO_SIGNED_IN_STORAGE_KEY, stored);
      render(<MyOffersPage />);
      expect(await screen.findByRole("button", { name: "Sign in (demo)" })).toBeTruthy();
      expect(request).not.toHaveBeenCalled();
    },
  );

  it("signs out back to the demo sign-in", async () => {
    replies(() => [offer]);
    render(<MyOffersPage />);
    await signInAs(202);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("button", { name: "Sign in (demo)" })).toBeTruthy();
    expect(window.localStorage.getItem(DEMO_SIGNED_IN_STORAGE_KEY)).toBeNull();
    expect(screen.queryByText("SENT")).toBeNull();
  });

  it("shows none of the previous nurse's rows after signing in as someone else", async () => {
    let releaseSecond: (offers: Offer[]) => void = () => {};
    request.mockImplementation(async <T,>(path: string, options?: { demoUser?: number }) => {
      if (options?.demoUser === 203 && path === "/me/offers") {
        return new Promise<Offer[]>((resolve) => {
          releaseSecond = resolve;
        }) as Promise<T>;
      }
      return [offer] as T;
    });
    render(<MyOffersPage />);
    await signInAs(202);
    await screen.findByRole("button", { name: "Accept offer 1" });
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await signInAs(203);
    // 203's read has not answered yet: 202's offer must not be on screen meanwhile.
    expect(await screen.findByText(/Demo mode: signed in as staff 203/)).toBeTruthy();
    expect(screen.getByText("Loading offers…")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept offer 1" })).toBeNull();
    const second = { ...offer, id: 9, staff_id: 203 };
    releaseSecond([second]);
    expect(await screen.findByRole("button", { name: "Accept offer 9" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept offer 1" })).toBeNull();
    const afterSwitch = request.mock.calls.slice(
      request.mock.calls.findIndex(([, options]) => options?.demoUser === 203),
    );
    expect(afterSwitch.every(([, options]) => options?.demoUser === 203)).toBe(true);
  });

  it("shows a 503 and lets the nurse try again", async () => {
    replies((path) =>
      path === "/me/offers"
        ? [offer]
        : new ApiError(503, { detail: "The offer is busy. Try again." }),
    );
    render(<MyOffersPage />);
    await signInAs(202);
    fireEvent.click(await screen.findByRole("button", { name: "Accept offer 1" }));
    expect(await screen.findByText("The offer is busy. Try again.")).toBeTruthy();
    const accept = await screen.findByRole("button", { name: "Accept offer 1" });
    expect((accept as HTMLButtonElement).disabled).toBe(false);
  });

  it("explains an expired offer and disables both buttons", async () => {
    replies(() => [
      {
        ...offer,
        status: "TIMEOUT",
        can_accept: false,
        can_reject: false,
        blocked_reason: "OFFER_EXPIRED",
      },
    ]);
    render(<MyOffersPage />);
    await signInAs(202);
    expect(await screen.findByText(/This offer has expired/)).toBeTruthy();
    for (const name of ["Accept offer 1", "Reject offer 1"]) {
      expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it("still works when storage is blocked", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    try {
      replies(() => [offer]);
      render(<MyOffersPage />);
      await signInAs(202);
      expect(await screen.findByText("SENT")).toBeTruthy();
    } finally {
      getItem.mockRestore();
      setItem.mockRestore();
    }
  });

  it("checks the nurse in to a seeded shift and says the arrival was late", async () => {
    replies((path) =>
      path === "/me/attendance/check-in"
        ? {
            attendance_id: 4,
            shift_id: 1,
            check_in_at: "2026-10-09T23:30:00+07:00",
            on_time: false,
            deadline: "2026-10-09T23:15:00+07:00",
          }
        : [],
    );
    render(<MyOffersPage />);
    await signInAs(101);
    fireEvent.click(await screen.findByRole("button", { name: "Check in" }));
    const status = await screen.findByText(/Checked in to shift 1/);
    expect(status.textContent).toContain("late (deadline 2026-10-09 23:15:00)");
    expect(request).toHaveBeenCalledWith(
      "/me/attendance/check-in",
      expect.objectContaining({ method: "POST", json: { shift_id: 1 }, demoUser: 101 }),
    );
  });

  it("explains a refused check-in", async () => {
    replies((path) =>
      path === "/me/attendance/check-in" ? new ApiError(409, { detail: "busy" }) : [],
    );
    render(<MyOffersPage />);
    await signInAs(101);
    fireEvent.click(await screen.findByRole("button", { name: "Check in" }));
    expect((await screen.findByRole("alert")).textContent).toContain("The shift is busy");
  });

  it("offers the shift of a handover for check-in and lists the handover", async () => {
    const handover = {
      handover_id: 9,
      roster_assignment_id: 30,
      active: true,
      generated_at: "2026-10-09T21:05:00+07:00",
      content: { version: 1, shift: { id: 21, ward_name: "Medicine" }, reason: "NO_SHOW", co_workers: [] },
    };
    replies((path) => (path === "/me/handovers" ? { active: [handover], history: [], next_cursor: null } : []));
    render(<MyOffersPage />);
    await signInAs(201);
    expect(await screen.findByText(/Shift 21 \(Medicine\)/)).toBeTruthy();
    const options = Array.from(
      (screen.getByLabelText("Shift") as HTMLSelectElement).options,
    ).map((option) => option.value);
    expect(options).toContain("21");
  });

  it("keeps the handovers it has and warns when a refresh fails", async () => {
    const handover = {
      handover_id: 9,
      roster_assignment_id: 30,
      active: true,
      generated_at: "2026-10-09T21:05:00+07:00",
      content: { version: 1, shift: { id: 21, ward_name: "Medicine" }, co_workers: [] },
    };
    let reads = 0;
    replies((path) => {
      if (path !== "/me/handovers") return [];
      reads += 1;
      return reads === 1 ? { active: [handover], history: [], next_cursor: null } : new ApiError(503, { detail: "down" });
    });
    render(<MyOffersPage />);
    await signInAs(201);
    expect(await screen.findByText(/Shift 21 \(Medicine\)/)).toBeTruthy();
    expect(
      await screen.findByText(/Could not refresh your handovers/, {}, { timeout: 4000 }),
    ).toBeTruthy();
    expect(screen.getByText(/Shift 21 \(Medicine\)/)).toBeTruthy();
  });
});

it("loads older handovers on demand and keeps the active handover", async () => {
  const make = (id: number, active: boolean) => ({
    handover_id: id, roster_assignment_id: id, active,
    generated_at: "2026-10-09T21:05:00+07:00",
    content: { version: 1, shift: { id, ward_name: "ICU" }, co_workers: [] },
  });
  replies((path) => {
    if (path === "/me/handovers") {
      return { active: [make(21, true)], history: [make(20, false)], next_cursor: "opaque+cursor=" };
    }
    if (path === "/me/handovers?cursor=opaque%2Bcursor%3D") {
      return { active: [make(21, true)], history: [make(19, false)], next_cursor: null };
    }
    return [];
  });
  render(<MyOffersPage />);
  await signInAs(201);
  await screen.findByText(/Shift 20 \(ICU\)/);
  expect(screen.queryByText(/Shift 19 \(ICU\)/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Load more history" }));
  expect(await screen.findByText(/Shift 19 \(ICU\)/)).toBeTruthy();
  expect(screen.getAllByText(/Shift 21 \(ICU\)/)).toHaveLength(1);
  expect(screen.getByText(/Shift 20 \(ICU\)/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Load more history" })).toBeNull();
});

it("keeps loaded handovers visible when the next page fails", async () => {
  const handover = {
    handover_id: 20, roster_assignment_id: 20, active: false,
    generated_at: "2026-10-09T21:05:00+07:00",
    content: { version: 1, shift: { id: 20, ward_name: "ICU" }, co_workers: [] },
  };
  replies((path) => {
    if (path === "/me/handovers") return { active: [], history: [handover], next_cursor: "older" };
    if (path.includes("cursor=")) return new ApiError(503, { detail: "offline" });
    return [];
  });
  render(<MyOffersPage />);
  await signInAs(201);
  await screen.findByText(/Shift 20 \(ICU\)/);
  fireEvent.click(screen.getByRole("button", { name: "Load more history" }));
  await screen.findByText(/Could not refresh your handovers/);
  expect(screen.getByText(/Shift 20 \(ICU\)/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Load more history" })).toBeTruthy();
});
