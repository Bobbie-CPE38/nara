"use client";

import { Suspense, useCallback, useMemo } from "react";
import { ActingAs } from "@/components/ActingAs";
import { DashboardView } from "@/components/dashboard/DashboardView";
import { SystemStatus } from "@/components/dashboard/SystemStatus";
import { useActor } from "@/hooks/useActor";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import type { Dashboard } from "@/lib/types/dashboard";

function Dashboard() {
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  const load = useCallback((signal: AbortSignal) => api<Dashboard>("/dashboard", { signal }), [api]);
  // Read again every 2 seconds like the approvals page; the read writes nothing
  const { data, error, isLoading } = usePolling(load);

  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <div className="mt-1">
        <ActingAs id="viewing-as" value={actorId} onChange={setActorId} />
      </div>
      {error && (
        <p role="alert" className="mt-4 text-red-700">
          {error.message}
          {data && " The numbers below are from the last successful read."}
        </p>
      )}
      {isLoading && !data && <p className="mt-4">Loading…</p>}
      {data && <DashboardView data={data} actorId={actorId} />}
      <SystemStatus />
    </main>
  );
}

export default function Home() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}
