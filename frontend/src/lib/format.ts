const bangkok = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Bangkok",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** An API time as Bangkok wall-clock time ("2026-10-09 21:00:00"), whatever zone the browser is in. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const part = Object.fromEntries(bangkok.formatToParts(date).map(({ type, value }) => [type, value]));
  return `${part.year}-${part.month}-${part.day} ${part.hour}:${part.minute}:${part.second}`;
}

/** One audit payload value as text. Lists and objects are shown as JSON. */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
