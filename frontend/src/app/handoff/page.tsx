"use client";

import Link from "next/link";
import { Suspense, useCallback, useMemo, useState } from "react";
import { ScrollX } from "@/components/ScrollX";
import { ActingAs } from "@/components/ActingAs";
import { CaseFilters, type CaseQuery, searchPath } from "@/components/case/CaseFilters";
import { HandoffManager, OutcomeView } from "@/components/handoff/HandoffManager";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pager } from "@/components/ui/Pager";
import { useActor } from "@/hooks/useActor";
import { useManagedCase } from "@/hooks/useManagedCase";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { CLICKABLE_ROW, ROW_LINK, followRowLink } from "@/lib/rowClick";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CasePage, HandoffCase } from "@/lib/types/handoff";

const PAGE_SIZE = 10;

/** Handed off and failed cases, or one of the two (round 6 PR EV6, docs/workflow.md 6.36.6) */
const HANDOFF_STATUS_FILTERS = [
  { value: "MANUAL_HANDOFF,FAILED", label: "cases.filter.attention" },
  { value: "MANUAL_HANDOFF", label: "hand.filter.manual" },
  { value: "FAILED", label: "hand.filter.failed" },
] as const;

function shortByText(row: HandoffCase): string {
  if (row.headcount_gap === null) return "—";
  return String(Math.max(row.headcount_gap - row.assigned_count, 0));
}

function HandoffPage() {
  const t = useT();
  // Who acts: the user a link carried here (the Dashboard counts), else the Golden Case head
  // nurse (docs/workflow.md, section 10). The API shows each one their own ward
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  // Search, filter and pages of round 6 PR EV6; the oldest case first, as it waits the longest
  const [query, setQuery] = useState<CaseQuery>({ q: "", status: HANDOFF_STATUS_FILTERS[0].value, page: 1 });
  const loadCases = useCallback(
    (signal: AbortSignal) => api<CasePage>(searchPath(query, PAGE_SIZE, "oldest"), { signal }),
    [api, query],
  );
  const { data: page, error, isLoading, refresh } = usePolling(loadCases);
  const cases = page?.items;
  const managed = useManagedCase(cases);

  function changeActor(id: number) {
    // Nothing of the previous user's case may stay open: it belongs to another ward's list
    setActorId(id);
    setQuery((value) => ({ ...value, page: 1 }));
    managed.reset();
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("hand.title")} description={t("hand.intro")}>
        <ActingAs id="handoff-acting-as" value={actorId} onChange={changeActor} />
      </PageHeader>

      <Card>
        <CaseFilters query={query} statuses={HANDOFF_STATUS_FILTERS} onChange={setQuery} />
      </Card>
      <div className="mt-4 space-y-3">
        {error && <p className="text-red-700">{describeError(error, t)}</p>}
        {/* With the dialog open its own answers show in it */}
        {!managed.selected && <OutcomeView outcome={managed.outcome} />}
      </div>
      {isLoading && <p className="mt-4">{t("common.loading")}</p>}
      {cases && cases.length === 0 && <p className="mt-4">{t("hand.noCases")}</p>}
      {page && cases && cases.length > 0 && (
        <Card className="mt-4">
          <ScrollX>
            <table>
              <thead>
                <tr>
                  <th>{t("common.case")}</th>
                  <th>{t("cand.status")}</th>
                  <th>{t("common.ward")}</th>
                  <th>{t("common.shift")}</th>
                  <th>{t("hand.stillShort")}</th>
                  <th>{t("hand.openedAt")}</th>
                  <th>{t("offers.col.action")}</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((row) => (
                  <tr key={row.id} className={CLICKABLE_ROW} onClick={followRowLink}>
                    <td>
                      <Link className="underline" href={`/cases/${row.id}`}>
                        {row.id}
                      </Link>
                    </td>
                    <td>{row.status}</td>
                    <td>{row.ward_name}</td>
                    <td>{row.shift_id}</td>
                    <td>{shortByText(row)}</td>
                    <td>{formatDateTime(row.created_at)}</td>
                    <td>
                      <div className="flex flex-wrap items-center gap-2">
                        {row.can_manage ? (
                          <Button onClick={() => managed.open(row.id)}>
                            {t("hand.manage")}
                          </Button>
                        ) : (
                          // FAILED stays an end point (R2-Q22)
                          <span className="text-sm">{t("hand.cannotManage")}</span>
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
            page={page.page}
            pageSize={page.page_size}
            total={page.total}
            onPage={(next) => setQuery((value) => ({ ...value, page: next }))}
          />
        </Card>
      )}

      {/* Managing a case is a dialog over the list (round 6 PR EV6): the list stays put */}
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

export default function Handoff() {
  return (
    <Suspense>
      <HandoffPage />
    </Suspense>
  );
}
