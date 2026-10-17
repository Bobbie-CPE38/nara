import { ApiError, apiRequest } from "@/lib/api";
import { UnexpectedResponseError } from "@/lib/errors";
import type { MessageKey } from "@/lib/i18n";
import type { AuditEntry, CaseDetail, CaseSummaryView } from "@/lib/types/case";

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

/** Statuses that carry no text (round 6 PR E1 added NOT_REQUESTED and QUOTA_EXHAUSTED). */
const TEXTLESS_EXPLANATION_STATUSES: unknown[] = ["NOT_REQUESTED", "PENDING", "UNAVAILABLE", "QUOTA_EXHAUSTED"];

const EXPLANATION_BLOCKS: unknown[] = [
  "ALREADY_READY", "PENDING", "NOT_CONFIGURED", "INVALID_INPUT", "ATTEMPTS_EXHAUSTED", "QUOTA_EXHAUSTED",
];

/** null, or a known status with the request flag (round 6 PR E2); READY needs a non-empty text and a known provider. */
function isExplanation(value: unknown): boolean {
  if (value === null) return true;
  if (!isRecord(value)) return false;
  // can_request is the only thing that opens the button, so a missing flag is an unexpected response
  if (typeof value.can_request !== "boolean") return false;
  if (value.request_blocked_reason !== null && !EXPLANATION_BLOCKS.includes(value.request_blocked_reason)) return false;
  if (TEXTLESS_EXPLANATION_STATUSES.includes(value.status)) return true;
  return value.status === "READY" && typeof value.text === "string" && value.text !== ""
    && (value.provider === "fake" || value.provider === "bedrock");
}

const SUMMARY_BLOCKS = [null, "ALREADY_READY", "PENDING", "NOT_CONFIGURED", "INVALID_INPUT", "ATTEMPTS_EXHAUSTED", "QUOTA_EXHAUSTED"];

export function isCaseSummary(value: unknown): value is CaseSummaryView | null {
  if (value === null) return true;
  if (!isRecord(value) || !isRecord(value.current) || !Array.isArray(value.history)) return false;
  const row = value.current;
  return (row.status === "READY" || TEXTLESS_EXPLANATION_STATUSES.includes(row.status))
    && (row.summary_id === null || (Number.isSafeInteger(row.summary_id) && Number(row.summary_id) > 0))
    && typeof row.stale === "boolean" && typeof row.can_request === "boolean"
    && SUMMARY_BLOCKS.includes(row.request_blocked_reason as string | null)
    && (row.can_request === (row.request_blocked_reason === null))
    && (row.generated_at === null || typeof row.generated_at === "string")
    && (row.status === "READY" ? typeof row.text === "string" && row.text.length > 0 : row.text === null)
    && value.history.every((old) => isRecord(old) && Number.isSafeInteger(old.summary_id)
      && typeof old.text === "string" && old.text.length > 0 && typeof old.generated_at === "string");
}

/**
 * What to tell the user when POST /cases/{id}/explanation or /summary is refused (docs/workflow.md 9.8):
 * the key of the text, which the page shows in the language of the user.
 */
export function explanationRequestKey(error: unknown): MessageKey {
  if (error instanceof ApiError) {
    const detail = isRecord(error.body) && isRecord(error.body.detail) ? error.body.detail : undefined;
    switch (detail?.code) {
      case "LLM_QUOTA_EXHAUSTED": return "ai.blockedQuota";
      case "LLM_ATTEMPTS_EXHAUSTED": return "ai.blockedAttempts";
      case "LLM_UNAVAILABLE": return "ai.refused";
      case "CASE_NOT_FOUND": return "ai.notFound";
    }
  }
  return "ai.requestFailed";
}

function isCaseDetail(value: unknown): value is CaseDetail {
  if (!isRecord(value) || typeof value.status !== "string") return false;
  const { gap, candidates } = value;
  const gapOk =
    gap === null || (isRecord(gap) && isRecordList(gap.roles) && isRecordList(gap.skills));
  return gapOk && isRecordList(candidates) && candidates.every(candidate => isScore(candidate.score))
    && value.explanation !== undefined && isExplanation(value.explanation)
    && value.summary !== undefined && isCaseSummary(value.summary);
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
    throw new UnexpectedResponseError();
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
