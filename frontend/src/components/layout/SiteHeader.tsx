"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { DemoClock } from "@/components/DemoClock";
import { LanguageSwitch } from "@/components/layout/LanguageSwitch";
import { Button } from "@/components/ui/Button";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import { describeError } from "@/lib/errors";
import type { AuthRole } from "@/lib/types/auth";

/** `roles`: who sees the item in session mode (docs/workflow.md 6.33.4); `demo`: shown in demo mode. */
const NAV_ITEMS: readonly { href: string; label: MessageKey; roles: readonly AuthRole[]; demo: boolean }[] = [
  { href: "/", label: "nav.dashboard", roles: ["staff", "head_nurse", "supervisor"], demo: true },
  { href: "/gap", label: "nav.gap", roles: ["staff", "head_nurse", "supervisor"], demo: true },
  { href: "/demo/control", label: "nav.demoControl", roles: [], demo: true },
  { href: "/approvals", label: "nav.approvals", roles: ["head_nurse", "supervisor"], demo: true },
  { href: "/handoff", label: "nav.handoff", roles: ["head_nurse", "supervisor"], demo: true },
  { href: "/demo/line-sim", label: "nav.lineSim", roles: [], demo: true },
  { href: "/roster", label: "nav.roster", roles: ["staff", "head_nurse", "supervisor"], demo: true },
  { href: "/me/offers", label: "nav.myOffers", roles: ["staff", "head_nurse", "supervisor"], demo: true },
  { href: "/admin/staff", label: "nav.staff", roles: ["supervisor"], demo: false },
  { href: "/me/leave", label: "nav.leave", roles: ["staff", "head_nurse", "supervisor"], demo: false },
];

/**
 * The menu follows the Backend's answer: demo mode shows what it always showed, a login shows
 * the pages of the role (the Demo pages stay out of the menu, their address still works behind
 * the Basic Auth of AWS), and a visitor sees none. The Backend checks every right again.
 */
function useNavItems() {
  const { state } = useAuth();
  return NAV_ITEMS.filter((item) => {
    if (state.status === "demo") return item.demo;
    if (state.status === "authenticated") return item.roles.includes(state.me.role);
    return false;
  });
}

const ROLE_KEYS: Record<AuthRole, MessageKey> = {
  staff: "role.staff",
  head_nurse: "role.headNurse",
  supervisor: "role.supervisor",
};

/** Who is logged in, with the way to change the password and to log out; a login link otherwise. */
function AccountMenu() {
  const t = useT();
  const { state, logout } = useAuth();
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (state.status === "anonymous") {
    return (
      <Link className="font-medium text-brand-700 underline" href="/login">
        {t("auth.login.title")}
      </Link>
    );
  }
  if (state.status !== "authenticated") return <span />;
  async function leave() {
    setBusy(true);
    setFailure(null);
    try {
      await logout();
    } catch (cause) {
      setFailure(cause);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="font-medium">{t("auth.signedInAs", { id: state.me.staff_id, role: t(ROLE_KEYS[state.me.role]) })}</span>
      <Link className="underline" href="/change-password">
        {t("auth.change.title")}
      </Link>
      <Button className="px-2 py-0.5 text-xs" disabled={busy} onClick={() => void leave()}>
        {t("auth.logout")}
      </Button>
      {failure !== null && (
        <span role="alert" className="text-red-700">
          {t("auth.logoutFailed", { error: describeError(failure, t) })}
        </span>
      )}
    </div>
  );
}

function NavLinks({ onNavigate, stacked }: { onNavigate?: () => void; stacked: boolean }) {
  const t = useT();
  const pathname = usePathname();
  const items = useNavItems();
  return (
    <ul className={stacked ? "flex flex-col gap-1" : "flex flex-wrap items-center gap-1"}>
      {items.map(({ href, label }) => {
        const current = pathname === href;
        return (
          <li key={href}>
            <Link
              href={href}
              onClick={onNavigate}
              aria-current={current ? "page" : undefined}
              className={`block rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                current
                  ? "bg-brand-50 font-semibold text-brand-700"
                  : "text-slate-700 hover:bg-brand-50 hover:text-brand-700"
              }`}
            >
              {t(label)}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The top bar of every page (round 6 PR UI1, docs/workflow.md 6.32): the logo, the menu, the
 * Backend clock and the language switch. On a narrow screen the menu folds into a button.
 */
export function SiteHeader() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const hasMenu = useNavItems().length > 0;
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 shadow-sm backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2">
        <Link href="/" className="shrink-0" aria-label={t("app.name")}>
          {/* The logo is a file of the team: shown as it is, never recoloured or redrawn */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/nara-logo.svg" alt="NARA" width={87} height={32} className="h-8 w-auto" />
        </Link>
        <nav aria-label={t("nav.main")} className="hidden flex-1 md:block">
          <NavLinks stacked={false} />
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <LanguageSwitch />
          {hasMenu && (
            <button
              type="button"
              className="px-2 md:hidden"
              aria-expanded={open}
              aria-controls="mobile-menu"
              aria-label={open ? t("nav.closeMenu") : t("nav.openMenu")}
              onClick={() => setOpen((value) => !value)}
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
              </svg>
            </button>
          )}
        </div>
      </div>
      {open && hasMenu && (
        <nav id="mobile-menu" aria-label={t("nav.main")} className="border-t border-slate-200 px-4 py-3 md:hidden">
          <NavLinks stacked onNavigate={() => setOpen(false)} />
        </nav>
      )}
      {/* The Backend clock is always in view: check-in and NO_SHOW follow it, not the browser */}
      <div className="border-t border-slate-100 bg-brand-50/70">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-1 text-xs text-slate-700">
          <AccountMenu />
          <DemoClock />
        </div>
      </div>
    </header>
  );
}
