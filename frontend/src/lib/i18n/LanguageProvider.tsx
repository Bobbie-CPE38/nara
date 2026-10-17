"use client";

import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import {
  LANG_COOKIE,
  LANG_COOKIE_MAX_AGE_SECONDS,
  type Lang,
  translator,
  type Translate,
} from "./index";

type LanguageValue = { lang: Lang; setLang: (lang: Lang) => void; t: Translate };

/**
 * Without a provider (a page rendered by a test) the language is English, the texts the
 * tests were written against. The app always has one: the root layout reads the cookie.
 */
const LanguageContext = createContext<LanguageValue>({
  lang: "en",
  setLang: () => {},
  t: translator("en"),
});

/** Holds the language of the page. `initial` is what the server read from the cookie. */
export function LanguageProvider({ initial, children }: { initial: Lang; children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initial);
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      document.cookie = `${LANG_COOKIE}=${next}; path=/; max-age=${LANG_COOKIE_MAX_AGE_SECONDS}; samesite=lax`;
      document.documentElement.lang = next;
    } catch {
      // The choice then lasts until the page is left, which is all a blocked cookie allows
    }
  }, []);
  const value = useMemo(() => ({ lang, setLang, t: translator(lang) }), [lang, setLang]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageValue {
  return useContext(LanguageContext);
}

/** The translate function of the current language. */
export function useT(): Translate {
  return useContext(LanguageContext).t;
}
