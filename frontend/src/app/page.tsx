"use client";

import { useEffect, useState } from "react";

type Health = { status: string; database: string; detail?: string };

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => res.json())
      .then(setHealth)
      .catch(() => setError(`Cannot reach the API at ${API_URL}. Check that the backend is running.`));
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
