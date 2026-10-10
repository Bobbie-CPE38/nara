/** Responses from the demo LINE simulator API. */
export type Offer = {
  id: number;
  case_id: number;
  candidate_item_id: number;
  staff_id: number;
  proposed_shift_id: number;
  status: string;
  case_status: string;
  channel: string;
  sent_at: string | null;
  response_at: string | null;
};

export type OfferResponse = {
  outreach_id: number;
  outreach_status: string;
  case_id: number;
  case_status: string;
};
