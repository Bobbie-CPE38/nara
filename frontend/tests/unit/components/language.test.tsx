// @vitest-environment jsdom
// The two languages of the web app (round 6 PR UI1, docs/workflow.md 6.32): the switch, the
// cookie, the menu on a phone, and the first pages in Thai and in English.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CaseView } from "../../../src/components/case/CaseView";
import { SiteHeader } from "../../../src/components/layout/SiteHeader";
import { LanguageProvider } from "../../../src/lib/i18n/LanguageProvider";
import { auditEntry, caseDetail, waitingResponseAudit } from "../../fixtures/case";

let pathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stubApi(detail: unknown = caseDetail(), audit: unknown = waitingResponseAudit()) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = new URL(url).pathname;
      if (path === "/clock") return json({ now: "2026-10-09T23:16:00+07:00", frozen: true });
      if (path.endsWith("/audit")) return json(audit);
      return json(detail);
    }),
  );
}

beforeEach(() => {
  pathname = "/";
  document.cookie = "nara-lang=; path=/; max-age=0";
  document.documentElement.lang = "th";
  stubApi();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderHeader(initial: "th" | "en" = "th") {
  return render(
    <LanguageProvider initial={initial}>
      <SiteHeader />
    </LanguageProvider>,
  );
}

describe("the top bar", () => {
  it("shows the menu in Thai first, and in English after the switch, and keeps the choice in a cookie", async () => {
    renderHeader();
    const desktop = within(screen.getAllByRole("navigation", { name: "เมนูหลัก" })[0]);
    expect(desktop.getByRole("link", { name: "แดชบอร์ด" })).toBeTruthy();
    expect(desktop.getByRole("link", { name: "ข้อเสนอของฉัน" })).toBeTruthy();

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "EN" })); });

    const english = within(screen.getAllByRole("navigation", { name: "Main navigation" })[0]);
    expect(english.getByRole("link", { name: "Dashboard" })).toBeTruthy();
    expect(english.getByRole("link", { name: "My offers" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "แดชบอร์ด" })).toBeNull();
    expect(document.cookie).toContain("nara-lang=en");
    expect(document.documentElement.lang).toBe("en");
    expect(screen.getByRole("button", { name: "EN" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "TH" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("starts in the language the server read from the cookie", () => {
    renderHeader("en");
    expect(screen.getByRole("link", { name: "Gap check" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "EN" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("marks the page the user is on", () => {
    pathname = "/gap";
    renderHeader("en");
    const current = screen.getAllByRole("link", { current: "page" });
    expect(current.map((link) => link.textContent)).toEqual(["Gap check"]);
  });

  it("folds the menu into a button on a phone, and the link closes it", async () => {
    renderHeader("en");
    const button = screen.getByRole("button", { name: "Open the menu" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("mobile-menu")).toBeNull();

    fireEvent.click(button);
    expect(screen.getByRole("button", { name: "Close the menu" }).getAttribute("aria-expanded")).toBe("true");
    const menu = within(document.getElementById("mobile-menu") as HTMLElement);
    expect(menu.getAllByRole("link")).toHaveLength(10);

    fireEvent.click(menu.getByRole("link", { name: "Roster" }));
    expect(document.getElementById("mobile-menu")).toBeNull();
  });

  it("shows the logo as the team's file, with a name", () => {
    renderHeader("en");
    const logo = screen.getByRole("img", { name: "NARA" });
    expect(logo.getAttribute("src")).toBe("/nara-logo.svg");
  });
});

describe("the case page in the two languages", () => {
  async function loaded(initial: "th" | "en") {
    vi.useFakeTimers();
    render(
      <LanguageProvider initial={initial}>
        <CaseView caseId="1" />
      </LanguageProvider>,
    );
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  }
  afterEach(() => vi.useRealTimers());

  it("speaks Thai by default: headings, the meaning of the status and the table headers", async () => {
    await loaded("th");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("เคส 1");
    expect(screen.getByText("สถานะ:").querySelector("strong")?.textContent).toBe("WAITING_RESPONSE");
    expect(screen.getByText("รอผู้สมัครตอบ")).toBeTruthy();
    expect(screen.getByRole("table", { name: "ผู้สมัคร" })).toBeTruthy();
    expect(screen.getByRole("table", { name: "ไทม์ไลน์" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "อันดับ 2 · Phanu Demo (202) · 1013 คะแนน" })).toBeTruthy();
    // The English texts of the page are gone
    expect(screen.queryByText("Waiting for candidates to reply")).toBeNull();
    expect(screen.queryByRole("table", { name: "Candidates" })).toBeNull();
  });

  it("keeps what the Backend sends as it is, in either language", async () => {
    await loaded("th");
    // Status codes, audit actions, names and the role and skill names are not translated
    expect(screen.getByText("WAITING_RESPONSE")).toBeTruthy();
    expect(screen.getAllByText("OFFER_SENT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Phanu Demo").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SAME_WARD", { selector: "td" }).length).toBeGreaterThan(0);
  });

  it("has the button for the AI explanation in Thai with the name of the contract", async () => {
    stubApi(caseDetail({
      explanation: { status: "NOT_REQUESTED", text: null, provider: null, model_id: null, can_request: true, request_blocked_reason: null },
    }));
    await loaded("th");
    expect(screen.getByRole("button", { name: "หน้าสรุปด้วย AI" })).toBeTruthy();
    expect(screen.getByText("ยังไม่ได้ขอคำอธิบายจาก AI")).toBeTruthy();
    expect(screen.getByRole("button", { name: "ขอสรุปสถานการณ์ด้วย AI" })).toBeTruthy();
  });

  it("changes to English at once when the language is switched", async () => {
    vi.useRealTimers();
    render(
      <LanguageProvider initial="th">
        <SiteHeader />
        <CaseView caseId="1" />
      </LanguageProvider>,
    );
    expect(await screen.findByText("รอผู้สมัครตอบ")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(await screen.findByText("Waiting for candidates to reply")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Case 1");
  });

  it("shows an unknown audit action and status as they are", async () => {
    stubApi(caseDetail({ status: "SOMETHING_NEW" }), [auditEntry(1, "A_NEW_ACTION")]);
    await loaded("th");
    expect(screen.getByText("SOMETHING_NEW")).toBeTruthy();
    expect(screen.getByText("A_NEW_ACTION")).toBeTruthy();
  });
});
