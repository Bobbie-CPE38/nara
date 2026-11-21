"use client";

import { SystemStatus } from "@/components/dashboard/SystemStatus";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useT } from "@/lib/i18n/LanguageProvider";

/** Whether the API and its database answer (round 6 PR EV8), for anyone: no login, no menu. */
export default function StatusPage() {
  const t = useT();
  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader title={t("sys.title")} description={t("sys.intro")} />
      <Card>
        <SystemStatus />
      </Card>
    </main>
  );
}
