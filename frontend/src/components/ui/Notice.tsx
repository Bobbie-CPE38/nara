import type { ReactNode } from "react";

const STYLES = {
  error: "border-red-200 bg-red-50 text-red-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  info: "border-brand-200 bg-brand-50 text-brand-900",
} as const;

/** A message about the state of the page: an error, a warning or a note. */
export function Notice({
  kind = "info",
  role,
  children,
}: {
  kind?: keyof typeof STYLES;
  role?: "alert" | "status";
  children: ReactNode;
}) {
  return (
    <p role={role} className={`rounded-lg border px-3 py-2 text-sm ${STYLES[kind]}`}>
      {children}
    </p>
  );
}
