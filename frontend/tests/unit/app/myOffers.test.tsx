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

  it("reads only /me/offers as the signed-in nurse, never the simulator or a staff_id", async () => {
    replies(() => [offer]);
    render(<MyOffersPage />);
    await signInAs(202);
    await screen.findByText("SENT");
    expect(request).toHaveBeenCalledWith(
      "/me/offers",
      expect.objectContaining({ demoUser: 202 }),
    );
    for (const path of requestedPaths()) {
      expect(path).toBe("/me/offers");
    }
    expect(window.localStorage.getItem(DEMO_SIGNED_IN_STORAGE_KEY)).toBe("202");
    expect(screen.getByText(/Demo mode: signed in as staff 202/)).toBeTruthy();
    // No staff switcher while signed in.
    expect(screen.queryByRole("combobox")).toBeNull();
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
});
