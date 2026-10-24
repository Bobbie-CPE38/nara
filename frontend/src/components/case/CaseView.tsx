"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AuditTimeline } from "@/components/audit/AuditTimeline";
import { CandidateTable } from "@/components/candidate/CandidateTable";
import { type ExplanationRequest, ScoreBreakdown } from "@/components/candidate/ScoreBreakdown";
import { SkippedTable } from "@/components/candidate/SkippedTable";
import { CANDIDATES_ID, CaseOverviewCard } from "@/components/case/CaseOverviewCard";
import { CaseSummary } from "@/components/case/CaseSummary";
import { CaseManagement } from "@/components/case/CaseManagement";
import { GapTable } from "@/components/case/GapTable";
import { HandoverList } from "@/components/handover/HandoverList";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, apiRequest } from "@/lib/api";
import { type CaseSnapshot, collectSkips, explanationRequestKey, isCaseId, loadCase } from "@/lib/cases";
import {
  CASE_STATUS_INFO,
  EXPLANATION_REQUEST_TIMEOUT_MS,
  POLL_INTERVAL_MS,
  TERMINAL_CASE_STATUSES,
} from "@/lib/constants";
import { describeError } from "@/lib/errors";
import { formatDateTime, formatValue } from "@/lib/format";
import type { MessageKey, Translate } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";

function isFinal({ detail }: CaseSnapshot) {
  return TERMINAL_CASE_STATUSES.has(detail.status);
}

// The sentence comes from the job after the case may already be final: keep reading until it
// is READY or UNAVAILABLE. No explanation row (LLM off, old plan) gives nothing to wait for.
function isWaitingForExplanation({ detail }: CaseSnapshot) {
  return detail.explanation?.status === "PENDING";
}

function isWaitingForSummary({ detail }: CaseSnapshot) {
  return detail.summary?.current.status === "PENDING";
}

// A handover stays active after the case ends, until its row ends or the nurse is moved out
// (section 6.25): keep reading so the section turns it into history.
function hasActiveHandover({ detail }: CaseSnapshot) {
  return (detail.handovers ?? []).some((handover) => handover.active);
}

function isDone(snapshot: CaseSnapshot) {
  return isFinal(snapshot) && !isWaitingForExplanation(snapshot) && !isWaitingForSummary(snapshot) && !hasActiveHandover(snapshot);
}

// 404: no such case. 422: the ID is outside the bigint range. A retry gives the same answer.
function isGone(error: Error) {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

/** Which line says whether the page keeps reading (docs/workflow.md 6.25, 6.27). */
function liveKey(snapshot: CaseSnapshot): MessageKey {
  if (!isFinal(snapshot)) return "case.live";
  if (isWaitingForExplanation(snapshot)) return "case.liveExplanation";
  if (isWaitingForSummary(snapshot)) return "case.liveSummary";
  if (hasActiveHandover(snapshot)) return "case.liveHandover";
  return "case.stopped";
}

function CaseSections({ detail, audit, request, onSummaryRequested }: CaseSnapshot & { request: ExplanationRequest; onSummaryRequested: () => Promise<void> }) {
  const t = useT();
  const info = CASE_STATUS_INFO.get(detail.status);
  const skips = collectSkips(audit);
  // FAILED is a normal answer. Its reason is only in the audit, and only as an error type.
  const failure = detail.status === "FAILED"
    ? audit.findLast(entry => entry.action === "WORKFLOW_FAILED")
    : undefined;
  return (
    <div className="space-y-4">
      <Card>
        <p>
          {t("case.status")}{" "}
          <Badge tone={info?.tone ?? "neutral"} as="strong">{detail.status}</Badge>
          {info && <span className="ml-2">{t(info.messageKey)}</span>}
        </p>
        {failure && (
          <p className="text-red-700">
            {t("case.failedAt", { at: formatValue(failure.payload.failed_at), error: formatValue(failure.payload.error_type) })}
          </p>
        )}
        <p className="mt-1 text-sm text-slate-500">{t(liveKey({ detail, audit }), { seconds: POLL_INTERVAL_MS / 1000 })}</p>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-[max-content_1fr]">
          <dt className="font-medium">{t("common.shift")}</dt>
          <dd>{detail.shift_id}</dd>
          <dt className="font-medium">{t("case.events")}</dt>
          <dd>{detail.event_ids.join(", ")}</dd>
          <dt className="font-medium">{t("case.replacementBy")}</dt>
          <dd>{formatDateTime(detail.required_replacement_time)}</dd>
          <dt className="font-medium">{t("case.opened")}</dt>
          <dd>{formatDateTime(detail.created_at)}</dd>
          <dt className="font-medium">{t("case.updated")}</dt>
          <dd>{formatDateTime(detail.updated_at)}</dd>
        </dl>
      </Card>
      {detail.overview && <CaseOverviewCard overview={detail.overview} caseStatus={detail.status} />}
      <Card title={t("common.gap")}>
        {detail.gap ? <GapTable gap={detail.gap} /> : <p className="mt-2">{t("case.notAssessed")}</p>}
      </Card>
      {/* The replacement summary's "See the candidates" jumps here */}
      <div id={CANDIDATES_ID} className="scroll-mt-28">
        <Card title={t("case.candidates")}>
          <CandidateTable
            candidates={detail.candidates}
            stopped={isFinal({ detail, audit }) || detail.status === "MANUAL_HANDOFF"}
          />
          <ScoreBreakdown candidates={detail.candidates} explanation={detail.explanation} partialPlan={detail.partial_plan} request={request} />
          {skips.length > 0 && (
            <>
              <h3 className="mt-4">{t("case.skipped")}</h3>
              <SkippedTable skips={skips} candidates={detail.candidates} />
            </>
          )}
        </Card>
      </div>
      <CaseSummary caseId={detail.id} summary={detail.summary} onRequested={onSummaryRequested} />
      <Card title={t("case.handovers")}>
        <HandoverList handovers={detail.handovers ?? []} emptyText={t("case.noHandover")} />
      </Card>
      <Card title={t("case.timeline")}>
        <AuditTimeline entries={audit} />
      </Card>
    </div>
  );
}

export function CaseView({ caseId }: { caseId: string }) {
  const t = useT();
  const valid = isCaseId(caseId);
  const load = useCallback((signal: AbortSignal) => loadCase(caseId, signal), [caseId]);
  const { data, error, isLoading, refresh } = usePolling(load, {
    intervalMs: POLL_INTERVAL_MS,
    enabled: valid,
    stopOnData: isDone,
    stopOnError: isGone,
  });
  const [requesting, setRequesting] = useState(false);
  const [requestMessage, setRequestMessage] = useState<MessageKey | null>(null);
  // A ref as well: two clicks before the next render must make one request
  const requestingRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);
  // An old message must not outlive the state it was about: clear it when the explanation changes
  const explanation = data?.detail.explanation;
  const explanationState = `${explanation?.status}/${explanation?.can_request}/${explanation?.request_blocked_reason}`;
  useEffect(() => { setRequestMessage(null); }, [explanationState]);
  // Asks for the AI explanation of the latest plan (docs/workflow.md 9.8). The Job writes the
  // sentence later, so the answer is read again and polling goes on while it is PENDING.
  // Every refusal is read again too: can_request tells the truth about what is allowed now.
  const requestExplanation = useCallback(async () => {
    if (requestingRef.current) return;
    requestingRef.current = true;
    setRequesting(true);
    setRequestMessage(null);
    // A request that never answers is given up, so the button comes back with a retry message
    const controller = new AbortController();
    controllerRef.current = controller;
    const timer = setTimeout(() => controller.abort(), EXPLANATION_REQUEST_TIMEOUT_MS);
    try {
      await apiRequest(`/cases/${caseId}/explanation`, { method: "POST", signal: controller.signal });
    } catch (cause) {
      if (mountedRef.current) setRequestMessage(explanationRequestKey(cause));
    } finally {
      clearTimeout(timer);
      controllerRef.current = null;
      requestingRef.current = false;
      if (mountedRef.current) setRequesting(false);
    }
    // Read again either way: a request that timed out may still have been accepted
    if (mountedRef.current) await refresh();
  }, [caseId, refresh]);
  const httpStatus = error instanceof ApiError ? error.status : undefined;

  let body;
  if (!valid || httpStatus === 422) {
    body = <p className="mt-4 text-red-700">{t("case.invalidId")}</p>;
  } else if (httpStatus === 404) {
    // Also after a demo reset: data of the case that is gone must not stay on screen.
    body = <p className="mt-4 text-red-700">{t("case.notFound", { id: caseId })}</p>;
  } else if (!data) {
    body = isLoading || !error
      ? <p className="mt-4" role="status">{t("common.loading")}</p>
      : <p className="mt-4 text-red-700" role="alert">{t("case.retrying", { error: describeError(error, t) })}</p>;
  } else {
    body = (
      <>
        {error && (
          <div className="mb-3">
            <Notice kind="warning" role="alert">
              {t("case.updateFailed", { error: describeError(error, t) })}
            </Notice>
          </div>
        )}
        <CaseSections detail={data.detail} audit={data.audit} request={{ busy: requesting, message: requestMessage, onRequest: requestExplanation }} onSummaryRequested={refresh} />
      </>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={valid ? t("case.title", { id: caseId }) : t("case.titleGeneric")}>
        {valid && data && httpStatus !== 403 && httpStatus !== 404 && httpStatus !== 422 && (
          <Suspense>
            <CaseManagement caseId={caseId} status={data.detail.status} onChanged={refresh} />
          </Suspense>
        )}
      </PageHeader>
      {body}
    </main>
  );
}
