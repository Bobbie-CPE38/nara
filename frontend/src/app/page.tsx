"use client";

import { Suspense, useCallback, useMemo } from "react";
import { ActingAs } from "@/components/ActingAs";
import { DashboardView } from "@/components/dashboard/DashboardView";
import { SystemStatus } from "@/components/dashboard/SystemStatus";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { Dashboard } from "@/lib/types/dashboard";

function DashboardPage() {
  const t = useT();
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  const load = useCallback((signal: AbortSignal) => api<Dashboard>("/dashboard", { signal }), [api]);
  // Read again every 2 seconds like the approvals page; the read writes nothing
  const { data, error, isLoading } = usePolling(load);

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("dash.title")}>
        <ActingAs id="viewing-as" value={actorId} onChange={setActorId} />
      </PageHeader>
      {error && (
        <div className="mb-4">
          <Notice kind="error" role="alert">
            {error.message}
            {data && t("dash.staleNote")}
          </Notice>
        </div>
      )}
      {isLoading && !data && <p>{t("common.loading")}</p>}
      {data && <DashboardView data={data} actorId={actorId} />}
      <SystemStatus />
    </main>
  );
}

export default function Home() {
  return (
    <Suspense>
      <DashboardPage />
    </Suspense>
  );
}
