"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { passwordProblem } from "@/lib/authForms";
import { describeError } from "@/lib/errors";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";

/**
 * Change the password (docs/workflow.md 6.33.2). A user whose account says must_change_password
 * lands here first. When it succeeds the Backend has ended every session of the account, so the
 * page says so and offers the login, instead of leaving the user on a page that no longer works.
 */
export default function ChangePasswordPage() {
  const t = useT();
  const router = useRouter();
  const { state, changePassword } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // Not logged in and not just changed: there is nothing to change here
    if (state.status === "anonymous" && !done) router.replace("/login");
  }, [state.status, done, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = passwordProblem(next, repeat) ?? (next === current ? "auth.change.same" : null);
    setProblem(found);
    setFailure(null);
    if (found !== null) return;
    setBusy(true);
    try {
      await changePassword(current, next);
      setDone(true);
    } catch (cause) {
      setFailure(cause);
    } finally {
      setBusy(false);
      setCurrent("");
      setNext("");
      setRepeat("");
    }
  }

  const mustChange = state.status === "authenticated" && state.me.must_change_password;
  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("auth.change.title")} description={t("auth.change.intro")} />
      {state.status === "demo" ? (
        <Notice kind="info" role="status">
          {t("auth.change.demoMode")}
        </Notice>
      ) : done ? (
        <Card className="max-w-md">
          <p role="status" className="font-medium text-green-700">
            {t("auth.change.done")}
          </p>
          <p className="mt-3">
            <Link className="underline" href="/login">
              {t("auth.register.back")}
            </Link>
          </p>
        </Card>
      ) : state.status === "authenticated" ? (
        <Card className="max-w-md">
          {mustChange && (
            <div className="mb-3">
              <Notice kind="warning" role="status">
                {t("auth.change.required")}
              </Notice>
            </div>
          )}
          <form onSubmit={(event) => void submit(event)} className="space-y-3" noValidate>
            <div>
              <label className="block" htmlFor="change-current">
                {t("auth.change.current")}
              </label>
              <input
                id="change-current"
                type="password"
                autoComplete="current-password"
                value={current}
                disabled={busy}
                onChange={(event) => setCurrent(event.target.value)}
              />
            </div>
            <div>
              <label className="block" htmlFor="change-new">
                {t("auth.change.new")}
              </label>
              <input
                id="change-new"
                type="password"
                autoComplete="new-password"
                value={next}
                disabled={busy}
                onChange={(event) => setNext(event.target.value)}
              />
              <p className="mt-1 text-sm text-slate-600">{t("auth.password.hint")}</p>
            </div>
            <div>
              <label className="block" htmlFor="change-repeat">
                {t("auth.password.confirm")}
              </label>
              <input
                id="change-repeat"
                type="password"
                autoComplete="new-password"
                value={repeat}
                disabled={busy}
                onChange={(event) => setRepeat(event.target.value)}
              />
            </div>
            {problem !== null && (
              <Notice kind="error" role="alert">
                {t(problem)}
              </Notice>
            )}
            {failure !== null && (
              <Notice kind="error" role="alert">
                {describeError(failure, t)}
              </Notice>
            )}
            <Button type="submit" variant="primary" disabled={busy || current === "" || next === ""}>
              {busy ? t("auth.change.busy") : t("auth.change.submit")}
            </Button>
          </form>
        </Card>
      ) : (
        <p role="status">{t("auth.checking")}</p>
      )}
    </main>
  );
}
