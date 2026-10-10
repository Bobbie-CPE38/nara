/** Walking-skeleton demo identities; names match the Golden Case seed. */
export const DEMO_STAFF = [
  [101, "Pimchanok"], [102, "Thanaphon"], [103, "Wanna"],
  [104, "Kitti"], [105, "Sudarat"], [201, "Arunee"],
  [202, "Phanu"], [203, "Chonthicha"], [900, "Malai"],
] as const;

export function formatDemoTime(value: string | null): string {
  if (value === null) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Bangkok", dateStyle: "medium", timeStyle: "short",
  }).format(new Date(value));
}
