// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LineSimulatorPage from "@/app/demo/line-sim/page";
import RosterPage from "@/app/roster/page";
import { ApiError, apiRequest } from "@/lib/api";
import type { Offer } from "@/lib/types/outreach";
import type { ShiftRoster } from "@/lib/types/roster";

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
  staff_id: 201,
  proposed_shift_id: 1,
  status: "SENT",
  case_status: "WAITING_RESPONSE",
  channel: "LINE",
  sent_at: "2026-10-09T21:00:00+07:00",
  response_at: null,
};
const roster: ShiftRoster = {
  shift: {
    id: 1,
    ward_id: 1,
    ward_name: "ICU",
    shift_type: "NIGHT",
    start_at: "2026-10-09T23:00:00+07:00",
    end_at: "2026-10-10T07:00:00+07:00",
    is_active: true,
  },
  assignments: [
    {
      id: 5,
      status: "CANCELLED",
      assignment_type: "REGULAR",
      candidate_source: null,
      staff_id: 105,
      first_name: "Sudarat",
      last_name: "Demo",
      staff_status: "ACTIVE",
      role_id: 1,
      role_name: "RN",
      home_ward_id: 1,
      home_ward_name: "ICU",
      created_at: offer.sent_at!,
      updated_at: offer.sent_at!,
    },
    {
      id: 6,
      status: "ASSIGNED",
      assignment_type: "REPLACEMENT",
      candidate_source: "SAME_WARD",
      staff_id: 201,
      first_name: "Arunee",
      last_name: "Demo",
      staff_status: "ACTIVE",
      role_id: 1,
      role_name: "RN",
      home_ward_id: 1,
      home_ward_name: "ICU",
      created_at: offer.sent_at!,
      updated_at: offer.sent_at!,
    },
  ],
};
beforeEach(() => {
  request.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
function replies(handler: (path: string) => unknown) {
  request.mockImplementation(async <T,>(path: string) => handler(path) as T);
}

describe("LINE simulator", () => {
  it("loads and switches staff with the matching demo identity", async () => {
    replies((path) => (path.includes("staff_id=201") ? [offer] : []));
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    expect(request).toHaveBeenCalledWith(
      "/demo/line-sim/offers?staff_id=201",
      expect.objectContaining({ demoUser: 201 }),
    );
    fireEvent.change(screen.getByLabelText("Staff member"), {
      target: { value: "202" },
    });
    await screen.findByText("No offers for this staff member.");
    expect(screen.queryByText("SENT")).toBeNull();
    expect(request).toHaveBeenCalledWith(
      "/demo/line-sim/offers?staff_id=202",
      expect.objectContaining({ demoUser: 202 }),
    );
  });
  it("accepts only once and refreshes history", async () => {
    let accepted = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        accepted = true;
        return {
          outreach_id: 1,
          outreach_status: "ACCEPTED",
          case_id: 7,
          case_status: "WAITING_APPROVAL",
        };
      }
      return [
        {
          ...offer,
          status: accepted ? "ACCEPTED" : "SENT",
          case_status: accepted ? "WAITING_APPROVAL" : "WAITING_RESPONSE",
        },
      ];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    const button = screen.getByRole("button", { name: "Accept" });
    fireEvent.click(button);
    fireEvent.click(button);
    await screen.findByText("ACCEPTED");
    const mutations = request.mock.calls.filter(([path]) =>
      path.endsWith("/respond"),
    );
    expect(mutations).toHaveLength(1);
    expect(mutations[0][1]).toEqual(
      expect.objectContaining({
        method: "POST",
        demoUser: 201,
        json: { response: "ACCEPT" },
      }),
    );
    expect(
      (screen.getByRole("button", { name: "Accept" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
  it("explains unsupported rejection without changing the offer", async () => {
    replies((path) => {
      if (path.endsWith("/respond"))
        throw new ApiError(422, { detail: "Unsupported" });
      return [offer];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await screen.findByText(
      "Rejection is not supported in this demo yet. The offer remains unchanged.",
    );
    expect(screen.getByText("SENT")).toBeTruthy();
  });
  it("refreshes stale offers after 409", async () => {
    let stale = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        stale = true;
        throw new ApiError(409, { detail: "No open offer" });
      }
      return stale ? [] : [offer];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await screen.findByText("No offers for this staff member.");
    expect(screen.getByRole("alert").textContent).toContain("No open offer");
  });
  it.each([
    { offers: [{ ...offer, status: "ACCEPTED" }] },
    { offers: [{ ...offer, case_status: "FAILED" }] },
    { offers: [offer, { ...offer, id: 2 }] },
  ])(
    "disables history, stopped cases and ambiguous offers: $offers",
    async ({ offers }) => {
      replies(() => offers);
      render(<LineSimulatorPage />);
      await screen.findByRole("table");
      for (const button of screen.getAllByRole("button"))
        expect((button as HTMLButtonElement).disabled).toBe(true);
    },
  );
  it("shows a read error", async () => {
    replies(() => {
      throw new Error("Network unavailable");
    });
    render(<LineSimulatorPage />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Network unavailable",
    );
  });
  it("shows a recorded workflow failure instead of claiming approval succeeded", async () => {
    let accepted = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        accepted = true;
        return {
          outreach_id: 1,
          outreach_status: "ACCEPTED",
          case_id: 7,
          case_status: "FAILED",
        };
      }
      return [
        {
          ...offer,
          status: accepted ? "ACCEPTED" : "SENT",
          case_status: accepted ? "FAILED" : "WAITING_RESPONSE",
        },
      ];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await screen.findByText(
      "Case 7 failed after acceptance. Check its timeline.",
    );
    await screen.findByText("FAILED");
    expect(
      (screen.getByRole("button", { name: "Accept" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
  it("ignores an old response when staff changes", async () => {
    let resolve: (value: unknown) => void = () => {};
    request.mockImplementation(<T,>(path: string) =>
      path.endsWith("/respond")
        ? new Promise<T>((done) => {
            resolve = done as (value: unknown) => void;
          })
        : Promise.resolve((path.includes("staff_id=201") ? [offer] : []) as T),
    );
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    fireEvent.change(screen.getByLabelText("Staff member"), {
      target: { value: "202" },
    });
    await screen.findByText("No offers for this staff member.");
    await act(async () =>
      resolve({
        outreach_id: 1,
        outreach_status: "ACCEPTED",
        case_id: 7,
        case_status: "WAITING_APPROVAL",
      }),
    );
    expect(screen.queryByText(/Offer 1: ACCEPTED/)).toBeNull();
  });

  it.each([false, true])(
    "keeps history visible during refresh after conflict=%s",
    async (conflict) => {
      let changed = false;
      let finishRefresh!: (value: Offer[]) => void;
      request.mockImplementation(<T,>(path: string) => {
        if (path.endsWith("/respond")) {
          changed = true;
          return conflict
            ? Promise.reject(new ApiError(409, { detail: "No open offer" }))
            : Promise.resolve({
                outreach_id: 1,
                outreach_status: "ACCEPTED",
                case_id: 7,
                case_status: "WAITING_APPROVAL",
              } as T);
        }
        if (changed)
          return new Promise<T>((resolve) => {
            finishRefresh = (value) => resolve(value as T);
          });
        return Promise.resolve([offer] as T);
      });
      render(<LineSimulatorPage />);
      const table = await screen.findByRole("table");
      fireEvent.click(screen.getByRole("button", { name: "Accept" }));
      if (conflict) await screen.findByRole("alert");
      else
        await screen.findByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL.");
      expect(screen.getByRole("table")).toBe(table);
      expect(screen.queryByText("Loading offers…")).toBeNull();
      await act(async () => finishRefresh([{ ...offer, status: "ACCEPTED" }]));
      expect(screen.getByText("ACCEPTED")).toBeTruthy();
    },
  );

  it("warns when the backend answered a different offer", async () => {
    replies((path) =>
      path.endsWith("/respond")
        ? {
            outreach_id: 8,
            outreach_status: "ACCEPTED",
            case_id: 9,
            case_status: "WAITING_APPROVAL",
          }
        : [offer],
    );
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "You selected offer 1, but the server recorded ACCEPTED for offer 8 on case 9",
    );
    expect(
      screen.queryByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL."),
    ).toBeNull();
  });

  it("uses the returned offer status for a successful rejection", async () => {
    replies((path) =>
      path.endsWith("/respond")
        ? {
            outreach_id: 1,
            outreach_status: "REJECTED",
            case_id: 7,
            case_status: "OUTREACH",
          }
        : [offer],
    );
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await screen.findByText("Offer 1: REJECTED. Case 7: OUTREACH.");
    expect(screen.queryByText(/Offer accepted/)).toBeNull();
  });
});

describe("Roster", () => {
  it("shows cancellations, replacements and their source", async () => {
    replies(() => roster);
    render(<RosterPage />);
    await screen.findByText("CANCELLED");
    expect(screen.getByText("REPLACEMENT")).toBeTruthy();
    expect(screen.getByText("SAME_WARD")).toBeTruthy();
    expect(request).toHaveBeenCalledWith(
      "/roster?shift_id=1",
      expect.objectContaining({ demoUser: 900 }),
    );
  });
  it("preserves duplicate staff and cross-ward inactive entries", async () => {
    replies(() => ({
      ...roster,
      assignments: [
        roster.assignments[0],
        {
          ...roster.assignments[0],
          id: 8,
          status: "ASSIGNED",
          home_ward_id: 2,
          home_ward_name: "ER",
          staff_status: "INACTIVE",
        },
      ],
    }));
    render(<RosterPage />);
    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("105 — Sudarat Demo")).toHaveLength(2);
    expect(screen.getByText("ER (cross-ward)")).toBeTruthy();
    expect(screen.getByText("INACTIVE")).toBeTruthy();
  });
  it("loads another shift and displays an empty roster", async () => {
    replies((path) =>
      path.includes("shift_id=1")
        ? roster
        : { ...roster, shift: { ...roster.shift, id: 2 }, assignments: [] },
    );
    render(<RosterPage />);
    await screen.findByText("CANCELLED");
    fireEvent.change(screen.getByLabelText("Shift"), {
      target: { value: "2" },
    });
    await screen.findByText("No assignments for this shift.");
    expect(screen.queryByText("CANCELLED")).toBeNull();
    expect(request).toHaveBeenCalledWith(
      "/roster?shift_id=2",
      expect.objectContaining({ demoUser: 900 }),
    );
  });
  it("shows a missing-shift error", async () => {
    replies(() => {
      throw new ApiError(404, { detail: "No shift 1" });
    });
    render(<RosterPage />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "No shift 1",
    );
  });
  it("polls every two seconds and stops on unmount", async () => {
    vi.useFakeTimers();
    replies(() => roster);
    const view = render(<RosterPage />);
    await act(async () => {});
    expect(request).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(request).toHaveBeenCalledTimes(2);
    view.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(request).toHaveBeenCalledTimes(2);
  });
});
