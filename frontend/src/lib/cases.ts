import { apiRequest } from "@/lib/api";
import type { AuditEntry, CaseDetail } from "@/lib/types/case";

export type SkipRecord = { key: string; origin: string; staffId: number; reason: string };

export type CaseSnapshot = { detail: CaseDetail; audit: AuditEntry[] };

/** A positive integer of at most 19 digits. Kept as text: a number would round IDs above 2^53. */
export function isCaseId(value: string): boolean {
  return /^[1-9]\d{0,18}$/.test(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRecordList(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every(isRecord);
}

/** A record with a string name and finite numbers for value, weight and points. */
function isScoreTerm(value: unknown): boolean {
  return isRecord(value) && typeof value.name === "string"
    && Number.isFinite(value.value) && Number.isFinite(value.weight) && Number.isFinite(value.points);
}

/** null, or a record with a finite total, a boolean first_wave and a list of valid score terms. */
function isScore(value: unknown): boolean {
  return value === null || (
    isRecord(value) && Number.isFinite(value.total)
    && typeof value.first_wave === "boolean" && Array.isArray(value.terms) && value.terms.every(isScoreTerm)
  );
}

function isCaseDetail(value: unknown): value is CaseDetail {
  if (!isRecord(value) || typeof value.status !== "string") return false;
  const { gap, candidates } = value;
  const gapOk =
    gap === null || (isRecord(gap) && isRecordList(gap.roles) && isRecordList(gap.skills));
  return gapOk && isRecordList(candidates) && candidates.every(candidate => isScore(candidate.score));
}

function isAuditList(value: unknown): value is AuditEntry[] {
  return isRecordList(value) && value.every(entry => isRecord(entry.payload));
}

/** Both public reads of a case (docs/workflow.md, section 9.3). */
export async function loadCase(caseId: string, signal: AbortSignal): Promise<CaseSnapshot> {
  if (!isCaseId(caseId)) throw new Error("Invalid case ID");
  const detail = await apiRequest<unknown>(`/cases/${caseId}`, { signal });
  // Audit second: a status is committed together with its audit rows (D4), so
  // this read holds every row of the status above, including a final one.
  const audit = await apiRequest<unknown>(`/cases/${caseId}/audit`, { signal });
  if (!isCaseDetail(detail) || !isAuditList(audit)) {
    throw new Error("Unexpected response from the API");
  }
  return { detail, audit };
}

/** Candidates skipped when a wave was selected, from the audit (docs/workflow.md, section 6.7). */
export function collectSkips(audit: AuditEntry[]): SkipRecord[] {
  const records: SkipRecord[] = [];
  for (const entry of audit) {
    if (entry.action !== "OFFER_SENT" && entry.action !== "MANUAL_HANDOFF") continue;
    const { skipped, wave } = entry.payload;
    if (!Array.isArray(skipped)) continue;
    const origin = entry.action === "MANUAL_HANDOFF"
      ? "Handoff"
      : typeof wave === "number" ? `Wave ${wave}` : "Wave";
    skipped.forEach((item: unknown, index: number) => {
      if (!isRecord(item) || typeof item.staff_id !== "number" || typeof item.reason !== "string") return;
      records.push({ key: `${entry.id}-${index}`, origin, staffId: item.staff_id, reason: item.reason });
    });
  }
  return records;
}
