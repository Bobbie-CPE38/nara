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
};

/** Answer of POST /approvals/{id}/decision. */
export type ApprovalDecisionResult = {
  approval_id: number;
  is_approved: boolean;
  case_id: number;
  case_status: string;
};
