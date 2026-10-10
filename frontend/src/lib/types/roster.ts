/** Response from GET /roster?shift_id=. */
export type ShiftRoster = {
  shift: {
    id: number; ward_id: number; ward_name: string; shift_type: string;
    start_at: string; end_at: string; is_active: boolean;
  };
  assignments: {
    id: number; status: string; assignment_type: string; candidate_source: string | null;
    staff_id: number; first_name: string; last_name: string; staff_status: string;
    role_id: number; role_name: string; home_ward_id: number; home_ward_name: string;
    created_at: string; updated_at: string;
  }[];
};
