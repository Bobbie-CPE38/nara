"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { DemoClock } from "@/components/DemoClock";
import { LanguageSwitch } from "@/components/layout/LanguageSwitch";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";

const NAV_ITEMS: readonly { href: string; label: MessageKey }[] = [
  { href: "/", label: "nav.dashboard" },
  { href: "/gap", label: "nav.gap" },
  { href: "/demo/control", label: "nav.demoControl" },
  { href: "/approvals", label: "nav.approvals" },
  { href: "/handoff", label: "nav.handoff" },
  { href: "/demo/line-sim", label: "nav.lineSim" },
  { href: "/roster", label: "nav.roster" },
  { href: "/me/offers", label: "nav.myOffers" },
];

function NavLinks({ onNavigate, stacked }: { onNavigate?: () => void; stacked: boolean }) {
  const t = useT();
  const pathname = usePathname();
  return (
    <ul className={stacked ? "flex flex-col gap-1" : "flex flex-wrap items-center gap-1"}>
      {NAV_ITEMS.map(({ href, label }) => {
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
        </div>
      </div>
      {open && (
        <nav id="mobile-menu" aria-label={t("nav.main")} className="border-t border-slate-200 px-4 py-3 md:hidden">
          <NavLinks stacked onNavigate={() => setOpen(false)} />
        </nav>
      )}
      {/* The Backend clock is always in view: check-in and NO_SHOW follow it, not the browser */}
      <div className="border-t border-slate-100 bg-brand-50/70">
        <div className="mx-auto flex max-w-6xl justify-end px-4 py-1 text-xs text-slate-700">
          <DemoClock />
        </div>
      </div>
    </header>
  );
}
