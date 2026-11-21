// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Page from "@/app/admin/staff/page";
import { AuthProvider } from "@/components/AuthProvider";
import { setSessionMode } from "@/lib/api";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/admin/staff" }));
let role: string, mode: string, failure: boolean, linked: boolean, stale: boolean, inactive: boolean;
let calls: { path: string; method: string; headers: Headers; credentials?: RequestCredentials; body?: unknown }[];
const staff = { id: 201, first_name: "Arunee", last_name: "Demo", role: "RN", ward_name: "ICU", status: "ACTIVE", line_linked: false, line_binding_present: false, skills: ["BLS", "ICU"], has_account: true };
const copy = vi.fn();
beforeEach(() => {
  role = "supervisor"; mode = "session"; failure = false; linked = true; stale = false; inactive = false; calls = []; copy.mockReset();
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: copy } });
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    const path = new URL(url).pathname + new URL(url).search;
    calls.push({ path, method: init.method ?? "GET", headers: new Headers(init.headers), credentials: init.credentials, body: init.body ? JSON.parse(String(init.body)) : undefined });
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
    if (path === "/auth/config") return json({ auth_mode: mode });
    if (path === "/auth/me") return json({ staff_id: 950, role, home_ward_id: 1, must_change_password: false });
    if (path === "/admin/staff/202/line-unlink") { if (stale) return json({ detail: "LINE_NOT_LINKED" }, 409); linked = false; return json({ unlinked_contacts: 1 }); }
    if (path === "/admin/staff/201/line-code") return failure ? json({ detail: "LINE_ALREADY_LINKED" }, 409) : json({ code: "test-secret-code", expires_at: "2026-10-23T12:10:00+07:00" }, 201);
    if (path.startsWith("/admin/staff?")) return json({ items: [staff, { ...staff, id: 202, first_name: "Phanu", line_linked: linked && !inactive, line_binding_present: linked }, { ...staff, id: 203, first_name: "Chonthicha", status: "INACTIVE" }], total: 30 });
    throw new Error(`Unexpected request: ${path}`);
  }));
});
afterEach(() => { cleanup(); setSessionMode(false); vi.unstubAllGlobals(); });
function view(lang: "en" | "th" = "en") {
  render(<LanguageProvider initial={lang}><AuthProvider><Page /></AuthProvider></LanguageProvider>);
}
it("creates and copies LINK with session credentials then hides the secret", async () => {
  view();
  fireEvent.click(within((await screen.findByText("Arunee Demo")).closest("tr")!).getByRole("button"));
  await screen.findByText("LINK test-secret-code");
  fireEvent.click(screen.getByRole("button", { name: "Copy message" }));
  await screen.findByText("Copied");
  expect(copy).toHaveBeenCalledWith("LINK test-secret-code");
  const issue = calls.find((c) => c.method === "POST")!;
  expect(issue.path).toBe("/admin/staff/201/line-code");
  expect(issue.credentials).toBe("include");
  expect(issue.headers.has("X-Demo-User")).toBe(false);
  expect(calls.some((c) => c.path.includes("test-secret-code"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Hide code" }));
  expect(screen.queryByText("LINK test-secret-code")).toBeNull();
});
it("brings the new code into view at once (round 6 PR EV6)", async () => {
  const scroll = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scroll });
  try {
    view();
    fireEvent.click(within((await screen.findByText("Arunee Demo")).closest("tr")!).getByRole("button"));
    const heading = await screen.findByRole("heading", { name: /Arunee Demo/ });
    await waitFor(() => expect(scroll).toHaveBeenCalledWith({ behavior: "smooth", block: "start" }));
    expect(scroll.mock.contexts[0]).toBe(heading);
    expect(document.activeElement).toBe(heading);
  } finally {
    delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
  }
});
it("shows each person's role, skills and web account (round 6 PR EV7)", async () => {
  view();
  const row = (await screen.findByText("Arunee Demo")).closest("tr")!;
  const cells = within(row).getAllByRole("cell").map((cell) => cell.textContent);
  expect(cells.slice(0, 7)).toEqual(["201", "Arunee Demo", "Staff", "BLS, ICU", "ICU", "Active", "Yes"]);
});
it("searches and paginates; linked and inactive staff cannot request codes", async () => {
  view(); await screen.findByText("Arunee Demo");
  for (const name of ["Phanu Demo", "Chonthicha Demo"]) expect(within(screen.getByText(name).closest("tr")!).getByRole("button", { name: "Create LINE code" }).hasAttribute("disabled")).toBe(true);
  fireEvent.change(screen.getByLabelText("Search by staff ID or name"), { target: { value: "201" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(calls.some((c) => c.path === "/admin/staff?q=201&offset=0&limit=25")).toBe(true));
  fireEvent.click(await screen.findByRole("button", { name: "Next" }));
  await waitFor(() => expect(calls.some((c) => c.path === "/admin/staff?q=201&offset=25&limit=25")).toBe(true));
});
it("explains a binding conflict without showing a code", async () => {
  failure = true; view();
  fireEvent.click(within((await screen.findByText("Arunee Demo")).closest("tr")!).getByRole("button"));
  expect((await screen.findByRole("alert")).textContent).toContain("already has a LINE binding");
  expect(screen.queryByText("LINK test-secret-code")).toBeNull();
});
it.each(["staff", "head_nurse"])("does not request the directory as %s", async (value) => {
  role = value; view();
  await screen.findByText("Only a signed-in supervisor can manage LINE linking.");
  expect(calls.filter((c) => c.path.startsWith("/admin/")).length).toBe(0);
});
it("does not use demo identity", async () => {
  mode = "demo"; view();
  await screen.findByText("Only a signed-in supervisor can manage LINE linking.");
  expect(calls.filter((c) => c.path.startsWith("/admin/")).length).toBe(0);
});
it("offers manual copying in Thai if clipboard access fails", async () => {
  copy.mockRejectedValue(new Error("unavailable")); view("th");
  fireEvent.click(within((await screen.findByText("Arunee Demo")).closest("tr")!).getByRole("button"));
  await screen.findByText("LINK test-secret-code");
  fireEvent.click(screen.getByRole("button", { name: "คัดลอกข้อความ" }));
  await screen.findByText("คัดลอกอัตโนมัติไม่ได้ โปรดเลือกและคัดลอกข้อความด้านบน");
});

it("requires the exact typed staff ID, unlinks only that staff, and reloads the directory", async () => {
  view();
  const row = (await screen.findByText("Phanu Demo")).closest("tr")!;
  fireEvent.click(within(row).getByRole("button", { name: "Unlink LINE" }));
  const confirm = screen.getByRole("button", { name: "Confirm unlink" });
  expect(confirm.hasAttribute("disabled")).toBe(true);
  fireEvent.change(screen.getByLabelText("Type staff ID 202 to confirm"), { target: { value: "201" } });
  expect(confirm.hasAttribute("disabled")).toBe(true);
  expect(calls.filter((c) => c.path.endsWith("/line-unlink"))).toHaveLength(0);
  fireEvent.change(screen.getByLabelText("Type staff ID 202 to confirm"), { target: { value: "202" } });
  expect(confirm.hasAttribute("disabled")).toBe(false);
  fireEvent.click(confirm);
  await screen.findByText("LINE unlinked for staff 202.");
  expect(calls.find((c) => c.path.endsWith("/line-unlink"))).toMatchObject({
    path: "/admin/staff/202/line-unlink", method: "POST", body: { confirm_staff_id: "202" }, credentials: "include",
  });
  await waitFor(() => expect(within(screen.getByText("Phanu Demo").closest("tr")!).queryByRole("button", { name: "Unlink LINE" })).toBeNull());
  expect(screen.queryByLabelText("Type staff ID 202 to confirm")).toBeNull();
});
it("cancel does not unlink and clears the confirmation when reopened", async () => {
  view();
  const row = (await screen.findByText("Phanu Demo")).closest("tr")!;
  fireEvent.click(within(row).getByRole("button", { name: "Unlink LINE" }));
  fireEvent.change(screen.getByLabelText("Type staff ID 202 to confirm"), { target: { value: "202" } });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(calls.filter((c) => c.path.endsWith("/line-unlink"))).toHaveLength(0);
  fireEvent.click(within(row).getByRole("button", { name: "Unlink LINE" }));
  expect((screen.getByLabelText("Type staff ID 202 to confirm") as HTMLInputElement).value).toBe("");
  expect(screen.getByRole("button", { name: "Confirm unlink" }).hasAttribute("disabled")).toBe(true);
});

it("clears unlink success when searching and preserves the table after unlink", async () => {
  view();
  const table = (await screen.findByText("Phanu Demo")).closest("table")!;
  fireEvent.click(within(table).getByRole("button", { name: "Unlink LINE" }));
  fireEvent.change(screen.getByLabelText("Type staff ID 202 to confirm"), { target: { value: "202" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm unlink" }));
  await screen.findByText("LINE unlinked for staff 202.");
  expect(screen.getByText("Phanu Demo").closest("table")).toBe(table);
  expect(screen.queryByText("Loading staff…")).toBeNull();
  fireEvent.change(screen.getByLabelText("Search by staff ID or name"), { target: { value: "201" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  expect(screen.queryByText("LINE unlinked for staff 202.")).toBeNull();
});
it("keeps a typed confirmation and blocks searching or paginating until explicitly cancelled", async () => {
  view();
  fireEvent.click(within((await screen.findByText("Phanu Demo")).closest("tr")!).getByRole("button", { name: "Unlink LINE" }));
  fireEvent.change(screen.getByLabelText("Type staff ID 202 to confirm"), { target: { value: "20" } });
  expect(screen.getByRole("button", { name: "Search" }).hasAttribute("disabled")).toBe(true);
  expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect((screen.getByLabelText("Type staff ID 202 to confirm") as HTMLInputElement).value).toBe("20");
  expect(calls.filter((c) => c.path.includes("offset=25"))).toHaveLength(0);
});
it("shows an inactive stored binding separately and permits only unlinking it", async () => {
  inactive = true; view();
  const row = (await screen.findByText("Phanu Demo")).closest("tr")!;
  expect(within(row).getByText("Binding inactive — unlink before replacing")).toBeTruthy();
  expect(within(row).getByRole("button", { name: "Create LINE code" }).hasAttribute("disabled")).toBe(true);
  expect(within(row).getByRole("button", { name: "Unlink LINE" }).hasAttribute("disabled")).toBe(false);
});
it("does not show a success notice for an already-removed binding", async () => {
  stale = true; view();
  fireEvent.click(within((await screen.findByText("Phanu Demo")).closest("tr")!).getByRole("button", { name: "Unlink LINE" }));
  expect(screen.getByText(/Old signup codes will no longer work/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Type staff ID 202 to confirm"), { target: { value: "202" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm unlink" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Nothing was changed");
  expect(screen.queryByText("LINE unlinked for staff 202.")).toBeNull();
});
