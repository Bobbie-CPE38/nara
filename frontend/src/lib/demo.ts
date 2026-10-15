import { formatDateTime } from "@/lib/format";

/** Fixed walking-skeleton identities; display names come from API responses. */
export const DEMO_STAFF_IDS = [
  101, 102, 103, 104, 105, 201, 202, 203, 900, 301, 302, 401, 902, 950,
] as const;
export const DEMO_SHIFT_IDS = [1, 2, 21, 22] as const;
export const DEMO_APPROVER_ID = 900;

/** A shift of the seed and the people on its roster before any event. */
export type DemoShift = { id: number; label: string; staffIds: readonly number[] };
export type DemoWard = { id: number; name: string; shifts: readonly DemoShift[] };

/**
 * Wards of the seed (docs/workflow.md, section 10.2; round 4 PR W4). The Float Pool
 * has no shifts of its own, so it is not here: its nurse 401 works Medicine shifts.
 */
export const DEMO_WARDS: readonly DemoWard[] = [
  {
    id: 1,
    name: "ICU",
    shifts: [
      { id: 1, label: "Shift 1 (night)", staffIds: [101, 102, 103, 104, 105] },
      { id: 2, label: "Shift 2 (day)", staffIds: [202, 203] },
    ],
  },
  {
    id: 2,
    name: "Medicine",
    shifts: [
      { id: 21, label: "Shift 21 (night)", staffIds: [301, 302, 401, 902, 950] },
      { id: 22, label: "Shift 22 (day)", staffIds: [301, 302, 401, 902, 950] },
    ],
  },
];

/** Ward names the API does not send with an ID. A ward the seed lacks shows its ID. */
const DEMO_WARD_NAMES = new Map<number, string>([
  [1, "ICU"],
  [2, "Medicine"],
  [3, "Float Pool"],
]);

export function wardName(wardId: number): string {
  return DEMO_WARD_NAMES.get(wardId) ?? `Ward ${wardId}`;
}

/** Who the approvals page can act as (docs/workflow.md, section 6.21). Not a real login. */
export const DEMO_APPROVERS = [
  { id: 900, label: "900 — Head Nurse, ICU" },
  { id: 902, label: "902 — Head Nurse, Medicine" },
  { id: 950, label: "950 — Supervisor, every ward" },
] as const;
/** Where the nurse page keeps its demo sign-in (docs/workflow.md, section 6.17). Not a real login. */
export const DEMO_SIGNED_IN_STORAGE_KEY = "nara.demo.signedInStaffId";

export function formatDemoTime(value: string | null): string {
  if (value === null) return "—";
  return formatDateTime(value);
}
