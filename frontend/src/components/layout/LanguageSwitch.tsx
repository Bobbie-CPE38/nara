"use client";

import { useLanguage } from "@/lib/i18n/LanguageProvider";
import { LANGS } from "@/lib/i18n";

/** TH | EN. The choice is kept in a cookie by the provider and applies to every page. */
export function LanguageSwitch() {
  const { lang, setLang, t } = useLanguage();
  return (
    <div
      role="group"
      aria-label={t("lang.label")}
      className="inline-flex overflow-hidden rounded-lg border border-slate-300 bg-white text-sm font-semibold"
    >
      {LANGS.map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          title={t(code === "th" ? "lang.th" : "lang.en")}
          aria-pressed={lang === code}
          onClick={() => setLang(code)}
          className={`rounded-none border-0 px-3 py-1 shadow-none ${
            lang === code ? "bg-brand-600 text-white hover:bg-brand-600" : "bg-white text-ink"
          }`}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
