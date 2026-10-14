import { formatDateTime } from "@/lib/format";

/** Fixed walking-skeleton identities; display names come from API responses. */
export const DEMO_STAFF_IDS = [
  101, 102, 103, 104, 105, 201, 202, 203, 900,
] as const;
export const DEMO_SHIFT_IDS = [1, 2] as const;
export const DEMO_APPROVER_ID = 900;
/** Where the nurse page keeps its demo sign-in (docs/workflow.md, section 6.17). Not a real login. */
export const DEMO_SIGNED_IN_STORAGE_KEY = "nara.demo.signedInStaffId";

export function formatDemoTime(value: string | null): string {
  if (value === null) return "—";
  return formatDateTime(value);
}
