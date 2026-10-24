import type { AuthRole } from "@/lib/types/auth";

const MANAGERS: readonly AuthRole[] = ["head_nurse", "supervisor"];

/**
 * Pages only some roles may open (round 6 PR EV7, docs/workflow.md 6.37.4): the same rights
 * as the menu, so typing the address of a page that is not in someone's menu sends them back
 * to the Dashboard. The longest matching prefix wins; any other page is for every signed-in
 * user. The Backend still checks every request: this only keeps a page of errors away.
 */
const ROUTE_ROLES: readonly (readonly [string, readonly AuthRole[]])[] = [
  ["/admin", ["supervisor"]],
  ["/approvals", MANAGERS],
  ["/handoff", MANAGERS],
  ["/demo/control", MANAGERS],
  ["/demo/test-runs", MANAGERS],
];

function matches(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`);
}

/** May a signed-in user with this role open this page? */
export function roleMayOpen(path: string, role: AuthRole): boolean {
  const rule = ROUTE_ROLES.filter(([prefix]) => matches(path, prefix)).sort(
    (left, right) => right[0].length - left[0].length,
  )[0];
  return rule === undefined || rule[1].includes(role);
}
