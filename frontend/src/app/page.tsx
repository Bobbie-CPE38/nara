"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import { ActingAs } from "@/components/ActingAs";
import { DashboardView } from "@/components/dashboard/DashboardView";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { Dashboard } from "@/lib/types/dashboard";

function DashboardPage() {
  const t = useT();
  const [actorId, setActorId] = useActor();
  // One ward of the user's, or every ward (round 6 PR EV6); a new user starts with every ward
  const [ward, setWard] = useState<{ actorId: number; id: number | null }>({ actorId, id: null });
  const wardId = ward.actorId === actorId ? ward.id : null;
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  const load = useCallback(
    (signal: AbortSignal) =>
      api<Dashboard>(wardId === null ? "/dashboard" : `/dashboard?ward_id=${wardId}`, { signal }),
    [api, wardId],
  );
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
            {describeError(error, t)}
            {data && t("dash.staleNote")}
          </Notice>
        </div>
      )}
      {isLoading && !data && <p>{t("common.loading")}</p>}
      {data && (
        <DashboardView
          data={data}
          actorId={actorId}
          wardId={wardId}
          onWardChange={(id) => setWard({ actorId, id })}
        />
      )}
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
