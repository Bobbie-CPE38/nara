"use client";

import { type InputHTMLAttributes, useState } from "react";
import { useT } from "@/lib/i18n/LanguageProvider";

/**
 * A password field with a button that shows what was typed (round 6 PR EV7): a typo in a long
 * password is otherwise only found when the login fails. The field goes back to hidden when
 * the form is left. The Basic Auth box of the AWS machine belongs to the browser, so it
 * cannot have this button.
 */
export function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const t = useT();
  const [shown, setShown] = useState(false);
  return (
    <span className="inline-flex max-w-full items-stretch gap-1">
      <input {...props} type={shown ? "text" : "password"} />
      <button
        type="button"
        className="rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-700 hover:bg-slate-50"
        aria-pressed={shown}
        aria-controls={props.id}
        aria-label={t(shown ? "auth.password.hide" : "auth.password.show")}
        disabled={props.disabled}
        onClick={() => setShown((value) => !value)}
      >
        {t(shown ? "auth.password.hideShort" : "auth.password.showShort")}
      </button>
    </span>
  );
}
