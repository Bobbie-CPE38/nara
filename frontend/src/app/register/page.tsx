"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { apiRequest } from "@/lib/api";
import { passwordProblem } from "@/lib/authForms";
import { describeError } from "@/lib/errors";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";

/**
 * First password of an account (docs/workflow.md 6.33.6): the code a person got in LINE by sending
 * REGISTER, and the password they choose. The page never asks for a role, a ward or a staff ID;
 * the Backend finds the person from the code.
 */
export default function RegisterPage() {
  const t = useT();
  const { state } = useAuth();
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [registered, setRegistered] = useState<number | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = passwordProblem(password, repeat);
    setProblem(found);
    setFailure(null);
    if (found !== null) return;
    setBusy(true);
    try {
      const result = await apiRequest<{ staff_id: number }>("/auth/register", {
        method: "POST",
        json: { code: code.trim(), password },
      });
      setRegistered(result.staff_id);
      setPassword("");
      setRepeat("");
    } catch (cause) {
      setFailure(cause);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("auth.register.title")} description={t("auth.register.intro")} />
      {state.status === "demo" ? (
        <Notice kind="info" role="status">
          {t("auth.login.demoMode")}
        </Notice>
      ) : registered !== null ? (
        <Card className="max-w-md">
          <p role="status" className="font-medium text-green-700">
            {t("auth.register.done", { id: registered })}
          </p>
          <p className="mt-3">
            <Link className="underline" href="/login">
              {t("auth.register.back")}
            </Link>
          </p>
        </Card>
      ) : (
        <Card className="max-w-md">
          <form onSubmit={(event) => void submit(event)} className="space-y-3" noValidate>
            <div>
              <label className="block" htmlFor="register-code">
                {t("auth.register.code")}
              </label>
              <input
                id="register-code"
                name="code"
                autoComplete="off"
                spellCheck={false}
                value={code}
                disabled={busy}
                onChange={(event) => setCode(event.target.value)}
              />
            </div>
            <div>
              <label className="block" htmlFor="register-password">
                {t("auth.password")}
              </label>
              <PasswordInput
                id="register-password"
                name="password"
                autoComplete="new-password"
                value={password}
                disabled={busy}
                onChange={(event) => setPassword(event.target.value)}
              />
              <p className="mt-1 text-sm text-slate-600">{t("auth.password.hint")}</p>
            </div>
            <div>
              <label className="block" htmlFor="register-repeat">
                {t("auth.password.confirm")}
              </label>
              <PasswordInput
                id="register-repeat"
                name="repeat"
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
            <Button type="submit" variant="primary" disabled={busy || code.trim() === "" || password === ""}>
              {busy ? t("auth.register.busy") : t("auth.register.submit")}
            </Button>
          </form>
          <p className="mt-4 text-sm">
            <Link className="underline" href="/login">
              {t("auth.register.back")}
            </Link>
          </p>
        </Card>
      )}
    </main>
  );
}
