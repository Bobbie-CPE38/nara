"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useEffect, useState } from "react";
import { safeNext, useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { parseStaffId } from "@/lib/authForms";
import { describeError } from "@/lib/errors";
import { useT } from "@/lib/i18n/LanguageProvider";

function LoginForm() {
  const t = useT();
  const router = useRouter();
  const next = safeNext(useSearchParams()?.get("next"));
  const { state, login } = useAuth();
  const [staffId, setStaffId] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [badId, setBadId] = useState(false);
  // The error itself, not its text: the text follows the language when it is switched
  const [failure, setFailure] = useState<unknown>(null);

  const me = state.status === "authenticated" ? state.me : null;
  useEffect(() => {
    // Already logged in (or just now): go on. A user who must change the password goes there first
    if (me) router.replace(me.must_change_password ? "/change-password" : next);
  }, [me, next, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const id = parseStaffId(staffId);
    setBadId(id === null);
    setFailure(null);
    if (id === null) return;
    setBusy(true);
    try {
      await login(id, password);
      setPassword("");
    } catch (cause) {
      setFailure(cause);
    } finally {
      setBusy(false);
    }
  }

  if (state.status === "demo") {
    return (
      <Notice kind="info" role="status">
        {t("auth.login.demoMode")}{" "}
        <Link className="underline" href="/">
          {t("nav.dashboard")}
        </Link>
      </Notice>
    );
  }

  return (
    <Card className="max-w-md">
      <form onSubmit={(event) => void submit(event)} className="space-y-3" noValidate>
        <div>
          <label className="block" htmlFor="login-staff-id">
            {t("auth.staffId")}
          </label>
          <input
            id="login-staff-id"
            name="staff_id"
            inputMode="numeric"
            autoComplete="username"
            value={staffId}
            disabled={busy}
            onChange={(event) => setStaffId(event.target.value)}
            aria-invalid={badId}
          />
          {badId && (
            <p role="alert" className="mt-1 text-sm text-red-700">
              {t("auth.login.badId")}
            </p>
          )}
        </div>
        <div>
          <label className="block" htmlFor="login-password">
            {t("auth.password")}
          </label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            disabled={busy}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {failure !== null && (
          <Notice kind="error" role="alert">
            {describeError(failure, t)}
          </Notice>
        )}
        <Button type="submit" variant="primary" disabled={busy || staffId.trim() === "" || password === ""}>
          {busy ? t("auth.login.busy") : t("auth.login.submit")}
        </Button>
      </form>
      <p className="mt-4 text-sm">
        {t("auth.login.firstTime")}{" "}
        <Link className="underline" href="/register">
          {t("auth.register.link")}
        </Link>
      </p>
    </Card>
  );
}

export default function LoginPage() {
  const t = useT();
  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("auth.login.title")} description={t("auth.login.intro")} />
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
