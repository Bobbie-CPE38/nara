import type { AuditEntry, CaseDetail } from "../../src/lib/types/case";

// The demo clock is frozen after a reset, so every row of a case carries this time.
export const DEMO_TIME = "2026-10-09T21:00:00+07:00";

/** The golden case while it waits for 201 to reply (docs/workflow.md, section 10). */
export function caseDetail(overrides: Partial<CaseDetail> = {}): CaseDetail {
  return {
    id: 1,
    status: "WAITING_RESPONSE",
    event_id: 1,
    shift_id: 1,
    required_replacement_time: "2026-10-09T23:00:00+07:00",
    created_at: DEMO_TIME,
    updated_at: DEMO_TIME,
    gap: {
      id: 1,
      headcount_gap: 1,
      computed_at: DEMO_TIME,
      roles: [{ id: 1, name: "RN", required_count: 5, current_count: 4, gap_count: 1 }],
      skills: [{ id: 1, name: "ICU", required_count: 2, current_count: 2, gap_count: 0 }],
    },
    candidates: [
      { candidate_item_id: 1, rank: 1, staff_id: 201, first_name: "Arunee", last_name: "Demo",
        source: "SAME_WARD", outreach_status: "SENT" },
      { candidate_item_id: 2, rank: 2, staff_id: 202, first_name: "Phanu", last_name: "Demo",
        source: "SAME_WARD", outreach_status: null },
      { candidate_item_id: 3, rank: 3, staff_id: 203, first_name: "Chonthicha", last_name: "Demo",
        source: "SAME_WARD", outreach_status: null },
    ],
    ...overrides,
  };
}

/** An audit row written by the orchestrator unless the overrides say otherwise. */
export function auditEntry(
  id: number, action: string, overrides: Partial<AuditEntry> = {},
): AuditEntry {
  return {
    id,
    action,
    actor_id: 2,
    actor_name: "workflow_orchestrator",
    actor_type: "component",
    entity_type: "STAFFING_CASES",
    entity_id: 1,
    payload: {},
    created_at: DEMO_TIME,
    ...overrides,
  };
}

export function statusChange(id: number, from: string, to: string): AuditEntry {
  return auditEntry(id, "CASE_STATUS_CHANGED", { payload: { from, to } });
}

const staff = (id: number) => ({ actor_id: id, actor_name: String(id), actor_type: "user" });

/** Timeline of the golden case up to WAITING_RESPONSE. */
export function waitingResponseAudit(): AuditEntry[] {
  return [
    auditEntry(1, "EVENT_RECEIVED", {
      ...staff(105), entity_type: "STAFFING_EVENTS",
      payload: { event_type: "STAFF_UNAVAILABLE", shift_id: 1, staff_id: 105 },
    }),
    auditEntry(2, "UNAVAILABILITY_CREATED", {
      ...staff(105), entity_type: "STAFF_UNAVAILABILITY",
      payload: { unavailability_id: 1, staff_id: 105, reason: "UNPLANNED_LEAVE" },
    }),
    auditEntry(3, "CASE_OPENED", { payload: { event_id: 1, shift_id: 1, headcount_gap: 1 } }),
    statusChange(4, "OPEN", "ASSESSING"),
    auditEntry(5, "GAP_ASSESSED", {
      actor_id: 3, actor_name: "staffing_gap_assessment_agent", entity_type: "STAFFING_GAP",
      payload: {
        gap_id: 1,
        headcount_gap: 1,
        role_gaps: [{ role_id: 1, required_count: 5, current_count: 4, gap_count: 1 }],
        skill_gaps: [{ skill_id: 1, required_count: 2, current_count: 2, gap_count: 0 }],
      },
    }),
    statusChange(6, "ASSESSING", "OPTIMIZING"),
    auditEntry(7, "SOLVER_EXECUTED", {
      actor_id: 4, actor_name: "constraint_fair_scheduling_agent", entity_type: "CANDIDATE_PLANS",
      payload: { plan_id: 1, solver_status: "FEASIBLE", candidate_count: 3 },
    }),
    statusChange(8, "OPTIMIZING", "OUTREACH"),
    auditEntry(9, "OFFER_SENT", {
      actor_id: 5, actor_name: "outreach_agent", entity_type: "CANDIDATE_OUTREACH",
      payload: { outreach_id: 1, staff_id: 201, channel: "LINE" },
    }),
    statusChange(10, "OUTREACH", "WAITING_RESPONSE"),
  ];
}

/** Rows added when 201 accepts and the case moves on to WAITING_APPROVAL. */
export function waitingApprovalAudit(): AuditEntry[] {
  return [
    ...waitingResponseAudit(),
    auditEntry(11, "OFFER_ACCEPTED", {
      ...staff(201), entity_type: "CANDIDATE_OUTREACH", payload: { outreach_id: 1, staff_id: 201 },
    }),
    statusChange(12, "WAITING_RESPONSE", "SAFETY_VALIDATION"),
    auditEntry(13, "SAFETY_PASSED", {
      actor_id: 6, actor_name: "safety_rule_engine", entity_type: "SAFETY_VALIDATION",
      payload: { validation_id: 1, staff_id: 201 },
    }),
    auditEntry(14, "APPROVAL_REQUESTED", {
      entity_type: "APPROVAL_REQUEST", payload: { approval_id: 1, approval_mode: "MANUAL" },
    }),
    statusChange(15, "SAFETY_VALIDATION", "WAITING_APPROVAL"),
  ];
}

/** Rows added when 900 approves and the case ends as RESOLVED. */
export function resolvedAudit(): AuditEntry[] {
  return [
    ...waitingApprovalAudit(),
    auditEntry(16, "APPROVAL_APPROVED", {
      ...staff(900), entity_type: "APPROVAL_REQUEST", payload: { approval_id: 1, reason: null },
    }),
    statusChange(17, "WAITING_APPROVAL", "EXECUTING"),
    auditEntry(18, "ASSIGNMENT_CREATED", {
      entity_type: "ROSTER_ASSIGNMENT", entity_id: 8,
      payload: { assignment_id: 8, staff_id: 201, assignment_type: "REPLACEMENT" },
    }),
    auditEntry(19, "CASE_RESOLVED", { payload: { assignment_ids: [8] } }),
    statusChange(20, "EXECUTING", "RESOLVED"),
  ];
}
