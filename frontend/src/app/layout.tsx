import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { LANG_COOKIE, parseLang, translate } from "@/lib/i18n";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import "./globals.css";

async function languageOfRequest() {
  // The choice of the user is in a cookie, so the first paint is already in their language
  return parseLang((await cookies()).get(LANG_COOKIE)?.value);
}

export async function generateMetadata(): Promise<Metadata> {
  const lang = await languageOfRequest();
  return { title: translate(lang, "app.name"), description: translate(lang, "app.description") };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const lang = await languageOfRequest();
  return (
    <html lang={lang}>
      <body>
        <LanguageProvider initial={lang}>
          <SiteHeader />
          {children}
        </LanguageProvider>
      </body>
    </html>
  );
}
