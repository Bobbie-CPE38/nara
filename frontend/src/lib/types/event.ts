/** Answer of POST /events and GET /events/{event_id} (docs/workflow.md, section 9.3). */
export type EventResult = {
  event_id: number;
  event_status: string;
  // Both null when the event has no case. IGNORED: there will be none.
  // RECEIVED: the event waits for the merge window of its shift to close
  case_id: number | null;
  case_status: string | null;
};

/** One merge window that was closed. No case when its events were IGNORED. */
export type ClosedWindow = {
  shift_id: number;
  event_ids: number[];
  case_id: number | null;
  case_status: string | null;
};

/** Answer of POST /demo/clock/advance: the new demo time and what it made due. */
export type ClockAdvanceResult = {
  clock: string;
  closed_windows: ClosedWindow[];
  /** Offers the new time set to TIMEOUT */
  timed_out_outreach_ids: number[];
  /** Waiting cases the recovery sweep moved on */
  recovered_case_ids: number[];
};
