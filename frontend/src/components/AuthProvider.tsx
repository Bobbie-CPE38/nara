"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ApiError, apiRequest, setAuthProblemHandler, setSessionMode } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { useT } from "@/lib/i18n/LanguageProvider";
import { homeOf, roleMayOpen } from "@/lib/routeAccess";
import type { AuthConfig, AuthMe } from "@/lib/types/auth";

/**
 * Who the page is for (round 6 PR AU3, docs/workflow.md 6.33). `demo`: the Backend runs with
 * AUTH_MODE=demo, the identity is the choice on the page as before. `loading`: the mode is not
 * known yet. The others are the states of AUTH_MODE=session.
 */
export type AuthState =
  | { status: "demo" }
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; me: AuthMe }
  | { status: "unavailable"; failure: unknown };

type AuthValue = {
  state: AuthState;
  login: (staffId: number, password: string) => Promise<AuthMe>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  reload: () => void;
};

const NO_PROVIDER = () => Promise.reject(new Error("AuthProvider is missing"));

/**
 * Without a provider (a page rendered alone by a test) the mode is `demo`, which is how the
 * pages worked before the login. The app always has a provider: the root layout.
 */
const AuthContext = createContext<AuthValue>({
  state: { status: "demo" },
  login: NO_PROVIDER,
  logout: NO_PROVIDER,
  changePassword: NO_PROVIDER,
  reload: () => {},
});

export function useAuth(): AuthValue {
  return useContext(AuthContext);
}

/** The signed-in person in session mode, otherwise undefined. */
export function useSessionUser(): AuthMe | undefined {
  const { state } = useAuth();
  return state.status === "authenticated" ? state.me : undefined;
}

/** Only used to resolve a path: the check is that the result stays on this origin. */
const SAFE_BASE = "http://nara.invalid";

/**
 * Where a page may send the user after a login: a path inside this web app only. It is checked as
 * the browser will read it, not as it is written: a browser drops a tab or a newline inside a URL,
 * so `/<tab>/evil.example` is `//evil.example`. A control character, a backslash, a path that
 * resolves to another origin, and one that resolves to the login or register page fall back to the
 * Dashboard, so the login page cannot be used to send people elsewhere. What comes back is the
 * resolved path, not the text that came in.
 */
export function safeNext(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.includes("\\")) return "/";
  if ([...value].some((char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127)) return "/";
  let url: URL;
  try {
    url = new URL(value, SAFE_BASE);
  } catch {
    return "/";
  }
  if (url.origin !== SAFE_BASE) return "/";
  // `/.//evil.example` resolves to the path `//evil.example`: on its own, as a router target, that is
  // another site. The result must stay a path when it is read without its origin
  if (url.pathname.startsWith("//")) return "/";
  if (/^\/(login|register)\/?$/.test(url.pathname)) return "/";
  return `${url.pathname}${url.search}${url.hash}`;
}

/** The API and database check (round 6 PR EV8): shown even when the Backend cannot be reached */
const STATUS_PAGE = "/status";

/**
 * Pages that work without an account: the login ones and the system status. Since round 6 PR
 * EV8 (docs/workflow.md 6.38.1) a Demo page needs the login of a head nurse or a supervisor
 * first: Caddy asks the Backend before its Basic Auth, and this page does the same.
 */
function worksWithoutAccount(path: string): boolean {
  // /change-password sends a visitor without a session to /login itself (it also shows the result)
  return path === "/login" || path === "/register" || path === "/change-password" || path === STATUS_PAGE;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    void (async () => {
      try {
        const config = await apiRequest<AuthConfig>("/auth/config");
        if (!current) return;
        setSessionMode(config.auth_mode === "session");
        if (config.auth_mode === "demo") {
          setState({ status: "demo" });
          return;
        }
        try {
          const me = await apiRequest<AuthMe>("/auth/me");
          if (current) setState({ status: "authenticated", me });
        } catch (cause) {
          if (!current) return;
          // 401 is the normal answer of a visitor who has not logged in
          if (cause instanceof ApiError && cause.status === 401) setState({ status: "anonymous" });
          else setState({ status: "unavailable", failure: cause });
        }
      } catch (cause) {
        if (current) setState({ status: "unavailable", failure: cause });
      }
    })();
    return () => {
      current = false;
    };
  }, [attempt]);

  useEffect(() => {
    // Any later answer that says the session is gone, or that the password must change first
    setAuthProblemHandler((problem) => {
      setState((previous) => {
        if (problem === "login") return previous.status === "authenticated" ? { status: "anonymous" } : previous;
        return previous.status === "authenticated"
          ? { status: "authenticated", me: { ...previous.me, must_change_password: true } }
          : previous;
      });
    });
    return () => setAuthProblemHandler(null);
  }, []);

  const login = useCallback(async (staffId: number, password: string) => {
    const me = await apiRequest<AuthMe>("/auth/login", { method: "POST", json: { staff_id: staffId, password } });
    setState({ status: "authenticated", me });
    return me;
  }, []);

  const logout = useCallback(async () => {
    await apiRequest<void>("/auth/logout", { method: "POST" });
    setState({ status: "anonymous" });
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await apiRequest<void>("/auth/change-password", {
      method: "POST",
      json: { current_password: currentPassword, new_password: newPassword },
    });
    // The Backend ended every session of the account, this one too
    setState({ status: "anonymous" });
  }, []);

  const value = useMemo(
    () => ({ state, login, logout, changePassword, reload }),
    [state, login, logout, changePassword, reload],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Keeps a page from showing before the Backend said who the user is. A visitor without a session
 * goes to /login and comes back to the page afterwards; a user who must change the password goes
 * to that page first. The Backend decides every right again on each request: this only spares
 * the user a page full of errors.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const t = useT();
  const { state, reload } = useAuth();
  const router = useRouter();
  const pathname = usePathname() ?? "/";

  const mustChange = state.status === "authenticated" && state.me.must_change_password;
  const sendToLogin = state.status === "anonymous" && !worksWithoutAccount(pathname);
  const sendToChangePassword = mustChange && pathname !== "/change-password";
  // A page outside the user's role goes back to their home page without a word (round 6 PR EV7):
  // the Dashboard, or My offers for a nurse (round 6 PR EV8)
  const sendHome = state.status === "authenticated" && !roleMayOpen(pathname, state.me.role);
  const redirectTo = sendToLogin
    ? `/login?next=${encodeURIComponent(safeNext(`${pathname}${typeof window === "undefined" ? "" : window.location.search}`))}`
    : sendToChangePassword
      ? "/change-password"
      : sendHome && state.status === "authenticated"
        ? homeOf(state.me.role)
        : null;

  useEffect(() => {
    if (redirectTo !== null) router.replace(redirectTo);
  }, [redirectTo, router]);

  // The status page says itself whether the API answers: no login, no check of the mode first
  if (pathname === STATUS_PAGE) return <>{children}</>;
  if (state.status === "loading") {
    return (
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
        <p role="status">{t("auth.checking")}</p>
      </main>
    );
  }
  if (state.status === "unavailable") {
    return (
      <main className="mx-auto max-w-6xl space-y-3 px-4 py-6 sm:py-8">
        <Notice kind="error" role="alert">
          {t("auth.unavailable", { error: describeError(state.failure, t) })}
        </Notice>
        <Button onClick={reload}>{t("auth.retry")}</Button>
      </main>
    );
  }
  if (redirectTo !== null) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
        <p role="status">{t("auth.redirecting")}</p>
      </main>
    );
  }
  // Not logged in and not a login page: nothing of the page is shown (handled above), so reaching
  // here means demo mode, a signed-in user, or a page that needs no account
  return <>{children}</>;
}
