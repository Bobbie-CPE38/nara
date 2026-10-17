"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { apiRequest } from "@/lib/api";
import { isCaseSummary } from "@/lib/cases";
import { formatDateTime } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CaseSummaryView } from "@/lib/types/case";

/** Why a summary cannot be asked for now, by request_blocked_reason. */
const BLOCKED_KEYS: Record<string, MessageKey> = {
  QUOTA_EXHAUSTED: "ai.blockedQuota",
  NOT_CONFIGURED: "sum.notConfigured",
  ATTEMPTS_EXHAUSTED: "sum.attempts",
  INVALID_INPUT: "sum.invalidInput",
};

export function CaseSummary({ caseId, summary, onRequested }: {
  caseId: number; summary: CaseSummaryView | null; onRequested: () => Promise<void>;
}) {
  const t = useT();
  const request = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => () => { request.current?.abort(); }, [caseId]);
  const current = summary?.current;
  async function ask() {
    if (request.current || !current?.can_request) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setFailed(false);
    try {
      const result = await apiRequest<unknown>(`/cases/${caseId}/summary`, {
        method: "POST", signal: controller.signal,
      });
      if (!isCaseSummary(result) || result === null) throw new Error("Unexpected summary response");
      if (!controller.signal.aborted) await onRequested();
    } catch {
      if (!controller.signal.aborted) {
        setFailed(true);
        await onRequested();
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
      if (request.current === controller) request.current = null;
    }
  }
  const blockedKey = current?.request_blocked_reason ? BLOCKED_KEYS[current.request_blocked_reason] : undefined;
  return (
    <Card title={t("sum.title")} className="mt-4">
      <p className="mt-1 text-sm text-slate-600">{t("sum.note")}</p>
      {current?.stale && <p className="mt-2 font-medium text-amber-700">{t("sum.stale")}</p>}
      {current?.text && <p className="mt-2 whitespace-pre-wrap">{current.text}</p>}
      {current?.generated_at && (
        <p className="text-sm text-slate-500">{t("sum.created", { time: formatDateTime(current.generated_at) })}</p>
      )}
      {current?.status === "PENDING" && <p role="status">{t("sum.pending")}</p>}
      {current?.status === "UNAVAILABLE" && <p className="mt-2">{t("sum.unavailable")}</p>}
      {blockedKey && <p className="mt-2">{t(blockedKey)}</p>}
      <Button
        variant="primary"
        className="mt-3"
        disabled={busy || !current?.can_request}
        onClick={() => void ask()}
      >
        {busy ? t("sum.buttonBusy") : current?.stale ? t("sum.buttonNew") : t("sum.button")}
      </Button>
      {failed && <p role="alert" className="mt-2 text-red-700">{t("sum.failed")}</p>}
      {!!summary?.history.length && <details className="mt-3">
        <summary>{t("sum.history")}</summary>
        <ul>{summary.history.map((row) => <li key={row.summary_id} className="mt-2 border-t pt-2">
          <p className="text-sm text-slate-500">{formatDateTime(row.generated_at)}</p>
          <p className="whitespace-pre-wrap">{row.text}</p>
        </li>)}</ul>
      </details>}
    </Card>
  );
}
