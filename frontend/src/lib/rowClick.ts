import type { MouseEvent } from "react";

/** The classes of a table row that opens a page when clicked (round 6 PR EV7). */
export const CLICKABLE_ROW = "cursor-pointer hover:bg-brand-50";

/** Mark the row's own detail link, the one a click on the row follows. */
export const ROW_LINK = { "data-row-link": "" } as const;

/**
 * Follow the row's detail link when the row is clicked, except on its own links and
 * buttons, which keep their own action (round 6 PR EV7, docs/workflow.md 6.37.7). Clicking
 * the link itself keeps the client-side navigation of the page; a keyboard user tabs to the
 * link, since a row is no control of its own.
 */
export function followRowLink(event: MouseEvent<HTMLElement>): void {
  const target = event.target as HTMLElement;
  if (target.closest("a, button, input, select, textarea, label")) return;
  event.currentTarget.querySelector<HTMLAnchorElement>("a[data-row-link]")?.click();
}
