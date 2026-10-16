/** Answer of POST /me/attendance/check-in and POST /demo/attendance/check-in (section 9.7). */
export type CheckInResult = {
  attendance_id: number;
  shift_id: number;
  check_in_at: string;
  on_time: boolean;
  /** Arrival time of the row plus the 15-minute grace (section 6.24) */
  deadline: string;
};

/** GET /clock: the time the backend runs on. */
export type ClockView = {
  now: string;
  /** true while the demo clock is frozen; false when it follows real time */
  frozen: boolean;
};
