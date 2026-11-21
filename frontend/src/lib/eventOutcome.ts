import { formatDateTime } from "@/lib/format";
import type { MessageKey, Params } from "@/lib/i18n";
import type { EventResult } from "@/lib/types/event";

const IGNORED: Record<string, MessageKey> = {
  NO_ASSIGNED_ROSTER: "event.ignored.NO_ASSIGNED_ROSTER",
  THRESHOLD_NOT_PASSED: "event.ignored.ENOUGH_STAFF",
  NO_GAP: "event.ignored.ENOUGH_STAFF",
  SHIFT_ENDED: "event.ignored.SHIFT_ENDED",
  REQUIREMENT_ITEM_NOT_FOUND: "event.ignored.REQUIREMENT_ITEM_NOT_FOUND",
};

/**
 * What a reported event did, in words (round 6 PR EV10, docs/workflow.md 6.40): opened a
 * case, joined the case already running on the shift, waits for its merge window (and
 * until when), or changed nothing and why. Never only "no case yet".
 */
export function eventOutcome(result: EventResult): { key: MessageKey; params?: Params } {
  if (result.case_id !== null) {
    return {
      key: result.joined_running_case ? "event.joined" : "event.opened",
      params: { case: result.case_id, status: result.case_status ?? "" },
    };
  }
  if (result.event_status === "RECEIVED") {
    return result.window_closes_at
      ? { key: "event.received", params: { at: formatDateTime(result.window_closes_at) } }
      : { key: "event.receivedSoon" };
  }
  return { key: (result.ignored_reason && IGNORED[result.ignored_reason]) || "event.ignored" };
}
