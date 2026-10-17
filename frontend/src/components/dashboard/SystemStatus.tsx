"use client";

import { useEffect, useState } from "react";
import { ApiError, apiRequest } from "@/lib/api";

type Health = { status: string; database: string; detail?: string };

/** The small API and database check the home page showed before the Dashboard (GET /health). */
export function SystemStatus() {
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
    <section aria-label="System check" className="mt-8 border-t border-slate-300 pt-3 text-sm">
      <h2 className="font-semibold">System check</h2>
      {error && <p className="mt-1 text-red-700">{error}</p>}
      {!error && !health && <p className="mt-1">Checking…</p>}
      {health && (
        <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
          <dt>API</dt>
          <dd className={health.status === "ok" ? "text-green-700" : "text-red-700"}>{health.status}</dd>
          <dt>Database</dt>
          <dd className={health.database === "ok" ? "text-green-700" : "text-red-700"}>{health.database}</dd>
        </dl>
      )}
    </section>
  );
}
