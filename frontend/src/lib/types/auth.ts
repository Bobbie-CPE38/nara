/** Answers of the login API (docs/workflow.md 6.33.3). */
export type AuthMode = "demo" | "session";
export type AuthConfig = { auth_mode: AuthMode };

/** The roles of the Backend (mapped from the roster roles there, never read from the page). */
export type AuthRole = "staff" | "head_nurse" | "supervisor";

/** Answer of GET /auth/me and POST /auth/login: no hash, token or session ID. */
export type AuthMe = {
  staff_id: number;
  role: AuthRole;
  home_ward_id: number;
  home_ward_name?: string | null;
  must_change_password: boolean;
};

/** Answer of GET /roster?staff_id=: one person and the shifts of their roster rows. */
export type StaffRoster = {
  staff: {
    id: number;
    first_name: string;
    last_name: string;
    staff_status: string;
    role_id: number;
    role_name: string;
    home_ward_id: number;
    home_ward_name: string;
  };
  assignments: {
    id: number;
    status: string;
    assignment_type: string;
    is_unavailable: boolean;
    shift: {
      id: number;
      ward_id: number;
      ward_name: string;
      shift_type: string;
      start_at: string;
      end_at: string;
      is_active: boolean;
    };
  }[];
};
