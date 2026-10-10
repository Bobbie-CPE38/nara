/** Answer of POST /events (docs/workflow.md, section 9.3). */
export type EventResult = {
  event_id: number;
  event_status: string;
  // Both null when the event was IGNORED: no gap, so no case
  case_id: number | null;
  case_status: string | null;
};
