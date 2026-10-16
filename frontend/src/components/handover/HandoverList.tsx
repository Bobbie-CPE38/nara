import Link from "next/link";
import { formatDateTime } from "@/lib/format";
import type { HandoverView } from "@/lib/types/case";

// Content keys of version 1 (docs/workflow.md 6.25). Other versions show these keys only.
type Shift = { id?: unknown; ward_name?: unknown; start_at?: unknown; end_at?: unknown };
type CoWorker = { staff_id?: unknown; name?: unknown; role_name?: unknown };

const REASON_TEXT: Record<string, string> = {
  UNPLANNED_LEAVE: "Unplanned leave",
  NO_SHOW: "No-show",
  ASSIGNMENT_CANCELLED: "Assignment cancelled",
  PATIENT_SURGE: "Patient surge",
  REQUIREMENT_CHANGED: "Requirement changed",
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

function HandoverCard({ handover, linkCase }: { handover: HandoverView; linkCase: boolean }) {
  const content = handover.content;
  const shift = (typeof content.shift === "object" && content.shift !== null
    ? content.shift
    : {}) as Shift;
  const coWorkers = Array.isArray(content.co_workers) ? (content.co_workers as CoWorker[]) : [];
  const reason = typeof content.reason === "string" ? content.reason : null;
  return (
    <li className="rounded border border-slate-300 p-3">
      <p className="font-semibold">
        Shift {text(shift.id)} ({text(shift.ward_name)}){" "}
        {!handover.active && <span className="font-normal text-slate-500">— history, no longer active</span>}
      </p>
      <dl className="mt-1 grid grid-cols-2 gap-1 text-sm">
        <dt>Your hours</dt>
        <dd>
          {time(content.cover_start_at)} – {time(content.cover_end_at)}
        </dd>
        <dt>Shift hours</dt>
        <dd>
          {time(shift.start_at)} – {time(shift.end_at)}
        </dd>
        <dt>Why the shift was short</dt>
        <dd>{reason === null ? "—" : (REASON_TEXT[reason] ?? reason)}</dd>
        <dt>Patients</dt>
        <dd>{text(content.patient_count)}</dd>
        <dt>Working with</dt>
        <dd>
          {coWorkers.length === 0
            ? "Nobody else"
            : coWorkers.map((person) => `${text(person.name)} (${text(person.role_name)})`).join(", ")}
        </dd>
        {linkCase && typeof content.case_id === "number" && (
          <>
            <dt>Case</dt>
            <dd>
              <Link className="underline" href={`/cases/${content.case_id}`}>
                {content.case_id}
              </Link>
            </dd>
          </>
        )}
        <dt>Written</dt>
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
