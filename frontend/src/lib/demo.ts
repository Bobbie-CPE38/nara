import { formatDateTime } from "@/lib/format";

/** Fixed walking-skeleton identities; display names come from API responses. */
export const DEMO_STAFF_IDS = [
  101, 102, 103, 104, 105, 201, 202, 203, 900, 301, 302, 401, 902, 950,
] as const;
export const DEMO_SHIFT_IDS = [1, 2, 21, 22] as const;
export const DEMO_APPROVER_ID = 900;

/** A shift of the seed and the people on its roster before any event. */
export type DemoShift = { id: number; kind: "night" | "day"; staffIds: readonly number[] };
export type DemoWard = { id: number; name: string; shifts: readonly DemoShift[] };

/**
 * Wards of the seed (docs/workflow.md, section 10.2; round 4 PR W4). The Float Pool
 * has no shifts of its own, so it is not here: its nurse 401 works Medicine shifts.
 * Copied from backend/app/seed/scenarios/golden_case.py and multi_ward.py: change
 * both together, because nothing checks that they still match.
 */
export const DEMO_WARDS: readonly DemoWard[] = [
  {
    id: 1,
    name: "ICU",
    shifts: [
      { id: 1, kind: "night", staffIds: [101, 102, 103, 104, 105] },
      { id: 2, kind: "day", staffIds: [202, 203] },
    ],
  },
  {
    id: 2,
    name: "Medicine",
    shifts: [
      { id: 21, kind: "night", staffIds: [301, 302, 401, 902, 950] },
      { id: 22, kind: "day", staffIds: [301, 302, 401, 902, 950] },
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
export const DEMO_APPROVERS: readonly {
  id: number;
  role: "headNurse" | "supervisor";
  /** The ward a head nurse decides for; null for the Supervisor, who may decide any */
  wardId: number | null;
}[] = [
  { id: 900, role: "headNurse", wardId: 1 },
  { id: 902, role: "headNurse", wardId: 2 },
  { id: 950, role: "supervisor", wardId: null },
];
/**
 * The demo user travels from one page to the next in this query parameter, so a link of the
 * Dashboard opens the destination for the same user (round 6 PR F2 review). Not a real login.
 */
export const ACTOR_QUERY = "as";

/** The user a page opens for: the one in the query, or the Golden Case head nurse. */
export function actorFromQuery(value: string | null | undefined): number {
  const id = Number(value);
  return DEMO_APPROVERS.some((approver) => approver.id === id) ? id : DEMO_APPROVER_ID;
}

/** A link to `path` that opens for `actorId`. */
export function withActor(path: string, actorId: number): string {
  return `${path}?${ACTOR_QUERY}=${actorId}`;
}

/** Where the nurse page keeps its demo sign-in (docs/workflow.md, section 6.17). Not a real login. */
export const DEMO_SIGNED_IN_STORAGE_KEY = "nara.demo.signedInStaffId";

export function formatDemoTime(value: string | null): string {
  if (value === null) return "—";
  return formatDateTime(value);
}
