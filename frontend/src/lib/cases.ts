import { apiRequest } from "@/lib/api";
import type { AuditEntry, CaseDetail } from "@/lib/types/case";

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

function isCaseDetail(value: unknown): value is CaseDetail {
  if (!isRecord(value) || typeof value.status !== "string") return false;
  const { gap, candidates } = value;
  const gapOk =
    gap === null || (isRecord(gap) && isRecordList(gap.roles) && isRecordList(gap.skills));
  return gapOk && isRecordList(candidates);
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
