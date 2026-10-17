import { en, type MessageKey } from "./en";
import { th } from "./th";

export type { MessageKey } from "./en";

/** The two languages of the web app (docs/workflow.md 6.32). Thai is the default. */
export const LANGS = ["th", "en"] as const;
export type Lang = (typeof LANGS)[number];
export const DEFAULT_LANG: Lang = "th";

/** The cookie that keeps the choice of a user in their browser, for a year. */
export const LANG_COOKIE = "nara-lang";
export const LANG_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

const MESSAGES: Record<Lang, Record<MessageKey, string>> = { th, en };

export type Params = Record<string, string | number>;

/** A language from a cookie value, or the default when it is missing or unknown. */
export function parseLang(value: string | null | undefined): Lang {
  return (LANGS as readonly string[]).includes(value ?? "") ? (value as Lang) : DEFAULT_LANG;
}

/** The text of `key` in `lang`, with every `{name}` replaced by the value of `params`. */
export function translate(lang: Lang, key: MessageKey, params?: Params): string {
  const text = MESSAGES[lang][key];
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    name in params ? String(params[name]) : placeholder,
  );
}

export type Translate = (key: MessageKey, params?: Params) => string;

export function translator(lang: Lang): Translate {
  return (key, params) => translate(lang, key, params);
}
