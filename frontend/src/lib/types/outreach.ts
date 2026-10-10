/** Responses from the demo LINE simulator API. */
export type OutreachStatus =
  | "PENDING"
  | "SENT"
  | "ACCEPTED"
  | "REJECTED"
  | "TIMEOUT"
  | "FAILED"
  | "CANCELLED";
export type CaseStatus =
  | "OPEN"
  | "ASSESSING"
  | "OPTIMIZING"
  | "OUTREACH"
  | "WAITING_RESPONSE"
  | "SAFETY_VALIDATION"
  | "WAITING_APPROVAL"
  | "EXECUTING"
  | "RESOLVED"
  | "MANUAL_HANDOFF"
  | "UNRESOLVED"
  | "FAILED";

export type Offer = {
  id: number;
  case_id: number;
  candidate_item_id: number;
  staff_id: number;
  proposed_shift_id: number;
  status: OutreachStatus;
  case_status: CaseStatus;
  channel: "LINE";
  sent_at: string | null;
  response_at: string | null;
};

export type OfferResponse = {
  outreach_id: number;
  outreach_status: OutreachStatus;
  case_id: number;
  case_status: CaseStatus;
};
