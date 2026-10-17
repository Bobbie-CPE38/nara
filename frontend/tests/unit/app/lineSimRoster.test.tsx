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
      actual_start_at: null,
      actual_end_at: null,
      transferred_from_assignment_id: null,
      staff_id: 105,
      first_name: "Sudarat",
      last_name: "Demo",
      staff_status: "ACTIVE",
      role_id: 1,
      role_name: "RN",
      home_ward_id: 1,
      home_ward_name: "ICU",
      is_unavailable: false,
      created_at: offer.sent_at!,
      updated_at: offer.sent_at!,
    },
    {
      id: 6,
      status: "ASSIGNED",
      assignment_type: "REPLACEMENT",
      candidate_source: "SAME_WARD",
      actual_start_at: null,
      actual_end_at: null,
      transferred_from_assignment_id: null,
      staff_id: 201,
      first_name: "Arunee",
      last_name: "Demo",
      staff_status: "ACTIVE",
      role_id: 1,
      role_name: "RN",
      home_ward_id: 1,
      home_ward_name: "ICU",
      is_unavailable: false,
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
  it("allows choosing one of several offers by its own ID", async () => {
    const second = { ...offer, id: 2, case_id: 8, ward_name: "Ward 2" };
    replies((path) =>
      path.endsWith("/respond")
        ? {
            outreach_id: 2,
            outreach_status: "ACCEPTED",
            case_id: 8,
            case_status: "WAITING_APPROVAL",
          }
        : [offer, second],
    );
    render(<LineSimulatorPage />);
    const button = await screen.findByRole("button", {
      name: "Accept offer 2",
    });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect(request).toHaveBeenCalledWith(
      "/demo/line-sim/respond",
      expect.objectContaining({
        json: { outreach_id: 2, response: "ACCEPT" },
        demoUser: 201,
      }),
    );
  });
  it("disables only Accept for a paused offer and explains why", async () => {
    replies(() => [
      { ...offer, can_accept: false, blocked_reason: "AWAITING_OTHER_CASE" },
    ]);
    render(<LineSimulatorPage />);
    const accept = await screen.findByRole("button", {
      name: "Accept offer 1",
    });
    expect((accept as HTMLButtonElement).disabled).toBe(true);
    expect(
      (
        screen.getByRole("button", {
          name: "Reject offer 1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
    expect(screen.getByText(/Accept is paused/)).toBeTruthy();
  });
  it("allows reserves to respond while the case waits for approval", async () => {
    replies(() => [{ ...offer, case_status: "WAITING_APPROVAL" }]);
    render(<LineSimulatorPage />);
    expect(
      (
        (await screen.findByRole("button", {
          name: "Accept offer 1",
        })) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  });
  it("shows the recorded cancellation reason", async () => {
    replies(() => [
      {
        ...offer,
        status: "CANCELLED",
        can_accept: false,
        can_reject: false,
        cancellation_reason: "CASE_RESOLVED",
      },
    ]);
    render(<LineSimulatorPage />);
    expect(await screen.findByText("Cancelled: CASE_RESOLVED")).toBeTruthy();
  });

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
  it.each(["RESOLVED", "FAILED", "UNRESOLVED", "MANUAL_HANDOFF"] as const)(
    "hides the waiting-for-approval message when the case is %s",
    async (caseStatus) => {
      replies(() => [
        {
          ...offer,
          status: "ACCEPTED",
          case_status: caseStatus,
          can_accept: false,
          can_reject: false,
        },
      ]);
      render(<LineSimulatorPage />);
      await screen.findByText("ACCEPTED");
      expect(screen.queryByText(/Wait for head-nurse approval/)).toBeNull();
    },
  );
  it("keeps the final outcome visible when LINE is unavailable", async () => {
    const message = "ข้อเสนอเข้าเวร #1 ถูกยกเลิกแล้ว คุณไม่ได้รับมอบหมายให้เข้าเวรจากข้อเสนอนี้";
    replies(() => [{
      ...offer,
      status: "CANCELLED",
      can_accept: false,
      can_reject: false,
      final_outcome: "CANCELLED",
      final_message: message,
      final_delivery_status: "FAILED",
    }]);
    render(<LineSimulatorPage />);
    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.getByText(/The LINE notification could not be delivered/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Accept offer 1" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not show an old failure message for a confirmed assignment", async () => {
    replies(() => [{
      ...offer,
      status: "ACCEPTED",
      is_assigned: true,
      final_message: "stale failure message",
    }]);
    render(<LineSimulatorPage />);
    expect(await screen.findByText("Assignment confirmed for this shift.")).toBeTruthy();
    expect(screen.queryByText("stale failure message")).toBeNull();
  });

  it("explains a TIMEOUT offer after the job runs", async () => {
    replies(() => [
      {
        ...offer,
        status: "TIMEOUT",
        blocked_reason: null,
        can_accept: false,
        can_reject: false,
      },
    ]);
    render(<LineSimulatorPage />);
    await screen.findByText("TIMEOUT");
    await screen.findByText(/This offer has expired/);
    expect(
      (
        screen.getByRole("button", {
          name: "Accept offer 1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      (
        screen.getByRole("button", {
          name: "Reject offer 1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(request.mock.calls.some(([path]) => path.endsWith("/respond"))).toBe(
      false,
    );
  });
  it("shows a confirmed assignment before the multi-person case has finished", async () => {
    replies(() => [
      {
        ...offer,
        status: "ACCEPTED",
        case_status: "WAITING_APPROVAL",
        is_assigned: true,
        can_accept: false,
        can_reject: false,
      },
    ]);
    render(<LineSimulatorPage />);
    await screen.findByText("Assignment confirmed for this shift.");
    expect(screen.queryByText(/Wait for head-nurse approval/)).toBeNull();
  });
  it("shows the approval message for a live non-reserve acceptance", async () => {
    replies(() => [
      {
        ...offer,
        status: "ACCEPTED",
        case_status: "WAITING_APPROVAL",
        can_accept: false,
        can_reject: false,
      },
    ]);
    render(<LineSimulatorPage />);
    await screen.findByText(/Wait for head-nurse approval/);
  });
  it("shows the deadline and disables an overdue SENT offer before the job runs", async () => {
    replies(() => [
      {
        ...offer,
        can_accept: false,
        can_reject: false,
        blocked_reason: "OFFER_EXPIRED",
      },
    ]);
    render(<LineSimulatorPage />);
    await screen.findByText("Deadline (Bangkok)");
    await screen.findByText(/This offer has expired/);
    for (const name of ["Accept offer 1", "Reject offer 1"]) {
      const button = screen.getByRole("button", { name }) as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      fireEvent.click(button);
    }
    expect(request.mock.calls.some(([path]) => path.endsWith("/respond"))).toBe(
      false,
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
    const button = screen.getByRole("button", { name: "Accept offer 1" });
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
        json: { outreach_id: offer.id, response: "ACCEPT" },
      }),
    );
    expect(
      (
        screen.getByRole("button", {
          name: "Accept offer 1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
  it("shows a rejected request error without claiming Reject is unsupported", async () => {
    replies((path) => {
      if (path.endsWith("/respond"))
        throw new ApiError(422, { detail: "Unsupported" });
      return [offer];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Reject offer 1" }));
    await screen.findByText("Unsupported");
    expect(screen.getByText("SENT")).toBeTruthy();
  });
  it("refreshes stale offers after 409", async () => {
    let stale = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        stale = true;
        throw new ApiError(409, { detail: "No open offer" });
      }
      return stale
        ? [{ ...offer, status: "ACCEPTED", case_status: "WAITING_APPROVAL" }]
        : [offer];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    await screen.findByText("ACCEPTED");
    expect(screen.getByRole("alert").textContent).toContain("No open offer");
  });
  it("sends the clicked offer ID and refreshes a replacement offer after a conflict", async () => {
    let conflicted = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        conflicted = true;
        throw new ApiError(409, {
          detail:
            "The open offer has changed; refresh offers before responding",
        });
      }
      return conflicted ? [{ ...offer, id: 8, case_id: 9 }] : [offer];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    expect(
      await screen.findByRole("button", { name: "Accept offer 8" }),
    ).toBeTruthy();
    const mutations = request.mock.calls.filter(([path]) =>
      path.endsWith("/respond"),
    );
    expect(mutations).toHaveLength(1);
    expect(mutations[0][1]).toEqual(
      expect.objectContaining({
        demoUser: 201,
        json: { outreach_id: 1, response: "ACCEPT" },
      }),
    );
    expect(screen.queryByText("ACCEPTED")).toBeNull();
  });
  it("clears a 409 explanation when the offer ID is reused with a new sent time", async () => {
    vi.useFakeTimers();
    let rows = [offer];
    replies((path) => {
      if (path.endsWith("/respond")) {
        rows = [
          { ...offer, status: "ACCEPTED", case_status: "WAITING_APPROVAL" },
        ];
        throw new ApiError(409, { detail: "No open offer" });
      }
      return rows;
    });
    render(<LineSimulatorPage />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    await act(async () => {});
    expect(screen.getByRole("alert").textContent).toContain("No open offer");
    rows = [{ ...offer, sent_at: "2026-10-10T21:00:00+07:00" }];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("clears a 409 explanation when another open offer appears beside the old history", async () => {
    vi.useFakeTimers();
    let rows: Offer[] = [offer];
    replies((path) => {
      if (path.endsWith("/respond")) {
        rows = [
          { ...offer, status: "ACCEPTED", case_status: "WAITING_APPROVAL" },
        ];
        throw new ApiError(409, { detail: "No open offer" });
      }
      return rows;
    });
    render(<LineSimulatorPage />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    await act(async () => {});
    expect(screen.getByRole("alert").textContent).toContain("No open offer");
    rows = [...rows, { ...offer, id: 2, case_id: 8 }];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "Accept offer 2",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  });

  it("preserves success when a pre-response poll lands before the refreshed result", async () => {
    vi.useFakeTimers();
    let reads = 0;
    let finishOld!: (rows: Offer[]) => void;
    let finishFresh!: (rows: Offer[]) => void;
    request.mockImplementation(<T,>(path: string) => {
      if (path.endsWith("/respond"))
        return Promise.resolve({
          outreach_id: 1,
          outreach_status: "ACCEPTED",
          case_id: 7,
          case_status: "WAITING_APPROVAL",
        } as T);
      reads += 1;
      if (reads === 1) return Promise.resolve([offer] as T);
      return new Promise<T>((resolve) => {
        if (reads === 2) finishOld = (rows) => resolve(rows as T);
        else finishFresh = (rows) => resolve(rows as T);
      });
    });
    render(<LineSimulatorPage />);
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    await act(async () => {});
    const message = "Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL.";
    expect(screen.getByText(message)).toBeTruthy();
    await act(async () => finishOld([{ ...offer }]));
    expect(screen.getByText(message)).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Accept offer 1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await act(async () =>
      finishFresh([
        { ...offer, status: "ACCEPTED", case_status: "WAITING_APPROVAL" },
      ]),
    );
    expect(screen.getByText(message)).toBeTruthy();
  });
  it.each([
    { offers: [{ ...offer, status: "ACCEPTED" }] },
    {
      offers: [
        {
          ...offer,
          case_status: "FAILED",
          can_accept: false,
          can_reject: false,
        },
      ],
    },
  ])("disables history and stopped cases: $offers", async ({ offers }) => {
    replies(() => offers);
    render(<LineSimulatorPage />);
    await screen.findByRole("table");
    for (const button of screen.getAllByRole("button"))
      expect((button as HTMLButtonElement).disabled).toBe(true);
  });
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
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    await screen.findByText(
      "Offer 1: ACCEPTED. Case 7 failed after this response. Check its timeline.",
    );
    await screen.findByText("FAILED");
    expect(
      (
        screen.getByRole("button", {
          name: "Accept offer 1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
  it("keeps the acting staff selected until the response arrives", async () => {
    let resolve!: (value: unknown) => void;
    let accepted = false;
    request.mockImplementation(<T,>(path: string) =>
      path.endsWith("/respond")
        ? new Promise<T>((done) => {
            resolve = (value) => {
              accepted = true;
              done(value as T);
            };
          })
        : Promise.resolve([
            {
              ...offer,
              status: accepted ? "ACCEPTED" : "SENT",
              case_status: accepted ? "WAITING_APPROVAL" : "WAITING_RESPONSE",
            },
          ] as T),
    );
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    const selector = screen.getByLabelText("Staff member") as HTMLSelectElement;
    expect(selector.disabled).toBe(true);
    fireEvent.change(selector, { target: { value: "202" } });
    expect(selector.value).toBe("201");
    await act(async () =>
      resolve({
        outreach_id: 1,
        outreach_status: "ACCEPTED",
        case_id: 7,
        case_status: "WAITING_APPROVAL",
      }),
    );
    await screen.findByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL.");
    expect(selector.disabled).toBe(false);
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
      fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
      if (conflict) await screen.findByRole("alert");
      else
        await screen.findByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL.");
      expect(screen.getByRole("table")).toBe(table);
      const accept = screen.getByRole("button", {
        name: "Accept offer 1",
      }) as HTMLButtonElement;
      expect(accept.disabled).toBe(true);
      fireEvent.click(accept);
      expect(
        request.mock.calls.filter(([path]) => path.endsWith("/respond")),
      ).toHaveLength(1);
      expect(screen.queryByText("Loading offers…")).toBeNull();
      await act(async () => finishRefresh([{ ...offer, status: "ACCEPTED" }]));
      expect(screen.getByText("ACCEPTED")).toBeTruthy();
    },
  );

  it("warns when the backend answered a different offer", async () => {
    let answered = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        answered = true;
        return {
          outreach_id: 8,
          outreach_status: "ACCEPTED",
          case_id: 9,
          case_status: "WAITING_APPROVAL",
        };
      }
      return answered
        ? [
            {
              ...offer,
              id: 8,
              case_id: 9,
              status: "ACCEPTED",
              case_status: "WAITING_APPROVAL",
            },
          ]
        : [offer];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "You selected offer 1, but the server recorded ACCEPTED for offer 8 on case 9",
    );
    expect(
      screen.queryByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL."),
    ).toBeNull();
  });

  it("uses the returned offer status for a successful rejection", async () => {
    let answered = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        answered = true;
        return {
          outreach_id: 1,
          outreach_status: "REJECTED",
          case_id: 7,
          case_status: "OUTREACH",
        };
      }
      return answered
        ? [{ ...offer, status: "REJECTED", case_status: "OUTREACH" }]
        : [offer];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Reject offer 1" }));
    await screen.findByText("Offer 1: REJECTED. Case 7: OUTREACH.");
    expect(screen.queryByText(/Offer accepted/)).toBeNull();
  });

  it.each(["RESOLVED", "RESET"])(
    "clears a success banner when polled data changes to %s",
    async (next) => {
      vi.useFakeTimers();
      let rows = [offer];
      replies((path) => {
        if (path.endsWith("/respond")) {
          rows = [
            { ...offer, status: "ACCEPTED", case_status: "WAITING_APPROVAL" },
          ];
          return {
            outreach_id: 1,
            outreach_status: "ACCEPTED",
            case_id: 7,
            case_status: "WAITING_APPROVAL",
          };
        }
        return rows;
      });
      render(<LineSimulatorPage />);
      await act(async () => {});
      fireEvent.click(screen.getByRole("button", { name: "Accept offer 1" }));
      await act(async () => {});
      expect(
        screen.getByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL."),
      ).toBeTruthy();
      rows =
        next === "RESET"
          ? [{ ...offer }]
          : [{ ...rows[0], case_status: "RESOLVED" }];
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(
        screen.queryByText("Offer 1: ACCEPTED. Case 7: WAITING_APPROVAL."),
      ).toBeNull();
      if (next === "RESET")
        expect(
          (
            screen.getByRole("button", {
              name: "Accept offer 1",
            }) as HTMLButtonElement
          ).disabled,
        ).toBe(false);
    },
  );

  it("clears an error banner when its offer is replaced", async () => {
    vi.useFakeTimers();
    let rows = [offer];
    replies((path) => {
      if (path.endsWith("/respond"))
        throw new ApiError(422, { detail: "Unsupported" });
      return rows;
    });
    render(<LineSimulatorPage />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Reject offer 1" }));
    await act(async () => {});
    expect(screen.getByRole("alert")).toBeTruthy();
    rows = [{ ...offer, id: 2 }];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("describes a failed rejection using REJECTED rather than acceptance", async () => {
    let answered = false;
    replies((path) => {
      if (path.endsWith("/respond")) {
        answered = true;
        return {
          outreach_id: 1,
          outreach_status: "REJECTED",
          case_id: 7,
          case_status: "FAILED",
        };
      }
      return [
        {
          ...offer,
          status: answered ? "REJECTED" : "SENT",
          case_status: answered ? "FAILED" : "WAITING_RESPONSE",
        },
      ];
    });
    render(<LineSimulatorPage />);
    await screen.findByText("SENT");
    fireEvent.click(screen.getByRole("button", { name: "Reject offer 1" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Offer 1: REJECTED. Case 7 failed after this response. Check its timeline.",
    );
  });

  it("gives each offer's buttons unique accessible names", async () => {
    replies(() => [offer, { ...offer, id: 2, status: "ACCEPTED" }]);
    render(<LineSimulatorPage />);
    await screen.findByRole("table");
    expect(screen.getByRole("button", { name: "Accept offer 1" })).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Accept offer 2",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});

describe("Roster", () => {
  function cellUnder(table: HTMLElement, row: HTMLElement, heading: string) {
    const headers = within(table).getAllByRole("columnheader");
    const header = within(table).getByRole("columnheader", { name: heading });
    return within(row).getAllByRole("cell")[headers.indexOf(header)];
  }

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
  it("shows actual intervals and transfer links while preserving scheduled shift times", async () => {
    replies(() => ({
      ...roster,
      assignments: [
        {
          ...roster.assignments[1],
          actual_start_at: "2026-10-10T01:00:00+07:00",
          actual_end_at: "2026-10-10T05:00:00+07:00",
          transferred_from_assignment_id: 42,
        },
      ],
    }));
    render(<RosterPage />);
    const table = await screen.findByRole("table");
    const row = within(table).getByText("201 — Arunee Demo").closest("tr")!;
    expect(cellUnder(table, row, "Working interval (Bangkok)").textContent).toBe(
      "2026-10-10 01:00:00 – 2026-10-10 05:00:00",
    );
    expect(cellUnder(table, row, "Transferred from assignment").textContent).toBe("42");
    expect(
      screen.getByText("2026-10-09 23:00:00 – 2026-10-10 07:00:00 (Bangkok)"),
    ).toBeTruthy();
  });

  it("falls back independently when an actual endpoint is null", async () => {
    replies(() => ({
      ...roster,
      assignments: [
        { ...roster.assignments[1], actual_end_at: "2026-10-10T01:00:00+07:00" },
      ],
    }));
    render(<RosterPage />);
    const table = await screen.findByRole("table");
    const row = within(table).getByText("201 — Arunee Demo").closest("tr")!;
    expect(cellUnder(table, row, "Working interval (Bangkok)").textContent).toBe(
      "2026-10-09 23:00:00 – 2026-10-10 01:00:00",
    );
    expect(cellUnder(table, row, "Transferred from assignment").textContent).toBe("—");
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
  it("marks only assigned people whose leave overlaps the shift", async () => {
    replies(() => ({
      ...roster,
      assignments: [
        roster.assignments[0],
        { ...roster.assignments[1], is_unavailable: true },
      ],
    }));
    render(<RosterPage />);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(within(rows[1]).queryByText("On leave")).toBeNull();
    expect(within(rows[2]).getByText("On leave")).toBeTruthy();
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
