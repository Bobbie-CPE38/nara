"use client";

import { Button } from "@/components/ui/Button";
import { useT } from "@/lib/i18n/LanguageProvider";

/** Previous and next page of a list, with where the user is (round 6 PR EV6). */
export function Pager({
  page,
  pageSize,
  total,
  disabled = false,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  disabled?: boolean;
  onPage: (page: number) => void;
}) {
  const t = useT();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav aria-label={t("pager.label")} className="mt-3 flex flex-wrap items-center gap-3 text-sm">
      <Button disabled={disabled || page <= 1} onClick={() => onPage(page - 1)}>
        {t("pager.previous")}
      </Button>
      <span>{t("pager.where", { page, pages, total })}</span>
      <Button disabled={disabled || page >= pages} onClick={() => onPage(page + 1)}>
        {t("pager.next")}
      </Button>
    </nav>
  );
}
