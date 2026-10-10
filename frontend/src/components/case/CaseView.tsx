"use client";

import { useCallback } from "react";
import { AuditTimeline } from "@/components/audit/AuditTimeline";
import { CandidateTable } from "@/components/candidate/CandidateTable";
import { GapTable } from "@/components/case/GapTable";
import { usePolling } from "@/hooks/usePolling";
import { ApiError } from "@/lib/api";
import { type CaseSnapshot, isCaseId, loadCase } from "@/lib/cases";
import {
  CASE_STATUS_INFO,
  POLL_INTERVAL_MS,
  type StatusTone,
  TERMINAL_CASE_STATUSES,
} from "@/lib/constants";
import { formatDateTime, formatValue } from "@/lib/format";

const TONE_CLASS: Record<StatusTone, string> = {
  ok: "text-green-700",
  bad: "text-red-700",
  waiting: "text-amber-700",
  neutral: "",
};

function isFinal({ detail }: CaseSnapshot) {
  return TERMINAL_CASE_STATUSES.has(detail.status);
}

// 404: no such case. 422: the ID is outside the bigint range. A retry gives the same answer.
function isGone(error: Error) {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

function describe(error: Error) {
  // fetch reports an unreachable server as a TypeError with a browser-specific text.
  return error instanceof TypeError
    ? "Cannot reach the API. Check that the backend is running."
    : error.message;
}

function CaseSections({ detail, audit }: CaseSnapshot) {
  const info = CASE_STATUS_INFO.get(detail.status);
  // FAILED is a normal answer. Its reason is only in the audit, and only as an error type.
  const failure = detail.status === "FAILED"
    ? audit.findLast(entry => entry.action === "WORKFLOW_FAILED")
    : undefined;
  return (
    <>
      <section className="mt-4">
        <p>
          Status:{" "}
          <strong className={TONE_CLASS[info?.tone ?? "neutral"]}>{detail.status}</strong>
          {info && <span className="ml-2">{info.meaning}</span>}
        </p>
        {failure && (
          <p className="text-red-700">
            Failed at {formatValue(failure.payload.failed_at)}: {formatValue(failure.payload.error_type)}
          </p>
        )}
        <p className="text-sm text-gray-500">
          {isFinal({ detail, audit }) ? "Final status. Updates stopped." : "Updating every 2 seconds."}
        </p>
        <dl className="mt-2 grid grid-cols-2 gap-2">
          <dt>Shift</dt>
          <dd>{detail.shift_id}</dd>
          <dt>Event</dt>
          <dd>{detail.event_id}</dd>
          <dt>Replacement needed by</dt>
          <dd>{formatDateTime(detail.required_replacement_time)}</dd>
          <dt>Opened</dt>
          <dd>{formatDateTime(detail.created_at)}</dd>
          <dt>Updated</dt>
          <dd>{formatDateTime(detail.updated_at)}</dd>
        </dl>
      </section>
      <section className="mt-6">
        <h2 className="text-xl font-semibold">Gap</h2>
        {detail.gap ? <GapTable gap={detail.gap} /> : <p className="mt-2">Not assessed yet.</p>}
      </section>
      <section className="mt-6">
        <h2 className="text-xl font-semibold">Candidates</h2>
        <CandidateTable candidates={detail.candidates} />
      </section>
      <section className="mt-6">
        <h2 className="text-xl font-semibold">Timeline</h2>
        <AuditTimeline entries={audit} />
      </section>
    </>
  );
}

export function CaseView({ caseId }: { caseId: string }) {
  const valid = isCaseId(caseId);
  const load = useCallback((signal: AbortSignal) => loadCase(caseId, signal), [caseId]);
  const { data, error, isLoading } = usePolling(load, {
    intervalMs: POLL_INTERVAL_MS,
    enabled: valid,
    stopOnData: isFinal,
    stopOnError: isGone,
  });
  const httpStatus = error instanceof ApiError ? error.status : undefined;

  let body;
  if (!valid || httpStatus === 422) {
    body = <p className="mt-4 text-red-700">Invalid case ID.</p>;
  } else if (httpStatus === 404) {
    // Also after a demo reset: data of the case that is gone must not stay on screen.
    body = <p className="mt-4 text-red-700">Case {caseId} not found.</p>;
  } else if (!data) {
    body = isLoading || !error
      ? <p className="mt-4" role="status">Loading…</p>
      : <p className="mt-4 text-red-700" role="alert">{describe(error)} Retrying…</p>;
  } else {
    body = (
      <>
        {error && (
          <p className="mt-2 text-sm text-amber-700" role="alert">
            Last update failed: {describe(error)} Showing the last known data. Retrying…
          </p>
        )}
        <CaseSections detail={data.detail} audit={data.audit} />
      </>
    );
  }

  return (
    <main className="mx-auto max-w-5xl p-8">
      <h1 className="text-2xl font-semibold">{valid ? `Case ${caseId}` : "Case"}</h1>
      {body}
    </main>
  );
}
