/** Answer of POST /events and GET /events/{event_id} (docs/workflow.md, section 9.3). */
export type EventResult = {
  event_id: number;
  event_status: string;
  // Both null when the event has no case. IGNORED: there will be none.
  // RECEIVED: the event waits for the merge window of its shift to close
  case_id: number | null;
  case_status: string | null;
  /** PROCESSED: the event joined the case already running on the shift (round 6 PR EV10) */
  joined_running_case?: boolean;
  /** IGNORED: why, e.g. NO_ASSIGNED_ROSTER when the person was already off the shift */
  ignored_reason?: string | null;
  /** RECEIVED: the earliest time its merge window closes */
  window_closes_at?: string | null;
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
  timed_out_approval_request_ids: number[];
  auto_approved_request_ids: number[];
  failed_auto_approval_ward_ids: number[];
  /** Waiting cases the recovery sweep moved on */
  recovered_case_ids: number[];
  /** STAFF_UNAVAILABLE events the NO_SHOW job wrote at the new time (section 6.24) */
  no_show_event_ids: number[];
};
