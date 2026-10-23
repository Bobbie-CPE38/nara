"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/i18n/LanguageProvider";

export type CaseQuery = { q: string; status: string; page: number };

/**
 * Search and status filter of a case list (round 6 PR EV6, docs/workflow.md 6.36.6). The search
 * is a case or shift ID, or part of a ward name; it applies on submit, the status at once.
 */
export function CaseFilters({
  query,
  statuses,
  disabled = false,
  onChange,
}: {
  query: CaseQuery;
  /** The choices of the status filter: the `status` parameter and its label */
  statuses: readonly { value: string; label: MessageKey }[];
  disabled?: boolean;
  onChange: (query: CaseQuery) => void;
}) {
  const t = useT();
  const [text, setText] = useState(query.q);

  function search(event: FormEvent) {
    event.preventDefault();
    onChange({ ...query, q: text.trim(), page: 1 });
  }

  return (
    <form role="search" className="flex flex-wrap items-end gap-3" onSubmit={search}>
      <label className="block text-sm font-medium" htmlFor="case-search">
        {t("cases.search")}{" "}
        <input
          id="case-search"
          type="search"
          maxLength={100}
          placeholder={t("cases.searchHint")}
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <Button type="submit" disabled={disabled}>
        {t("cases.find")}
      </Button>
      <label className="block text-sm font-medium" htmlFor="case-status">
        {t("cand.status")}{" "}
        <select
          id="case-status"
          value={query.status}
          disabled={disabled}
          onChange={(event) => onChange({ ...query, status: event.target.value, page: 1 })}
        >
          {statuses.map((item) => (
            <option key={item.value} value={item.value}>
              {t(item.label)}
            </option>
          ))}
        </select>
      </label>
    </form>
  );
}

/** The query string of GET /cases/search for a query */
export function searchPath(query: CaseQuery, pageSize: number, sort: "newest" | "oldest"): string {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(pageSize), sort });
  if (query.q) params.set("q", query.q);
  if (query.status) params.set("status", query.status);
  return `/cases/search?${params.toString()}`;
}
