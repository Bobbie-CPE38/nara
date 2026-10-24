"use client";

import Link from "next/link";
import { Suspense, useCallback, useMemo, useState } from "react";
import { ActingAs } from "@/components/ActingAs";
import { useSessionUser } from "@/components/AuthProvider";
import { CaseFilters, type CaseQuery, searchPath } from "@/components/case/CaseFilters";
import { HandoffManager, OutcomeView } from "@/components/handoff/HandoffManager";
import { ScrollX } from "@/components/ScrollX";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pager } from "@/components/ui/Pager";
import { useActor } from "@/hooks/useActor";
import { useManagedCase } from "@/hooks/useManagedCase";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { CASE_STATUS_INFO } from "@/lib/constants";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { CLICKABLE_ROW, ROW_LINK, followRowLink } from "@/lib/rowClick";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CasePage } from "@/lib/types/handoff";

const PAGE_SIZE = 20;

/** The status filter: every case, the ones that need a person, the running and the ended ones */
const CASE_STATUS_FILTERS = [
  { value: "", label: "cases.filter.all" },
  { value: "MANUAL_HANDOFF,FAILED", label: "cases.filter.attention" },
  {
    value: "OPEN,ASSESSING,OPTIMIZING,OUTREACH,WAITING_RESPONSE,SAFETY_VALIDATION,WAITING_APPROVAL,EXECUTING",
    label: "cases.filter.running",
  },
  { value: "RESOLVED,UNRESOLVED", label: "cases.filter.ended" },
] as const;

/**
 * Every case the user may read, newest first, with search, a status filter and pages (round 6
 * PR EV6, docs/workflow.md 6.36.6). Before it, a case was only reached by a link. A case in
 * MANUAL_HANDOFF has a Manage button that opens the dialog of the Handoff page here (round 6
 * PR EV8, 6.38.7); a nurse never has one, and the Backend checks every action again.
 */
function CaseListPage() {
  const t = useT();
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  const [query, setQuery] = useState<CaseQuery>({ q: "", status: "", page: 1 });
  const load = useCallback(
    (signal: AbortSignal) => api<CasePage>(searchPath(query, PAGE_SIZE, "newest"), { signal }),
    [api, query],
  );
  const { data, error, isLoading, refresh } = usePolling(load);
  const managed = useManagedCase(data?.items);
  const nurse = useSessionUser()?.role === "staff";

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("cases.title")} description={t("cases.intro")}>
        <ActingAs
          id="cases-viewing-as"
          value={actorId}
          onChange={(id) => {
            setActorId(id);
            setQuery((value) => ({ ...value, page: 1 }));
            managed.reset();
          }}
        />
      </PageHeader>
      <Card>
        <CaseFilters query={query} statuses={CASE_STATUS_FILTERS} onChange={setQuery} />
      </Card>
      {error && (
        <div className="mt-4">
          <Notice kind="error" role="alert">
            {describeError(error, t)}
          </Notice>
        </div>
      )}
      {!managed.selected && managed.outcome && (
        <div className="mt-4">
          <OutcomeView outcome={managed.outcome} />
        </div>
      )}
      {isLoading && !data && <p className="mt-4">{t("common.loading")}</p>}
      {data && data.items.length === 0 && <p className="mt-4">{t("cases.empty")}</p>}
      {data && data.items.length > 0 && (
        <Card className="mt-4">
          <ScrollX>
            <table aria-label={t("cases.title")}>
              <thead>
                <tr>
                  <th>{t("common.case")}</th>
                  <th>{t("cand.status")}</th>
                  <th>{t("common.ward")}</th>
                  <th>{t("common.shift")}</th>
                  <th>{t("hand.stillShort")}</th>
                  <th>{t("hand.openedAt")}</th>
                  <th>
                    <span className="sr-only">{t("cases.seeDetails")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr
                    key={row.id}
                    className={CLICKABLE_ROW}
                    onClick={followRowLink}
                  >
                    <td>
                      <Link className="underline" href={`/cases/${row.id}`}>
                        {row.id}
                      </Link>
                    </td>
                    <td>
                      <Badge tone={CASE_STATUS_INFO.get(row.status)?.tone ?? "neutral"}>{row.status}</Badge>
                    </td>
                    <td>{row.ward_name}</td>
                    <td className="whitespace-nowrap">
                      {t("cases.shiftCell", {
                        id: row.shift_id,
                        type: row.shift_type,
                        start: formatDateTime(row.shift_start_at).slice(0, 16),
                      })}
                    </td>
                    <td>
                      {row.headcount_gap === null ? "—" : Math.max(row.headcount_gap - row.assigned_count, 0)}
                    </td>
                    <td className="whitespace-nowrap">{formatDateTime(row.created_at)}</td>
                    <td>
                      <div className="flex flex-wrap items-center gap-2">
                        {row.can_manage && !nurse && (
                          <Button onClick={() => managed.open(row.id)}>{t("hand.manage")}</Button>
                        )}
                        <Link {...ROW_LINK} className="whitespace-nowrap font-medium text-brand-700 underline" href={`/cases/${row.id}`}>
                          {t("cases.seeDetails")}
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollX>
          <Pager
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPage={(page) => setQuery((value) => ({ ...value, page }))}
          />
        </Card>
      )}
      {managed.selected && (
        <HandoffManager
          key={managed.selected.id}
          caseId={managed.selected.id}
          api={api}
          onClose={managed.close}
          onDone={managed.done}
          onChanged={refresh}
        />
      )}
    </main>
  );
}

export default function CaseList() {
  return (
    <Suspense>
      <CaseListPage />
    </Suspense>
  );
}
