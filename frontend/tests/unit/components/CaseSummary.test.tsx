// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CaseSummary } from "@/components/case/CaseSummary";
import { apiRequest } from "@/lib/api";
import type { CaseSummaryView } from "@/lib/types/case";

vi.mock("@/lib/api", () => ({ apiRequest: vi.fn() }));
const api = vi.mocked(apiRequest);
const summary = (overrides: Partial<CaseSummaryView["current"]> = {}): CaseSummaryView => ({
  current: { summary_id: null, status: "NOT_REQUESTED", text: null, generated_at: null,
    stale: false, can_request: true, request_blocked_reason: null, ...overrides }, history: [],
});
beforeEach(() => { api.mockReset(); });
afterEach(cleanup);

it("does not request AI on render and only queues when clicked", async () => {
  const refresh = vi.fn(async () => {});
  api.mockResolvedValue(summary({ summary_id: 1, status: "PENDING", can_request: false, request_blocked_reason: "PENDING" }));
  render(<CaseSummary caseId={7} summary={summary()} onRequested={refresh} />);
  expect(api).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Summarise with AI" }));
  await act(async () => {});
  expect(api).toHaveBeenCalledTimes(1);
  expect(api).toHaveBeenCalledWith("/cases/7/summary", expect.objectContaining({ method: "POST" }));
  expect(refresh).toHaveBeenCalledTimes(1);
});

it("retains cached text and disables a request when quota is exhausted", () => {
  render(<CaseSummary caseId={7} summary={summary({ summary_id: 1, status: "READY", text: "สรุปเดิม",
    stale: true, can_request: false, request_blocked_reason: "QUOTA_EXHAUSTED" })} onRequested={vi.fn()} />);
  expect(screen.getByText("สรุปเดิม")).toBeTruthy();
  expect(screen.getByText(/Today's AI explanation quota is used up/)).toBeTruthy();
  expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
  expect(api).not.toHaveBeenCalled();
});

it("shows stale and historical summaries and offers a new snapshot only explicitly", () => {
  const data = summary({ summary_id: 2, status: "READY", text: "ข้อความที่ล้าสมัย", stale: true });
  data.history = [{ summary_id: 1, text: "ฉบับก่อนหน้า", generated_at: "2026-10-09T21:00:00+07:00" }];
  render(<CaseSummary caseId={7} summary={data} onRequested={vi.fn()} />);
  expect(screen.getByText(/The case data has changed/)).toBeTruthy();
  expect(screen.getByText("ฉบับก่อนหน้า")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Create a new summary" }) as HTMLButtonElement).disabled).toBe(false);
  expect(api).not.toHaveBeenCalled();
});

it("prevents double clicks and refreshes after an error without automatically re-posting", async () => {
  let reject: (error: Error) => void = () => {};
  api.mockImplementation(() => new Promise((_, no) => { reject = no; }));
  const refresh = vi.fn(async () => {});
  render(<CaseSummary caseId={7} summary={summary()} onRequested={refresh} />);
  const button = screen.getByRole("button");
  fireEvent.click(button);
  fireEvent.click(button);
  expect(api).toHaveBeenCalledTimes(1);
  await act(async () => { reject(new Error("quota changed")); });
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(api).toHaveBeenCalledTimes(1);
  expect(refresh).toHaveBeenCalledTimes(1);
});

it("aborts a request when the case page unmounts", () => {
  api.mockImplementation(() => new Promise(() => {}));
  const { unmount } = render(<CaseSummary caseId={7} summary={summary()} onRequested={vi.fn()} />);
  fireEvent.click(screen.getByRole("button"));
  const signal = api.mock.calls[0][1]?.signal;
  unmount();
  expect(signal?.aborted).toBe(true);
});
