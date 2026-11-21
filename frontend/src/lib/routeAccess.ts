import type { AuthRole } from "@/lib/types/auth";

const MANAGERS: readonly AuthRole[] = ["head_nurse", "supervisor"];

/**
 * Pages only some roles may open (round 6 PR EV7, docs/workflow.md 6.37.4): the same rights
 * as the menu, so typing the address of a page that is not in someone's menu sends them back
 * to their home page. The longest matching prefix wins; any other page is for every signed-in
 * user. The Backend still checks every request: this only keeps a page of errors away.
 *
 * Round 6 PR EV8 (6.38.2): a nurse has the cases, the roster, their offers and their leave
 * only. The Dashboard ("/", matched exactly), the gap check and every Demo page are for head
 * nurses and supervisors.
 */
const ROUTE_ROLES: readonly (readonly [string, readonly AuthRole[]])[] = [
  ["/admin", ["supervisor"]],
  ["/approvals", MANAGERS],
  ["/handoff", MANAGERS],
  ["/gap", MANAGERS],
  ["/demo", MANAGERS],
];

/** Pages matched by their exact path only: "/" as a prefix would match every page */
const EXACT_ROLES: ReadonlyMap<string, readonly AuthRole[]> = new Map([["/", MANAGERS]]);

/** Where a nurse starts: their offers and check-in (round 6 PR EV8) */
export const STAFF_HOME = "/me/offers";

function matches(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`);
}

/** May a signed-in user with this role open this page? */
export function roleMayOpen(path: string, role: AuthRole): boolean {
  const exact = EXACT_ROLES.get(path);
  if (exact !== undefined) return exact.includes(role);
  const rule = ROUTE_ROLES.filter(([prefix]) => matches(path, prefix)).sort(
    (left, right) => right[0].length - left[0].length,
  )[0];
  return rule === undefined || rule[1].includes(role);
}

/** The page a role starts from, and goes back to from a page it may not open. */
export function homeOf(role: AuthRole): string {
  return role === "staff" ? STAFF_HOME : "/";
}
