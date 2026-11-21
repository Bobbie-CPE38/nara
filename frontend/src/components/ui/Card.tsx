import type { ReactNode } from "react";

/**
 * A white panel with a heading (round 6 PR UI1, docs/workflow.md 6.32). `label` is the
 * accessible name of the section, so a screen reader and a test find it as a region.
 */
export function Card({
  label,
  title,
  children,
  className = "",
}: {
  label?: string;
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={label}
      className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5 ${className}`}
    >
      {title !== undefined && <h2 className="text-lg font-semibold">{title}</h2>}
      {children}
    </section>
  );
}
