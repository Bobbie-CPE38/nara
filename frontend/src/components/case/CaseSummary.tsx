"use client";

import { useEffect, useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { isCaseSummary } from "@/lib/cases";
import { formatDateTime } from "@/lib/format";
import type { CaseSummaryView } from "@/lib/types/case";

const QUOTA_MESSAGE = "ใช้โควตาคำอธิบายจาก AI ครบแล้วในวันนี้ กรุณาลองใหม่ในวันถัดไป คุณยังดูอันดับและดำเนินการจัดเวรต่อได้ตามปกติ";

export function CaseSummary({ caseId, summary, onRequested }: {
  caseId: number; summary: CaseSummaryView | null; onRequested: () => Promise<void>;
}) {
  const request = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => () => { request.current?.abort(); }, [caseId]);
  const current = summary?.current;
  async function ask() {
    if (request.current || !current?.can_request) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError(null);
    try {
      const result = await apiRequest<unknown>(`/cases/${caseId}/summary`, {
        method: "POST", signal: controller.signal,
      });
      if (!isCaseSummary(result) || result === null) throw new Error("Unexpected summary response");
      if (!controller.signal.aborted) await onRequested();
    } catch {
      if (!controller.signal.aborted) {
        setError("ขอสรุปไม่สำเร็จ กรุณาตรวจสถานะล่าสุดแล้วลองใหม่");
        await onRequested();
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
      if (request.current === controller) request.current = null;
    }
  }
  return (
    <section className="mt-6">
      <h2 className="text-xl font-semibold">สรุปสถานการณ์ด้วย AI</h2>
      <p className="mt-1 text-sm text-gray-500">สรุปจากข้อมูลที่บันทึกไว้ โปรดใช้ข้อมูลในตารางประกอบการตัดสินใจ</p>
      {current?.stale && <p className="mt-2 text-amber-700">ข้อมูลเคสเปลี่ยนแล้ว สรุปฉบับนี้ล้าสมัย</p>}
      {current?.text && <p className="mt-2 whitespace-pre-wrap">{current.text}</p>}
      {current?.generated_at && <p className="text-sm text-gray-500">สร้างเมื่อ {formatDateTime(current.generated_at)}</p>}
      {current?.status === "PENDING" && <p role="status">กำลังสร้างสรุป กรุณารอสักครู่</p>}
      {current?.status === "UNAVAILABLE" && <p className="mt-2">ยังสร้างสรุปไม่สำเร็จ</p>}
      {current?.request_blocked_reason === "QUOTA_EXHAUSTED" && <p className="mt-2">{QUOTA_MESSAGE}</p>}
      {current?.request_blocked_reason === "NOT_CONFIGURED" && <p className="mt-2">ยังไม่ได้เปิดใช้งาน AI</p>}
      {current?.request_blocked_reason === "ATTEMPTS_EXHAUSTED" && <p className="mt-2">ใช้จำนวนครั้งที่ขอได้สำหรับข้อมูลฉบับนี้ครบแล้ว</p>}
      {current?.request_blocked_reason === "INVALID_INPUT" && <p className="mt-2">ข้อมูลฉบับนี้ยังไม่พร้อมสำหรับสร้างสรุป</p>}
      <button className="mt-2 rounded border border-slate-400 px-3 py-2 disabled:opacity-40"
        type="button" disabled={busy || !current?.can_request} onClick={() => void ask()}>
        {busy ? "กำลังขอสรุป…" : current?.stale ? "สร้างสรุปฉบับใหม่" : "ขอสรุปสถานการณ์ด้วย AI"}
      </button>
      {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
      {!!summary?.history.length && <details className="mt-3">
        <summary>สรุปฉบับก่อนหน้า</summary>
        <ul>{summary.history.map((row) => <li key={row.summary_id} className="mt-2 border-t pt-2">
          <p className="text-sm text-gray-500">{formatDateTime(row.generated_at)}</p>
          <p className="whitespace-pre-wrap">{row.text}</p>
        </li>)}</ul>
      </details>}
    </section>
  );
}
