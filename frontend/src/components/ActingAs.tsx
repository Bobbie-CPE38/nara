"use client";

import { useAuth } from "@/components/AuthProvider";
import { DEMO_APPROVERS, wardName } from "@/lib/demo";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";

/**
 * Who a page looks or acts as (docs/workflow.md, sections 6.17 and 6.31). Not a real
 * login: the API shows each demo user only their own ward, and a Supervisor every ward.
 */
export function ActingAs({
  id,
  value,
  onChange,
  label = "actingAs.label",
  disabled = false,
}: {
  id: string;
  value: number;
  onChange: (staffId: number) => void;
  /** The text before the choice: "Viewing as" for the pages that only read, "Acting as" for the ones that decide */
  label?: MessageKey;
  disabled?: boolean;
}) {
  const t = useT();
  // With a login the choice does not exist: the identity is the cookie, and the header shows who it is
  if (useAuth().state.status !== "demo") return null;
  return (
    <label className="flex flex-wrap items-center gap-2 text-sm font-medium" htmlFor={id}>
      {t(label)}
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {DEMO_APPROVERS.map((approver) => (
          <option key={approver.id} value={approver.id}>
            {`${approver.id} — ${t(approver.role === "headNurse" ? "role.headNurse" : "role.supervisor")}, ${
              approver.wardId === null ? t("role.everyWard") : wardName(approver.wardId)
            }`}
          </option>
        ))}
      </select>
    </label>
  );
}
