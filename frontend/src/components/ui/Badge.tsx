import type { ReactNode } from "react";
import type { StatusTone } from "@/lib/constants";

/** Every pair passes WCAG AA (4.5:1): the dark text of a tone on its light fill. */
const TONES: Record<StatusTone, string> = {
  ok: "bg-green-50 text-green-800 ring-green-600/25",
  bad: "bg-red-50 text-red-800 ring-red-600/25",
  waiting: "bg-amber-50 text-amber-900 ring-amber-600/30",
  neutral: "bg-brand-50 text-brand-800 ring-brand-600/20",
};

/** A short label with the tone of a status (the tones of docs/workflow.md section 4). */
export function Badge({
  tone = "neutral",
  as: Tag = "span",
  children,
}: {
  tone?: StatusTone;
  /** The element: a status in a sentence is a <strong>, which a screen reader reads as emphasis */
  as?: "span" | "strong";
  children: ReactNode;
}) {
  return (
    <Tag
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${TONES[tone]}`}
    >
      {children}
    </Tag>
  );
}
