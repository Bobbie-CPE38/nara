"use client";

import { type FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { ScrollX } from "@/components/ScrollX";
import { ApiError, apiRequest } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageProvider";

type Staff = {
  id: number; first_name: string; last_name: string; role: string;
  ward_name: string; status: string; line_linked: boolean;
};
type StaffPage = { items: Staff[]; total: number };
type Code = { code: string; expires_at: string };
const PAGE_SIZE = 25;

function Directory() {
  const t = useT();
  const [input, setInput] = useState("");
  const [query, setQuery] = useState({ q: "", offset: 0, revision: 0 });
  const [data, setData] = useState<StaffPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [issueFailure, setIssueFailure] = useState<unknown>(null);
  // Codes stay in component memory only: never localStorage, URLs, or console logs.
  const [issued, setIssued] = useState<{ staff: Staff; result: Code } | null>(null);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFailure(null);
    setData(null);
    setIssued(null);
    void apiRequest<StaffPage>(`/admin/staff?q=${encodeURIComponent(query.q)}&offset=${query.offset}&limit=${PAGE_SIZE}`, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setFailure(error); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query]);

  function search(event: FormEvent) {
    event.preventDefault();
    setQuery((value) => ({ q: input.trim(), offset: 0, revision: value.revision + 1 }));
    setIssueFailure(null);
  }

  async function issue(staff: Staff) {
    setBusy(staff.id);
    setIssued(null);
    setIssueFailure(null);
    setCopyStatus("idle");
    try {
      const result = await apiRequest<Code>(`/admin/staff/${staff.id}/line-code`, { method: "POST" });
      setIssued({ staff, result });
    } catch (error) {
      setIssueFailure(error);
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(`LINK ${issued.result.code}`);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  }

  const detail = issueFailure instanceof ApiError && typeof issueFailure.body === "object" && issueFailure.body !== null && "detail" in issueFailure.body ? issueFailure.body.detail : null;
  return (
    <div className="space-y-4">
      <Card>
        <form onSubmit={search} className="flex flex-wrap items-end gap-3">
          <div className="flex-1">
            <label htmlFor="staff-search" className="block">{t("staff.search")}</label>
            <input id="staff-search" className="w-full" maxLength={100} value={input} onChange={(e) => setInput(e.target.value)} disabled={busy !== null} />
          </div>
          <Button type="submit" disabled={busy !== null}>{t("staff.find")}</Button>
        </form>
      </Card>
      {issueFailure !== null && <Notice kind="error" role="alert">{detail === "LINE_ALREADY_LINKED" ? t("staff.alreadyLinked") : detail === "LINE_STAFF_UNAVAILABLE" ? t("staff.unavailable") : t("staff.issueFailed", { error: describeError(issueFailure, t) })}</Notice>}
      {issued && (
        <Card>
          <h2 className="font-semibold">{t("staff.codeFor", { id: issued.staff.id, name: `${issued.staff.first_name} ${issued.staff.last_name}` })}</h2>
          <p className="my-3 break-all select-all rounded bg-brand-50 p-3 font-mono">LINK {issued.result.code}</p>
          <p>{t("staff.expires", { time: formatDateTime(issued.result.expires_at) })}</p>
          <p className="my-2">{t("staff.instructions")}</p>
          <div className="flex gap-3">
            <Button onClick={() => void copy()}>{t("staff.copy")}</Button>
            <Button onClick={() => setIssued(null)}>{t("staff.dismiss")}</Button>
          </div>
          {copyStatus !== "idle" && <p role="status">{t(copyStatus === "copied" ? "staff.copied" : "staff.copyFailed")}</p>}
        </Card>
      )}
      {loading && <p role="status">{t("staff.loading")}</p>}
      {failure !== null && <Notice kind="error" role="alert">{t("staff.failed", { error: describeError(failure, t) })}</Notice>}
      {data && <Card>
        <p className="mb-3">{t("staff.total", { total: data.total })}</p>
        {data.items.length === 0 ? <p>{t("staff.empty")}</p> : <ScrollX><table className="w-full text-left text-sm">
          <thead><tr>{(["staff.id", "staff.name", "staff.ward", "staff.status", "staff.line"] as const).map((key) => <th key={key} className="p-2">{t(key)}</th>)}<th><span className="sr-only">{t("staff.issue")}</span></th></tr></thead>
          <tbody>{data.items.map((staff) => <tr key={staff.id} className="border-t border-slate-200">
            <td className="p-2">{staff.id}</td><td className="p-2">{staff.first_name} {staff.last_name}</td><td className="p-2">{staff.ward_name}</td>
            <td className="p-2">{t(staff.status === "ACTIVE" ? "staff.active" : "staff.inactive")}</td><td className="p-2">{t(staff.line_linked ? "staff.linked" : "staff.unlinked")}</td>
            <td className="p-2"><Button disabled={busy !== null || staff.line_linked || staff.status !== "ACTIVE"} onClick={() => void issue(staff)}>{t(busy === staff.id ? "staff.issuing" : "staff.issue")}</Button></td>
          </tr>)}</tbody>
        </table></ScrollX>}
        <div className="mt-3 flex gap-3">
          <Button disabled={busy !== null || query.offset === 0} onClick={() => setQuery((value) => ({ ...value, offset: Math.max(0, value.offset - PAGE_SIZE) }))}>{t("staff.previous")}</Button>
          <Button disabled={busy !== null || query.offset + PAGE_SIZE >= data.total} onClick={() => setQuery((value) => ({ ...value, offset: value.offset + PAGE_SIZE }))}>{t("staff.next")}</Button>
        </div>
      </Card>}
    </div>
  );
}

export default function StaffManagementPage() {
  const t = useT();
  const { state } = useAuth();
  const allowed = state.status === "authenticated" && state.me.role === "supervisor" && !state.me.must_change_password;
  return <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
    <PageHeader title={t("staff.title")} description={t("staff.description")} />
    {allowed ? <Directory key={state.me.staff_id} /> : <Notice>{t("staff.restricted")}</Notice>}
  </main>;
}
