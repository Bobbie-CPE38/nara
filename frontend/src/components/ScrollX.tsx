/**
 * A table that is wider than the screen scrolls inside this box instead of making the whole
 * page scroll sideways (round 6 PR F3, docs/workflow.md 6.30 part A item 3). The page and its
 * heading stay in view; on a wide screen the box changes nothing.
 */
export function ScrollX({ children }: { children: React.ReactNode }) {
  // relative: a visually hidden header (sr-only is absolute) stays inside the box instead of
  // widening the page (round 6 PR EV7)
  return <div className="relative overflow-x-auto">{children}</div>;
}
