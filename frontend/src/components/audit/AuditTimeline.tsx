import { formatDateTime, formatValue } from "@/lib/format";
import type { AuditEntry } from "@/lib/types/case";

/**
 * Audit rows in the order the API sends them, which is by id. Never sort by
 * created_at: the demo clock is frozen, so every row can carry the same time.
 */
export function AuditTimeline({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <p className="mt-2">No audit entries yet.</p>;
  return (
    <table aria-label="Timeline" className="mt-2 w-full text-left">
      <thead>
        <tr>
          <th className="py-1 pr-4">#</th>
          <th className="py-1 pr-4">Time</th>
          <th className="py-1 pr-4">Action</th>
          <th className="py-1 pr-4">Actor</th>
          <th className="py-1 pr-4">Entity</th>
          <th className="py-1 pr-4">Details</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(entry => {
          // One per transition, so they outnumber the real steps: keep them, but lighter.
          const isStatusChange = entry.action === "CASE_STATUS_CHANGED";
          return (
            <tr key={entry.id} className={isStatusChange ? "text-sm text-gray-500" : undefined}>
              <td className="py-1 pr-4 align-top">{entry.id}</td>
              <td className="py-1 pr-4 align-top whitespace-nowrap">{formatDateTime(entry.created_at)}</td>
              <td className="py-1 pr-4 align-top">{entry.action}</td>
              <td className="py-1 pr-4 align-top">
                {entry.actor_type === "user" ? `Staff ${entry.actor_name}` : entry.actor_name}
              </td>
              <td className="py-1 pr-4 align-top">
                {entry.entity_type}{entry.entity_id === null ? "" : ` #${entry.entity_id}`}
              </td>
              <td className="py-1 pr-4 align-top break-all">
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
  );
}
