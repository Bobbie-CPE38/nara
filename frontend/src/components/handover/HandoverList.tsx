"use client";

import Link from "next/link";
import { formatDateTime } from "@/lib/format";
import type { MessageKey, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { HandoverView } from "@/lib/types/case";

// Content keys of version 1 (docs/workflow.md 6.25). Other versions show these keys only.
type Shift = { id?: unknown; ward_name?: unknown; start_at?: unknown; end_at?: unknown };
type CoWorker = { staff_id?: unknown; name?: unknown; role_name?: unknown };
type Need = { name?: unknown; required_count?: unknown };

const REASON_KEYS: Record<string, MessageKey> = {
  UNPLANNED_LEAVE: "handoverReason.UNPLANNED_LEAVE",
  NO_SHOW: "handoverReason.NO_SHOW",
  ASSIGNMENT_CANCELLED: "handoverReason.ASSIGNMENT_CANCELLED",
  PATIENT_SURGE: "handoverReason.PATIENT_SURGE",
  REQUIREMENT_CHANGED: "handoverReason.REQUIREMENT_CHANGED",
};

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "—";
}

function time(value: unknown): string {
  return typeof value === "string" ? formatDateTime(value) : "—";
}

/** Whether a list item from the API has the shape of a handover; other items are skipped. */
export function isHandover(value: unknown): value is HandoverView {
  return (
    typeof value === "object" &&
    value !== null &&
    "handover_id" in value &&
    "content" in value &&
    typeof value.content === "object" &&
    value.content !== null
  );
}

/** "RN × 4, Head nurse × 1" from the role or skill list of content.requirement. */
function needs(value: unknown, t: Translate): string {
  if (!Array.isArray(value) || value.length === 0) return t("handover.none");
  return (value as Need[]).map((need) => `${text(need.name)} × ${text(need.required_count)}`).join(", ");
}

function HandoverCard({ handover, linkCase }: { handover: HandoverView; linkCase: boolean }) {
  const t = useT();
  const content = handover.content;
  const shift = (typeof content.shift === "object" && content.shift !== null
    ? content.shift
    : {}) as Shift;
  const coWorkers = Array.isArray(content.co_workers) ? (content.co_workers as CoWorker[]) : [];
  const reason = typeof content.reason === "string" ? content.reason : null;
  const reasonKey = reason === null ? undefined : REASON_KEYS[reason];
  const requirement = (typeof content.requirement === "object" && content.requirement !== null
    ? content.requirement
    : {}) as { roles?: unknown; skills?: unknown };
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <p className="font-semibold">
        {t("handover.shiftTitle", { id: text(shift.id), ward: text(shift.ward_name) })}{" "}
        {!handover.active && <span className="font-normal text-slate-500">{t("handover.history")}</span>}
      </p>
      <dl className="mt-1 grid grid-cols-2 gap-1 text-sm">
        <dt>{t("handover.yourHours")}</dt>
        <dd>
          {time(content.cover_start_at)} – {time(content.cover_end_at)}
        </dd>
        <dt>{t("handover.shiftHours")}</dt>
        <dd>
          {time(shift.start_at)} – {time(shift.end_at)}
        </dd>
        <dt>{t("handover.why")}</dt>
        <dd>{reason === null ? "—" : (reasonKey ? t(reasonKey) : reason)}</dd>
        <dt>{t("handover.patients")}</dt>
        <dd>{text(content.patient_count)}</dd>
        <dt>{t("handover.rolesNeeded")}</dt>
        <dd>{needs(requirement.roles, t)}</dd>
        <dt>{t("handover.skillsNeeded")}</dt>
        <dd>{needs(requirement.skills, t)}</dd>
        <dt>{t("handover.workingWith")}</dt>
        <dd>
          {coWorkers.length === 0
            ? t("handover.nobody")
            : coWorkers.map((person) => `${text(person.name)} (${text(person.role_name)})`).join(", ")}
        </dd>
        {linkCase && typeof content.case_id === "number" && (
          <>
            <dt>{t("common.case")}</dt>
            <dd>
              <Link className="underline" href={`/cases/${content.case_id}`}>
                {content.case_id}
              </Link>
            </dd>
          </>
        )}
        <dt>{t("handover.written")}</dt>
        <dd>{formatDateTime(handover.generated_at)}</dd>
      </dl>
    </li>
  );
}

/** Active handovers first, then history; each group keeps the API order (newest first). */
export function HandoverList({
  handovers,
  emptyText,
  linkCase = false,
}: {
  handovers: readonly unknown[];
  emptyText: string;
  linkCase?: boolean;
}) {
  const rows = handovers.filter(isHandover);
  if (rows.length === 0) return <p className="mt-2">{emptyText}</p>;
  const ordered = [...rows.filter((row) => row.active), ...rows.filter((row) => !row.active)];
  return (
    <ul className="mt-2 space-y-2">
      {ordered.map((handover) => (
        <HandoverCard key={handover.handover_id} handover={handover} linkCase={linkCase} />
      ))}
    </ul>
  );
}
