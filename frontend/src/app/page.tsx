"use client";

import { useEffect, useState } from "react";
import { ApiError, apiRequest } from "@/lib/api";

type Health = { status: string; database: string; detail?: string };

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiRequest<Health>("/health", { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setHealth(result);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        // /health returns its system-check details with HTTP 503 when the DB is down.
        if (
          cause instanceof ApiError &&
          cause.status === 503 &&
          typeof cause.body === "object" &&
          cause.body !== null &&
          "status" in cause.body && typeof cause.body.status === "string" &&
          "database" in cause.body && typeof cause.body.database === "string"
        ) {
          setHealth({ status: cause.body.status, database: cause.body.database });
        } else {
          setError(cause instanceof ApiError
            ? cause.message
            : "Cannot reach the API. Check that the backend is running.");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-2xl font-semibold">System check</h1>
      {error && <p className="mt-4 text-red-700">{error}</p>}
      {!error && !health && <p className="mt-4">Checking…</p>}
      {health && (
        <dl className="mt-4 grid grid-cols-2 gap-2">
          <dt>API</dt>
          <dd className={health.status === "ok" ? "text-green-700" : "text-red-700"}>{health.status}</dd>
          <dt>Database</dt>
          <dd className={health.database === "ok" ? "text-green-700" : "text-red-700"}>{health.database}</dd>
        </dl>
      )}
    </main>
  );
}
