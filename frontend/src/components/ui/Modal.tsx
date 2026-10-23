"use client";

import { type ReactNode, useEffect, useRef } from "react";
import { useT } from "@/lib/i18n/LanguageProvider";

/**
 * A dialog over the page (round 6 PR EV6): a dimmed backdrop, a title, a close button, and
 * Escape to close. The body scrolls inside, so a long staff list never pushes the buttons
 * off a phone screen. Focus moves into the dialog when it opens and back when it closes.
 */
export function Modal({
  title,
  onClose,
  closeDisabled = false,
  children,
}: {
  title: string;
  onClose: () => void;
  /** While a request runs the dialog stays, so its answer has somewhere to show */
  closeDisabled?: boolean;
  children: ReactNode;
}) {
  const t = useT();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const before = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus();
    return () => before?.focus();
  }, []);

  useEffect(() => {
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape" && !closeDisabled) onClose();
    }
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose, closeDisabled]);

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="flex max-h-[92vh] w-full max-w-3xl flex-col rounded-t-2xl bg-white shadow-xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 className="text-lg font-semibold text-brand-800">{title}</h2>
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-slate-600 hover:bg-slate-100 disabled:opacity-50"
            aria-label={t("common.close")}
            disabled={closeDisabled}
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <div className="overflow-y-auto px-4 py-3">{children}</div>
      </div>
    </div>
  );
}
