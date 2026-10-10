/** Response from GET /roster?shift_id=. */
export type ShiftType = "DAY" | "EVENING" | "NIGHT";
export type RosterStatus =
  | "PENDING_APPROVAL"
  | "ASSIGNED"
  | "CANCELLED"
  | "COMPLETED";
export type AssignmentType = "REGULAR" | "REPLACEMENT";
export type CandidateSource = "SAME_WARD" | "FLOAT_POOL" | "CROSS_WARD";
export type StaffStatus = "ACTIVE" | "INACTIVE";

export type ShiftRoster = {
  shift: {
    id: number;
    ward_id: number;
    ward_name: string;
    shift_type: ShiftType;
    start_at: string;
    end_at: string;
    is_active: boolean;
  };
  assignments: {
    id: number;
    status: RosterStatus;
    assignment_type: AssignmentType;
    candidate_source: CandidateSource | null;
    staff_id: number;
    first_name: string;
    last_name: string;
    staff_status: StaffStatus;
    role_id: number;
    role_name: string;
    home_ward_id: number;
    home_ward_name: string;
    created_at: string;
    updated_at: string;
  }[];
};
