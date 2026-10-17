import { describe, expect, it } from "vitest";
import { DEFAULT_LANG, LANG_COOKIE, LANGS, parseLang, translate } from "../../../src/lib/i18n";
import { en } from "../../../src/lib/i18n/en";
import { th } from "../../../src/lib/i18n/th";

const KEYS = Object.keys(en) as (keyof typeof en)[];
const THAI_LETTERS = /[฀-๿]/;

/** The names between braces: {count}, {time}. Both languages must take the same values. */
function placeholders(text: string): string[] {
  return [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
}

describe("the two dictionaries", () => {
  it("have the same keys, so no screen is left without a text in one language", () => {
    expect(Object.keys(th).sort()).toEqual([...KEYS].sort());
  });

  it("take the same values: a {name} in one language is in the other", () => {
    for (const key of KEYS) expect(placeholders(th[key]), key).toEqual(placeholders(en[key]));
  });

  it("have a Thai text that is Thai, except for the words the Thai documents keep in English", () => {
    const ENGLISH_BY_DESIGN = new Set<string>([
      "app.name", "nav.handoff", "lang.en", "common.gap", "sys.api", "case.handovers",
      "case.events", "handoverReason.NO_SHOW",
    ]);
    const NOT_THAI = KEYS.filter(
      (key) => !ENGLISH_BY_DESIGN.has(key) && th[key] !== "" && !THAI_LETTERS.test(th[key]),
    );
    expect(NOT_THAI).toEqual([]);
  });

  it("have no English sentence in the Thai file by mistake", () => {
    // A Thai text of more than three English words in a row is an untranslated one
    const UNTRANSLATED = KEYS.filter((key) => /[A-Za-z]{3,}(\s+[A-Za-z]{2,}){3,}/.test(th[key]));
    expect(UNTRANSLATED).toEqual([]);
  });
});

describe("translate", () => {
  it("returns the text of the language", () => {
    expect(translate("en", "nav.dashboard")).toBe("Dashboard");
    expect(translate("th", "nav.dashboard")).toBe("แดชบอร์ด");
  });

  it("puts the values in, and leaves a name that has no value as it is", () => {
    expect(translate("en", "dash.caseLink", { id: 7 })).toBe("Case 7");
    expect(translate("th", "dash.caseLink", { id: 7 })).toBe("เคส 7");
    expect(translate("en", "dash.caseLink")).toBe("Case {id}");
  });
});

describe("the language of a request", () => {
  it("is Thai unless the cookie holds a language the app has", () => {
    expect(DEFAULT_LANG).toBe("th");
    expect(LANGS).toEqual(["th", "en"]);
    expect(LANG_COOKIE).toBe("nara-lang");
    expect(parseLang(undefined)).toBe("th");
    expect(parseLang("")).toBe("th");
    expect(parseLang("fr")).toBe("th");
    expect(parseLang("<script>")).toBe("th");
    expect(parseLang("en")).toBe("en");
    expect(parseLang("th")).toBe("th");
  });
});
