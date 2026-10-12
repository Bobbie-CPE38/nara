"""Hard Rule codes (round 1 contract, section 7.2).

Source of truth: docs/round1/round1-contract-draft.md section 7.2 and the
Candidate Skip Reasons section of docs/database-schema.md.
Rules:
  * The order of the members is the order of the contract table. Results list the
    codes in this order, and SAFETY_VALIDATION.failure_reason joins them with ",".
  * A value is stored as plain text (failure_reason, validation_snapshot, the
    `skipped` list in audit payloads). Change one only together with the contract.
  * OFFER_LIMIT_REACHED is not a Hard Rule. It needs CANDIDATE_OUTREACH, so it
    lives in the service layer and Safety never checks it.
"""

from enum import StrEnum


class HardRuleCode(StrEnum):
    STAFF_NOT_ACTIVE = "STAFF_NOT_ACTIVE"
    ALREADY_ON_SHIFT = "ALREADY_ON_SHIFT"
    UNAVAILABLE = "UNAVAILABLE"
    SHIFT_CONFLICT = "SHIFT_CONFLICT"
    ROLE_MISMATCH = "ROLE_MISMATCH"
    SKILL_MISMATCH = "SKILL_MISMATCH"
    INSUFFICIENT_REST = "INSUFFICIENT_REST"
    DAILY_HOURS_EXCEEDED = "DAILY_HOURS_EXCEEDED"
    WEEKLY_HOURS_EXCEEDED = "WEEKLY_HOURS_EXCEEDED"
    CONSECUTIVE_SHIFTS_EXCEEDED = "CONSECUTIVE_SHIFTS_EXCEEDED"
    SOURCE_WARD_MINIMUM_VIOLATION = "SOURCE_WARD_MINIMUM_VIOLATION"


# Not a Hard Rule (see the module docstring): the Solver and wave selection write
# this code when a candidate already holds the maximum number of open offers
OFFER_LIMIT_REACHED = "OFFER_LIMIT_REACHED"
