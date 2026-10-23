/** What the Demo control picks from (round 6 PR EV6, docs/workflow.md 6.36.5). */
export type DemoWard = { id: number; name: string; is_active: boolean; is_float_pool: boolean };

export type DemoRosterPerson = {
  staff_id: number;
  first_name: string;
  last_name: string;
  status: string;
  checked_in: boolean;
};

/** One item of GET /demo/shifts?ward_id=&date= */
export type DemoShift = {
  id: number;
  ward_id: number;
  shift_type: string;
  start_at: string;
  end_at: string;
  people: DemoRosterPerson[];
};
