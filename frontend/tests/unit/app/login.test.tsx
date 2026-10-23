// @vitest-environment jsdom
// Login, register, change password, the gate, the menu and the leave page (round 6 PR AU3,
// docs/workflow.md 6.33). The Backend is a stub of fetch; the pages, the provider and the API
// layer are the real ones, so what the browser would send is what is checked.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChangePasswordPage from "@/app/change-password/page";
import LoginPage from "@/app/login/page";
import LeavePage from "@/app/me/leave/page";
import RegisterPage from "@/app/register/page";
import { ActingAs } from "@/components/ActingAs";
import { AuthGate, AuthProvider, safeNext } from "@/components/AuthProvider";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { setSessionMode } from "@/lib/api";
import { bangkokIso, parseStaffId, passwordProblem } from "@/lib/authForms";
import type { Lang } from "@/lib/i18n";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";

const replace = vi.fn();
let pathname = "/";
let params = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
  useSearchParams: () => params,
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

type Reply = { status: number; body?: unknown };
type Handler = (init: RequestInit, url: URL) => Reply | Promise<Reply>;
let routes: Record<string, Handler> = {};
const calls: { method: string; path: string; body: unknown; headers: Headers; credentials?: RequestCredentials }[] = [];

const ME = { staff_id: 201, role: "staff", home_ward_id: 1, must_change_password: false };
const HEAD = { staff_id: 900, role: "head_nurse", home_ward_id: 1, must_change_password: false };
const SUPERVISOR = { staff_id: 950, role: "supervisor", home_ward_id: 3, must_change_password: false };

function session(me: unknown | null, extra: Record<string, Handler> = {}) {
  routes = {
    "GET /auth/config": () => ({ status: 200, body: { auth_mode: "session" } }),
    "GET /auth/me": () => (me ? { status: 200, body: me } : { status: 401, body: { detail: "AUTH_REQUIRED" } }),
    "GET /clock": () => ({ status: 200, body: { now: "2026-10-22T09:00:00+07:00", frozen: false, date: "2026-10-22" } }),
    ...extra,
  };
}

beforeEach(() => {
  replace.mockReset();
  pathname = "/";
  params = new URLSearchParams();
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      const method = init.method ?? "GET";
      const path = url.pathname + url.search;
      calls.push({
        method,
        path,
        body: init.body ? JSON.parse(String(init.body)) : undefined,
        headers: new Headers(init.headers),
        credentials: init.credentials,
      });
      const handler = routes[`${method} ${url.pathname}`] ?? routes[`${method} ${path}`];
      if (!handler) return new Response(JSON.stringify({ detail: `no stub for ${method} ${path}` }), { status: 599 });
      const reply = await handler(init, url);
      return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), { status: reply.status });
    }),
  );
});
afterEach(() => {
  cleanup();
  setSessionMode(false);
  vi.unstubAllGlobals();
});

function app(element: ReactElement, lang: Lang = "en") {
  return render(
    <LanguageProvider initial={lang}>
      <AuthProvider>{element}</AuthProvider>
    </LanguageProvider>,
  );
}

const sentOf = (method: string, path: string) => calls.filter((call) => call.method === method && call.path === path);

describe("safeNext", () => {
  it.each([
    ["/gap", "/gap"],
    ["/me/offers?x=1", "/me/offers?x=1"],
    ["https://evil.example/", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["javascript:alert(1)", "/"],
    ["", "/"],
    [null, "/"],
    ["/login?next=/gap", "/"],
    ["/register", "/"],
    // A browser drops a tab or a newline inside a URL: these are //evil.example
    ["/\t/evil.example", "/"],
    ["/\n/evil.example", "/"],
    ["/\r/evil.example", "/"],
    ["/\u0000/evil.example", "/"],
    ["/\u007f/gap", "/"],
    // The same loops by another spelling of the path
    ["/./login", "/"],
    ["/foo/../register", "/"],
    ["/login/", "/"],
    ["/gap/../me/offers", "/me/offers"],
    ["/gap#top", "/gap#top"],
    // The path resolves to //evil.example: returned alone it would be another site
    ["/.//evil.example", "/"],
    ["/a/..//evil.example", "/"],
    ["/a/b/../..//evil.example", "/"],
    ["/./gap", "/gap"],
  ])("%s becomes %s", (value, expected) => {
    expect(safeNext(value)).toBe(expected);
  });

  it("never returns a value that leaves the app when it is resolved against the app's origin", () => {
    const origin = "https://app.example";
    const attempts = [
      "/.//evil.example",
      "/a/..//evil.example",
      "//evil.example",
      "/\t/evil.example",
      "/%2F/evil.example",
      "/..//evil.example",
      "/gap/../../evil.example",
      "/gap?next=//evil.example",
      "/gap#//evil.example",
      "https://evil.example",
      "/login/..//evil.example",
    ];
    for (const attempt of attempts) {
      expect(new URL(safeNext(attempt), origin).origin, attempt).toBe(origin);
    }
  });
});

describe("helpers of the forms", () => {
  it("reads a staff ID only as a positive whole number", () => {
    expect(parseStaffId(" 201 ")).toBe(201);
    for (const bad of ["", "abc", "20.1", "-3", "0", "1e3", "9".repeat(30)]) expect(parseStaffId(bad)).toBeNull();
  });

  it("counts characters, not bytes, for the length of 12 to 128", () => {
    expect(passwordProblem("a".repeat(11), "a".repeat(11))).toBe("auth.password.tooShort");
    expect(passwordProblem("a".repeat(12), "a".repeat(12))).toBeNull();
    expect(passwordProblem("a".repeat(129), "a".repeat(129))).toBe("auth.password.tooShort");
    // 12 Thai letters are 36 bytes but 12 characters
    expect(passwordProblem("ก".repeat(12), "ก".repeat(12))).toBeNull();
    expect(passwordProblem("a".repeat(12), "b".repeat(12))).toBe("auth.password.mismatch");
  });

  it("turns the time of the leave form into an aware Bangkok time", () => {
    expect(bangkokIso("")).toBeUndefined();
    expect(bangkokIso("2026-10-22T08:30")).toBe("2026-10-22T08:30:00+07:00");
  });
});

describe("AuthGate", () => {
  it("shows a page at once in demo mode and asks nothing else", async () => {
    routes = { "GET /auth/config": () => ({ status: 200, body: { auth_mode: "demo" } }) };
    app(
      <AuthGate>
        <p>the page</p>
      </AuthGate>,
    );
    expect(await screen.findByText("the page")).toBeTruthy();
    expect(calls.map((call) => call.path)).toEqual(["/auth/config"]);
    expect(replace).not.toHaveBeenCalled();
  });

  it("holds the page back while it asks who the user is", async () => {
    session(ME);
    app(
      <AuthGate>
        <p>the page</p>
      </AuthGate>,
    );
    expect(screen.queryByText("the page")).toBeNull();
    expect(await screen.findByText("the page")).toBeTruthy();
  });

  it("sends a visitor to /login and keeps where they wanted to go", async () => {
    session(null);
    pathname = "/approvals";
    app(
      <AuthGate>
        <p>secret page</p>
      </AuthGate>,
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fapprovals"));
    expect(screen.queryByText("secret page")).toBeNull();
  });

  it("leaves the login pages and the Demo control to a visitor", async () => {
    session(null);
    for (const path of ["/login", "/register", "/demo/control"]) {
      cleanup();
      pathname = path;
      app(
        <AuthGate>
          <p>open page</p>
        </AuthGate>,
      );
      expect(await screen.findByText("open page")).toBeTruthy();
    }
    expect(replace).not.toHaveBeenCalled();
  });

  it("keeps the LINE simulator behind the login: it answers as a person", async () => {
    session(null);
    pathname = "/demo/line-sim";
    app(
      <AuthGate>
        <p>simulator</p>
      </AuthGate>,
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fdemo%2Fline-sim"));
    expect(screen.queryByText("simulator")).toBeNull();
  });

  it("sends a user who must change the password to that page before any other", async () => {
    session({ ...ME, must_change_password: true });
    pathname = "/gap";
    app(
      <AuthGate>
        <p>gap page</p>
      </AuthGate>,
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/change-password"));
    expect(screen.queryByText("gap page")).toBeNull();
  });

  it("says so, and offers to try again, when the Backend cannot say who the user is", async () => {
    session(ME, { "GET /auth/me": () => ({ status: 500, body: { detail: "boom" } }) });
    app(
      <AuthGate>
        <p>the page</p>
      </AuthGate>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("Cannot tell who you are");
    expect(screen.queryByText("the page")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("goes to /login when a later answer says the session is gone", async () => {
    session(ME, { "GET /cases": () => ({ status: 401, body: { detail: "AUTH_REQUIRED" } }) });
    pathname = "/gap";
    const { apiRequest } = await import("@/lib/api");
    app(
      <AuthGate>
        <p>gap page</p>
      </AuthGate>,
    );
    await screen.findByText("gap page");
    await expect(apiRequest("/cases")).rejects.toThrow();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fgap"));
  });
});

describe("login page", () => {
  it("logs in with the staff ID and the password, as JSON with the cookie, and goes on", async () => {
    session(null, { "POST /auth/login": () => ({ status: 200, body: ME }) });
    params = new URLSearchParams("next=/me/offers");
    pathname = "/login";
    app(<LoginPage />);
    await screen.findByLabelText("Staff ID");
    fireEvent.change(screen.getByLabelText("Staff ID"), { target: { value: "201" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse battery" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/me/offers"));
    const [login] = sentOf("POST", "/auth/login");
    expect(login.body).toEqual({ staff_id: 201, password: "correct horse battery" });
    expect(login.credentials).toBe("include");
    expect(login.headers.has("X-Demo-User")).toBe(false);
  });

  it("does not follow a next that names another site", async () => {
    session(null, { "POST /auth/login": () => ({ status: 200, body: ME }) });
    params = new URLSearchParams("next=https://evil.example/");
    app(<LoginPage />);
    await screen.findByLabelText("Staff ID");
    fireEvent.change(screen.getByLabelText("Staff ID"), { target: { value: "201" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "x".repeat(12) } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("sends a user who must change the password to the change page, not to next", async () => {
    session(null, { "POST /auth/login": () => ({ status: 200, body: { ...ME, must_change_password: true } }) });
    params = new URLSearchParams("next=/gap");
    app(<LoginPage />);
    await screen.findByLabelText("Staff ID");
    fireEvent.change(screen.getByLabelText("Staff ID"), { target: { value: "201" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "x".repeat(12) } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/change-password"));
    expect(replace).not.toHaveBeenCalledWith("/gap");
  });

  it("says the same thing for any wrong login, in the language of the page, and keeps no password", async () => {
    session(null, { "POST /auth/login": () => ({ status: 401, body: { detail: "AUTH_INVALID_CREDENTIALS" } }) });
    app(<LoginPage />, "th");
    await screen.findByLabelText("รหัสพนักงาน");
    fireEvent.change(screen.getByLabelText("รหัสพนักงาน"), { target: { value: "201" } });
    fireEvent.change(screen.getByLabelText("รหัสผ่าน"), { target: { value: "wrong password!" } });
    fireEvent.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
    expect((await screen.findByRole("alert")).textContent).toBe("รหัสพนักงานหรือรหัสผ่านไม่ถูกต้อง");
    expect(replace).not.toHaveBeenCalled();
  });

  it("tells a staff ID that is not a number before it asks the Backend", async () => {
    session(null);
    app(<LoginPage />);
    await screen.findByLabelText("Staff ID");
    fireEvent.change(screen.getByLabelText("Staff ID"), { target: { value: "abc" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "whatever" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Enter your staff ID as a number.");
    expect(sentOf("POST", "/auth/login")).toHaveLength(0);
  });

  it("shows the rate limit as a sentence", async () => {
    session(null, { "POST /auth/login": () => ({ status: 429, body: { detail: "AUTH_RATE_LIMITED" } }) });
    app(<LoginPage />);
    await screen.findByLabelText("Staff ID");
    fireEvent.change(screen.getByLabelText("Staff ID"), { target: { value: "201" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "whatever" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Too many attempts");
  });

  it("says there is no login in demo mode", async () => {
    routes = { "GET /auth/config": () => ({ status: 200, body: { auth_mode: "demo" } }) };
    app(<LoginPage />);
    expect((await screen.findByRole("status")).textContent).toContain("demo mode");
    expect(screen.queryByLabelText("Password")).toBeNull();
  });
});

describe("register page", () => {
  it("sends the code and the password only, then offers the login", async () => {
    session(null, { "POST /auth/register": () => ({ status: 201, body: { staff_id: 201 } }) });
    app(<RegisterPage />);
    await screen.findByLabelText("Registration code");
    fireEvent.change(screen.getByLabelText("Registration code"), { target: { value: " CODE-from-LINE " } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "twelve chars!" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "twelve chars!" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect((await screen.findByRole("status")).textContent).toContain("staff ID 201");
    // No role, ward or staff ID travels: the Backend finds the person from the code
    expect(sentOf("POST", "/auth/register")[0].body).toEqual({ code: "CODE-from-LINE", password: "twelve chars!" });
  });

  it("refuses a short password and two different passwords without asking the Backend", async () => {
    session(null);
    app(<RegisterPage />);
    await screen.findByLabelText("Registration code");
    fireEvent.change(screen.getByLabelText("Registration code"), { target: { value: "abc" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The password needs 12 to 128 characters.");
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "long enough password" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The two passwords are not the same.");
    expect(sentOf("POST", "/auth/register")).toHaveLength(0);
  });

  it("gives one sentence for a wrong, expired or used code", async () => {
    session(null, { "POST /auth/register": () => ({ status: 400, body: { detail: "AUTH_INVALID_REGISTRATION" } }) });
    app(<RegisterPage />);
    await screen.findByLabelText("Registration code");
    fireEvent.change(screen.getByLabelText("Registration code"), { target: { value: "abc" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "long enough password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "long enough password" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect((await screen.findByRole("alert")).textContent).toContain("wrong, has expired or was used already");
  });
});

describe("change password page", () => {
  it("changes the password and says every login has ended", async () => {
    session(ME, { "POST /auth/change-password": () => ({ status: 204 }) });
    pathname = "/change-password";
    app(<ChangePasswordPage />);
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "the old password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a brand new password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a brand new password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("status")).textContent).toContain("every login of the account has ended");
    expect(sentOf("POST", "/auth/change-password")[0].body).toEqual({
      current_password: "the old password",
      new_password: "a brand new password",
    });
    // The page stays to say so: it must not bounce the user to /login before they read it
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows a wrong current password as a sentence and does not log the user out", async () => {
    session(ME, { "POST /auth/change-password": () => ({ status: 400, body: { detail: "AUTH_INVALID_PASSWORD" } }) });
    app(<ChangePasswordPage />);
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "not the password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a brand new password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a brand new password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The current password is wrong.");
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Current password")).toBeTruthy();
  });

  it("keeps what the user typed when the change fails", async () => {
    session(ME, { "POST /auth/change-password": () => ({ status: 400, body: { detail: "AUTH_INVALID_PASSWORD" } }) });
    app(<ChangePasswordPage />);
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "a wrong current one" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a brand new password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a brand new password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The current password is wrong.");
    expect((screen.getByLabelText("Current password") as HTMLInputElement).value).toBe("a wrong current one");
    expect((screen.getByLabelText("New password") as HTMLInputElement).value).toBe("a brand new password");
    expect((screen.getByLabelText("Repeat the password") as HTMLInputElement).value).toBe("a brand new password");
  });

  it("keeps the fields on a rate limit too", async () => {
    session(ME, { "POST /auth/change-password": () => ({ status: 429, body: { detail: "AUTH_RATE_LIMITED" } }) });
    app(<ChangePasswordPage />);
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "the old password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a brand new password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a brand new password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Too many attempts");
    expect((screen.getByLabelText("New password") as HTMLInputElement).value).toBe("a brand new password");
  });

  it("goes to /login when the session expires during the change", async () => {
    session(ME, { "POST /auth/change-password": () => ({ status: 401, body: { detail: "AUTH_REQUIRED" } }) });
    pathname = "/change-password";
    app(<ChangePasswordPage />);
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "the old password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a brand new password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a brand new password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    // The user is not left on "Checking who you are…": the page sends them to log in again
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("shows the success message even when the provider turns anonymous before the page does", async () => {
    // The provider is anonymous the moment the password is changed; the page must not leave first
    session(ME, { "POST /auth/change-password": () => ({ status: 204 }) });
    pathname = "/change-password";
    app(<ChangePasswordPage />);
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "the old password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a brand new password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a brand new password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("status")).textContent).toContain("every login of the account has ended");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(replace).not.toHaveBeenCalledWith("/login");
  });

  it("refuses a new password equal to the current one", async () => {
    session(ME);
    app(<ChangePasswordPage />);
    await screen.findByLabelText("Current password");
    for (const label of ["Current password", "New password", "Repeat the password"]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "the same password" } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The new password must differ from the current one.");
    expect(sentOf("POST", "/auth/change-password")).toHaveLength(0);
  });

  it("explains why the user is here when the account says the password must change", async () => {
    session({ ...ME, must_change_password: true });
    pathname = "/change-password";
    app(<ChangePasswordPage />);
    expect((await screen.findByText(/must change the password before/)).textContent).toBeTruthy();
  });

  it("sends a visitor without a session to /login", async () => {
    session(null);
    pathname = "/change-password";
    app(<ChangePasswordPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});

describe("the menu follows the role", () => {
  async function menuOf(me: unknown | null) {
    session(me);
    app(<SiteHeader />);
    await screen.findByRole("navigation", { name: "Main navigation" }).catch(() => undefined);
    // The menu needs the answer of /auth/me: wait for a link only a login shows, or for the login link
    await waitFor(() => expect(calls.some((call) => call.path === "/auth/me")).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const nav = screen.getAllByRole("navigation", { name: "Main navigation" })[0];
    return within(nav).queryAllByRole("link").map((link) => link.textContent);
  }

  it("shows a staff nurse the pages of a nurse and no approvals, handoff or Demo pages", async () => {
    const links = await menuOf(ME);
    expect(links).toEqual(["Dashboard", "Gap check", "Cases", "Roster", "My offers", "Report leave"]);
  });

  it("adds Demo control, Approvals and Handoff for a head nurse and a supervisor, no other Demo page", async () => {
    // Round 6 PR EV6: the Demo control is in the menu of the people who run the demo
    for (const me of [HEAD, SUPERVISOR]) {
      cleanup();
      const links = await menuOf(me);
      expect(links).toEqual([
        "Dashboard", "Gap check", "Demo control", "Approvals", "Handoff", "Cases", "Roster", "My offers",
        ...(me === SUPERVISOR ? ["Staff management"] : []), "Report leave",
      ]);
    }
  });

  it("shows a visitor no menu button on a phone either: there is nothing to open", async () => {
    session(null);
    app(<SiteHeader />);
    await screen.findByRole("link", { name: "Log in" });
    expect(screen.queryByRole("button", { name: "Open the menu" })).toBeNull();
  });

  it("shows a logged-in user the menu button", async () => {
    session(ME);
    app(<SiteHeader />);
    await screen.findByText("Staff 201 · Staff");
    expect(screen.getByRole("button", { name: "Open the menu" })).toBeTruthy();
  });

  it("shows a visitor no pages, only the login link", async () => {
    const links = await menuOf(null);
    expect(links).toEqual([]);
    expect(await screen.findByRole("link", { name: "Log in" })).toBeTruthy();
  });

  it("shows who is logged in and logs out, then asks nothing but the logout", async () => {
    session(HEAD, { "POST /auth/logout": () => ({ status: 204 }) });
    app(<SiteHeader />);
    expect(await screen.findByText("Staff 900 · Head Nurse")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Change password" }).getAttribute("href")).toBe("/change-password");
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(sentOf("POST", "/auth/logout")).toHaveLength(1));
    expect(await screen.findByRole("link", { name: "Log in" })).toBeTruthy();
  });

  it("keeps every page in the menu in demo mode, as before the login", async () => {
    routes = {
      "GET /auth/config": () => ({ status: 200, body: { auth_mode: "demo" } }),
      "GET /clock": () => ({ status: 200, body: { now: "2026-10-22T09:00:00+07:00", frozen: false, date: "2026-10-22" } }),
    };
    app(<SiteHeader />);
    await waitFor(() => expect(calls.some((call) => call.path === "/auth/config")).toBe(true));
    const nav = await waitFor(() => {
      const found = screen.getAllByRole("navigation", { name: "Main navigation" })[0];
      expect(within(found).queryAllByRole("link").length).toBeGreaterThan(0);
      return found;
    });
    expect(within(nav).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Dashboard",
      "Gap check",
      "Demo control",
      "Approvals",
      "Handoff",
      "Cases",
      "LINE simulator",
      "Test runs",
      "Roster",
      "My offers",
    ]);
  });
});

describe("ActingAs", () => {
  it("is the choice of a demo user in demo mode and nothing at all with a login", async () => {
    routes = { "GET /auth/config": () => ({ status: 200, body: { auth_mode: "demo" } }) };
    const demo = app(<ActingAs id="a" value={900} onChange={() => {}} />);
    expect(await demo.findByLabelText(/Viewing as/)).toBeTruthy();
    cleanup();
    session(HEAD);
    const real = app(<ActingAs id="a" value={900} onChange={() => {}} />);
    await waitFor(() => expect(calls.some((call) => call.path === "/auth/me")).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(real.container.querySelector("select")).toBeNull();
  });
});

describe("leave page", () => {
  const ROSTER = {
    staff: { id: 201, first_name: "A", last_name: "B", staff_status: "ACTIVE", role_id: 1, role_name: "RN", home_ward_id: 1, home_ward_name: "ICU" },
    assignments: [
      { id: 1, status: "ASSIGNED", assignment_type: "REGULAR", is_unavailable: false, shift: { id: 21, ward_id: 2, ward_name: "Medicine", shift_type: "NIGHT", start_at: "2026-10-22T20:00:00+07:00", end_at: "2026-10-23T08:00:00+07:00", is_active: true } },
      { id: 2, status: "CANCELLED", assignment_type: "REGULAR", is_unavailable: false, shift: { id: 22, ward_id: 2, ward_name: "Medicine", shift_type: "DAY", start_at: "2026-10-23T08:00:00+07:00", end_at: "2026-10-23T20:00:00+07:00", is_active: true } },
    ],
  };

  it("lists only the assigned shifts of the person and sends only the shift", async () => {
    session(ME, {
      "GET /roster?staff_id=201": () => ({ status: 200, body: ROSTER }),
      "POST /me/unavailability": () => ({ status: 201, body: { event_id: 7, event_status: "RECEIVED", case_id: null, case_status: null } }),
    });
    app(<LeavePage />);
    const select = (await screen.findByLabelText("Shift you cannot work")) as HTMLSelectElement;
    expect(select.options).toHaveLength(1);
    expect(select.options[0].textContent).toContain("Shift 21");
    fireEvent.click(screen.getByRole("button", { name: "Report leave" }));
    expect((await screen.findByText(/Event 7 is RECEIVED/)).textContent).toBeTruthy();
    expect(screen.getByText(/There is no case yet/)).toBeTruthy();
    // No staff ID, no event type, no reason: the Backend knows who is logged in
    expect(sentOf("POST", "/me/unavailability")[0].body).toEqual({ shift_id: 21 });
  });

  it("sends the time of return as Bangkok time", async () => {
    session(ME, {
      "GET /roster?staff_id=201": () => ({ status: 200, body: ROSTER }),
      "POST /me/unavailability": () => ({ status: 201, body: { event_id: 8, event_status: "RECEIVED", case_id: 3, case_status: "OPEN" } }),
    });
    app(<LeavePage />);
    await screen.findByLabelText("Shift you cannot work");
    fireEvent.change(screen.getByLabelText("Back at (optional)"), { target: { value: "2026-10-23T02:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Report leave" }));
    expect(await screen.findByText(/Case 3 is OPEN/)).toBeTruthy();
    expect(sentOf("POST", "/me/unavailability")[0].body).toEqual({ shift_id: 21, end_at: "2026-10-23T02:00:00+07:00" });
  });

  it("shows a refusal of the Backend as a sentence", async () => {
    session(ME, {
      "GET /roster?staff_id=201": () => ({ status: 200, body: ROSTER }),
      "POST /me/unavailability": () => ({ status: 403, body: { detail: "AUTH_FORBIDDEN" } }),
    });
    app(<LeavePage />, "th");
    await screen.findByLabelText("เวรที่คุณทำไม่ได้");
    fireEvent.click(screen.getByRole("button", { name: "แจ้งลา" }));
    expect((await screen.findByRole("alert")).textContent).toBe("แจ้งลาไม่ได้: คุณไม่มีสิทธิ์ทำสิ่งนี้");
  });

  it("says there is nothing to report when no shift is assigned", async () => {
    session(ME, { "GET /roster?staff_id=201": () => ({ status: 200, body: { ...ROSTER, assignments: [] } }) });
    app(<LeavePage />);
    expect(await screen.findByText("You have no assigned shift to report leave for.")).toBeTruthy();
  });

  it("is for a login only: in demo mode it says so and asks for no shifts", async () => {
    routes = { "GET /auth/config": () => ({ status: 200, body: { auth_mode: "demo" } }) };
    app(<LeavePage />);
    expect((await screen.findByRole("status")).textContent).toContain("needs a login");
    expect(calls.some((call) => call.path.startsWith("/roster"))).toBe(false);
  });
});
