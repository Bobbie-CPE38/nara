// @vitest-environment jsdom
// The pages of round 6 PR UI2 in Thai and in English: a title, the labels, an empty state, and
// nothing of the other language left on the page.
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Approvals from "../../../src/app/approvals/page";
import DemoControl from "../../../src/app/demo/control/page";
import LineSimulator from "../../../src/app/demo/line-sim/page";
import GapCheck from "../../../src/app/gap/page";
import Handoff from "../../../src/app/handoff/page";
import MyOffers from "../../../src/app/me/offers/page";
import Roster from "../../../src/app/roster/page";
import { ClockProvider } from "../../../src/components/ClockProvider";
import { LanguageProvider } from "../../../src/lib/i18n/LanguageProvider";
import { dashboard } from "../../fixtures/dashboard";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

const ROSTER = {
  shift: {
    id: 1, ward_id: 1, ward_name: "ICU", shift_type: "NIGHT",
    start_at: "2026-10-17T23:00:00+07:00", end_at: "2026-10-18T07:00:00+07:00", is_active: true,
  },
  assignments: [],
};

const SHIFT_OF_THE_DAY = {
  shift_id: 1, ward_id: 1, start_at: ROSTER.shift.start_at, end_at: ROSTER.shift.end_at,
  required_staff: 5, rostered_count: 0, headcount_gap: 5, case_id: null,
};
/** What GET /gap/shifts answers: none for the gap check, shift 1 for the roster */
let gapShifts: unknown[] = [];

/** What the API answers to each read of these pages: nothing to list. */
function answer(url: string): unknown {
  const { pathname, search } = new URL(url);
  if (pathname === "/roster") return ROSTER;
  if (pathname === "/dashboard") return dashboard();
  if (pathname === "/clock") return { now: "2026-10-17T23:00:00+07:00", frozen: true };
  if (pathname === "/gap/shifts") return gapShifts;
  // Round 6 PR EV6: the case search, and what the Demo control picks from
  if (pathname === "/cases/search") return { items: [], total: 0, page: 1, page_size: 10 };
  if (pathname === "/demo/wards") return [{ id: 1, name: "ICU", is_active: true, is_float_pool: false }];
  if (pathname === "/demo/shifts") {
    return [{ id: 1, ward_id: 1, shift_type: "NIGHT", start_at: ROSTER.shift.start_at, end_at: ROSTER.shift.end_at, people: [] }];
  }
  return pathname.startsWith("/gap/shifts") || search.includes("status=") || pathname.startsWith("/approvals") || pathname.includes("offers")
    ? []
    : {};
}

beforeEach(() => {
  window.localStorage.clear();
  gapShifts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => new Response(JSON.stringify(answer(url)))),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function show(page: React.ReactElement, lang: "th" | "en") {
  render(<LanguageProvider initial={lang}>{page}</LanguageProvider>);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
}

const title = () => screen.getByRole("heading", { level: 1 }).textContent;

describe("the pages in Thai", () => {
  it("Roster", async () => {
    gapShifts = [SHIFT_OF_THE_DAY];
    await show(<Roster />, "th");
    expect(title()).toBe("ตารางเวร");
    expect(screen.getByText(/เวรของหอที่คุณมีสิทธิ์ดู/)).toBeTruthy();
    expect(await screen.findByRole("option", { name: "เวร 1 · 23:00–07:00" })).toBeTruthy();
    expect(await screen.findByText("เวรนี้ไม่มีการจัดคนเข้าเวร")).toBeTruthy();
    expect(screen.getByText("ICU · เวร 1 · NIGHT")).toBeTruthy();
    expect(screen.queryByText("No assignments for this shift.")).toBeNull();
  });

  it("LINE simulator", async () => {
    await show(<LineSimulator />, "th");
    expect(title()).toBe("จำลอง LINE สำหรับ Demo");
    expect(screen.getByLabelText("พนักงาน")).toBeTruthy();
    expect(screen.getByRole("option", { name: "พนักงาน 201" })).toBeTruthy();
    expect(await screen.findByText("พนักงานคนนี้ไม่มีข้อเสนอ")).toBeTruthy();
    expect(screen.getByText(/เลือกข้อเสนอเพื่อตอบรับหรือปฏิเสธ/)).toBeTruthy();
    expect(screen.queryByText("No offers for this staff member.")).toBeNull();
  });

  it("My offers: the demo sign-in", async () => {
    await show(<MyOffers />, "th");
    expect(title()).toBe("ข้อเสนอเวรของฉัน");
    expect(screen.getByText(/ลงชื่อเข้าใช้ Demo: เลือกว่าคุณคือใคร/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "ลงชื่อเข้าใช้ (Demo)" })).toBeTruthy();
    expect(screen.queryByText("Sign in (demo)")).toBeNull();
  });

  it("Handoff", async () => {
    await show(<Handoff />, "th");
    expect(title()).toBe("เคสที่ส่งต่อให้คน");
    expect(screen.getByLabelText("ดูในฐานะ")).toBeTruthy();
    expect(await screen.findByText("ไม่มีเคสที่ส่งต่อให้คน")).toBeTruthy();
    expect(screen.queryByText("No handed-off cases.")).toBeNull();
  });

  it("Approvals", async () => {
    await show(<Approvals />, "th");
    expect(title()).toBe("คำขออนุมัติที่รอ");
    expect(screen.getByLabelText("ทำในฐานะ")).toBeTruthy();
    expect(screen.getByRole("option", { name: "950 — ผู้ควบคุมดูแล, ทุกหอ" })).toBeTruthy();
    expect(await screen.findByText("ไม่มีคำขออนุมัติที่รอ")).toBeTruthy();
    const auto = within(screen.getByRole("region", { name: "ที่ระบบอนุมัติให้" }));
    expect(await auto.findByText("ไม่มีของพนักงาน 900")).toBeTruthy();
    expect(screen.queryByText("No pending approvals.")).toBeNull();
  });

  it("Gap check", async () => {
    await show(<GapCheck />, "th");
    expect(title()).toBe("เช็ค Gap");
    expect(await screen.findByLabelText("วันที่เวรเริ่ม")).toBeTruthy();
    expect(screen.getByLabelText(/^หอ/)).toBeTruthy();
    expect(await screen.findByText("ไม่มีเวรที่เริ่มในวันนี้ในหอนี้")).toBeTruthy();
    expect(screen.queryByText("No shift starts on this day in this ward.")).toBeNull();
  });

  it("Demo control", async () => {
    await show(<ClockProvider><DemoControl /></ClockProvider>, "th");
    expect(title()).toBe("ควบคุม Demo");
    expect(screen.getByRole("button", { name: "รีเซ็ต Demo" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "เดินนาฬิกา" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "105 แจ้งลา (เวร 1)" })).toBeTruthy();
    expect(screen.getByText("แจ้งลาหรือจำลองการเช็คอิน เลือกหอ วัน เวร และคนได้อิสระ")).toBeTruthy();
    expect(screen.getByRole("button", { name: "ตั้งเวลาแล้วเดินต่อ" })).toBeTruthy();
    expect(await screen.findByRole("option", { name: "เวร 1 · NIGHT · 23:00–07:00" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "จำลองการเช็คอิน (Demo)" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reset demo" })).toBeNull();
  });
});

describe("the same pages in English", () => {
  it("keep the texts they had before the language switch", async () => {
    gapShifts = [SHIFT_OF_THE_DAY];
    await show(<Roster />, "en");
    expect(title()).toBe("Shift roster");
    expect(await screen.findByText("No assignments for this shift.")).toBeTruthy();
    cleanup();
    await show(<Approvals />, "en");
    expect(title()).toBe("Pending approvals");
    expect(await screen.findByText("No pending approvals.")).toBeTruthy();
    cleanup();
    await show(<ClockProvider><DemoControl /></ClockProvider>, "en");
    expect(await screen.findByRole("option", { name: "Shift 1 · NIGHT · 23:00–07:00" })).toBeTruthy();
  });
});
