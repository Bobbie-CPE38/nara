"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { WardOption } from "@/lib/types/dashboard";

/**
 * How many wards the user sees, and the choice of one (round 6 PR EV6, docs/workflow.md
 * 6.36.4). A Supervisor may see dozens of wards: the list opens with a fixed height and
 * scrolls, instead of a native select that grows with the wards, or a long joined line.
 */
export function WardFilter({
  options,
  value,
  onChange,
}: {
  options: WardOption[];
  /** null: every ward */
  value: number | null;
  onChange: (wardId: number | null) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const listId = useId();
  const chosen = options.find((option) => option.id === value);

  // Close on a click outside or Escape, like a native select
  useEffect(() => {
    if (!open) return;
    function outside(event: MouseEvent) {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  function pick(wardId: number | null) {
    onChange(wardId);
    setOpen(false);
  }

  const items: { id: number | null; label: string }[] = [
    { id: null, label: t("dash.allWards") },
    ...options.map((option) => ({
      id: option.id,
      label: option.is_active === false ? t("dash.wardPaused", { ward: option.name }) : option.name,
    })),
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-900">
      {/* The wards that run; a paused one is offered in the list only */}
      <span className="font-medium">
        {t("dash.wardCount", { count: options.filter((option) => option.is_active !== false).length })}
      </span>
      <div ref={box} className="relative">
        <button
          type="button"
          className="min-w-44 rounded-lg border border-slate-300 bg-white px-3 py-1 text-left"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listId}
          aria-label={t("dash.wardFilter")}
          onClick={() => setOpen((value) => !value)}
        >
          {chosen ? items.find((item) => item.id === chosen.id)?.label : t("dash.allWards")}
          <span aria-hidden="true" className="ml-2 text-slate-500">
            ▾
          </span>
        </button>
        {open && (
          <ul
            id={listId}
            role="listbox"
            aria-label={t("dash.wardFilter")}
            className="absolute z-20 mt-1 max-h-60 w-64 overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
          >
            {items.map((item) => (
              <li key={item.id ?? "all"} role="option" aria-selected={item.id === value}>
                <button
                  type="button"
                  className={`block w-full rounded-none border-0 bg-transparent px-3 py-1.5 text-left shadow-none hover:bg-brand-50 ${
                    item.id === value ? "font-semibold text-brand-700" : ""
                  }`}
                  onClick={() => pick(item.id)}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
