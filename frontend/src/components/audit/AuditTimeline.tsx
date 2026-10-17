"use client";

import { ScrollX } from "@/components/ScrollX";
import { formatDateTime, formatValue } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { AuditEntry } from "@/lib/types/case";

/**
 * Audit rows in the order the API sends them, which is by id. Never sort by
 * created_at: the demo clock is frozen, so every row can carry the same time.
 * The action codes and the details are the audit trail as the Backend wrote it.
 */
export function AuditTimeline({ entries }: { entries: AuditEntry[] }) {
  const t = useT();
  if (entries.length === 0) return <p className="mt-2">{t("audit.none")}</p>;
  return (
    <ScrollX>
      <table aria-label={t("case.timeline")} className="mt-2">
        <thead>
          <tr>
            <th>#</th>
            <th>{t("audit.time")}</th>
            <th>{t("audit.action")}</th>
            <th>{t("audit.actor")}</th>
            <th>{t("audit.entity")}</th>
            <th>{t("audit.details")}</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(entry => {
            // One per transition, so they outnumber the real steps: keep them, but lighter.
            const isStatusChange = entry.action === "CASE_STATUS_CHANGED";
            return (
              <tr key={entry.id} className={isStatusChange ? "text-sm text-slate-500" : undefined}>
                <td>{entry.id}</td>
                <td className="whitespace-nowrap">{formatDateTime(entry.created_at)}</td>
                <td>{entry.action}</td>
                <td>
                  {entry.actor_type === "user" ? t("audit.staff", { name: entry.actor_name }) : entry.actor_name}
                </td>
                <td>
                  {entry.entity_type}{entry.entity_id === null ? "" : ` #${entry.entity_id}`}
                </td>
                <td className="break-all">
                  {isStatusChange ? (
                    `${formatValue(entry.payload.from)} → ${formatValue(entry.payload.to)}`
                  ) : (
                    <ul>
                      {Object.entries(entry.payload).map(([key, value]) => (
                        <li key={key}>{key}: {formatValue(value)}</li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollX>
  );
}
