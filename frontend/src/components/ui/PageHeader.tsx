import type { ReactNode } from "react";

/** The title of a page, an optional line under it and the controls that belong to it. */
export function PageHeader({
  title,
  description,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-6">
      <h1>{title}</h1>
      {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
