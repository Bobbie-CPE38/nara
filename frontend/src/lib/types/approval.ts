export type ApprovalSide = "DESTINATION" | "SOURCE";
export type ApprovalOutcome =
  | "WAITING_OTHER_WARD"
  | "ASSIGNED"
  | "REJECTED"
  | "TRANSFER_CANCELLED"
  | "EXECUTION_FAILED";

/** One item of GET /approvals?pending=true (docs/workflow.md, section 9.3, seam 6). */
export type PendingApproval = {
  id: number;
  case_id: number;
  candidate_item_id: number;
  required_approver_role: number | null;
  approval_mode: string;
  is_pending: boolean;
  staff_id: number;
  proposed_shift_id: number;
  requested_at: string;
  /** When the request times out: deciding at or after it answers 409 (workflow.md 6.13) */
  expires_at: string;
  home_ward_id: number;
  source_ward_id: number | null;
  wards: {
    ward_id: number;
    side: ApprovalSide;
    status: "PENDING" | "APPROVED";
    /** Who approved an APPROVED side: a person or the system (round 6 PR EV9, 6.39) */
    approval_mode?: "MANUAL" | "AUTO" | null;
  }[];
  supervisor_from: string;
};

/**
 * One item of GET /approvals/auto: a request the system approved on at least one side
 * (workflow.md 6.22, 6.39). `is_pending` true: another ward still decides.
 */
export type AutoApprovedApproval = PendingApproval & { decided_at: string };

/** Answer of POST /approvals/{id}/decision. */
export type ApprovalDecisionResult = {
  approval_id: number;
  is_approved: boolean | null;
  case_id: number;
  case_status: string;
  outcome: ApprovalOutcome;
  reason: string | null;
  failed_rules: string[];
};
