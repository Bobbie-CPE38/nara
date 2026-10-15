"""Inputs of the Hard Rules and the working-time values derived from them.

Round 1 contract, section 7 (docs/round1/round1-contract-draft.md). No database
access, clock reads, or writes. The caller loads the candidate's rows and builds
these values, the same way callers of gap_calculator do.

The functions at the bottom hold the one definition of day, week and consecutive
run (Q14 and "the two ceilings" in section 7.2). working_time_service and the
Solver's soft cost must call them instead of keeping their own copies.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction

from app.core.clock import APP_TIMEZONE
from app.domain.enums import COMMITTED_ROSTER_STATUSES, RosterStatus, StaffStatus

# A rest of at most this long keeps two shifts in the same consecutive run
MAX_REST_WITHIN_RUN = timedelta(hours=24)

_MICROSECOND = timedelta(microseconds=1)
_MICROSECONDS_PER_HOUR = 3_600_000_000


@dataclass(frozen=True, kw_only=True)
class HardRulePolicy:
    """The HARD_CONSTRAINT_POLICY values the rules read.

    A flag that is False switches its rule off. The numeric limits have no flag
    and are always checked. preserve_minimum_staffing is not a rule of its own:
    it selects the target headcount of the source shift (workflow.md section 3.6).
    """

    require_active_staff: bool
    prevent_shift_conflict: bool
    require_matching_role: bool
    require_matching_skill: bool
    preserve_source_ward_minimum: bool
    preserve_minimum_staffing: bool
    minimum_rest_hours: Decimal | int
    maximum_daily_hours: Decimal | int
    maximum_weekly_hours: Decimal | int
    maximum_consecutive_shifts: int

    def __post_init__(self) -> None:
        for name in ("minimum_rest_hours", "maximum_daily_hours", "maximum_weekly_hours"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
                raise TypeError(f"{name} must be a Decimal or int, not float or bool")
            if not Decimal(value).is_finite() or value < 0:
                raise ValueError(f"{name} must be non-negative and finite")
        limit = self.maximum_consecutive_shifts
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("maximum_consecutive_shifts must be an int")
        if limit < 0:
            raise ValueError("maximum_consecutive_shifts must be non-negative")


@dataclass(frozen=True)
class ShiftSlot:
    """Identity and time of one shift."""

    shift_id: int
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        if self.start_at.utcoffset() is None or self.end_at.utcoffset() is None:
            raise ValueError("Shift times must be timezone-aware")
        if self.end_at <= self.start_at:
            raise ValueError("A shift must end after it starts")


@dataclass(frozen=True)
class RosterEntry:
    """One roster row of the candidate, joined with its shift.

    Pass rows of every status. The rules decide which statuses count.
    """

    shift: ShiftSlot
    status: RosterStatus


@dataclass(frozen=True)
class UnavailabilityPeriod:
    """One STAFF_UNAVAILABILITY row. No end_at = unavailable from start_at on."""

    start_at: datetime
    end_at: datetime | None

    def __post_init__(self) -> None:
        if self.start_at.utcoffset() is None or (
            self.end_at is not None and self.end_at.utcoffset() is None
        ):
            raise ValueError("Unavailability times must be timezone-aware")


@dataclass(frozen=True)
class SourceShift:
    """The shift the candidate would be moved out of.

    assigned_count is the headcount of that shift with the candidate still on it.
    """

    assigned_count: int
    required_staff: int
    minimum_staff: int

    def __post_init__(self) -> None:
        if min(self.assigned_count, self.required_staff, self.minimum_staff) < 0:
            raise ValueError("Source shift counts must be non-negative")


@dataclass(frozen=True, kw_only=True)
class CandidateContext:
    """Everything the rules need to know about one candidate and one proposed shift.

    roster must hold every row of the candidate that can matter: the whole
    Asia/Bangkok week of the proposed shift, and the unbroken run of shifts
    around it. A missing row makes a rule pass silently.

    target_role_ids are the roles the candidate may have. The caller passes one
    of two sets (Q55, and section 8.3 of the contract):
      * the roles of the role targets the candidate is selected to fill, or
      * for a candidate who fills no role target (selected for headcount or a
        skill only), the role IDs of the requirement of the proposed shift.
    The second set is not optional: without it a role the shift does not use
    passes. The set is empty only when the requirement lists no role at all,
    and then any role passes.

    target_skill_ids are the skills of the skill targets the candidate is
    selected to fill (Q55). The candidate must hold every one of them. An empty
    set asks for no skill, so a candidate selected for headcount only passes
    without the skill the case is short of.

    source_shift is None when taking the proposed shift removes no existing
    assignment, which is every case in round 1.

    linked_duty is the kept part of the source shift that runs straight into
    proposed_shift when the candidate is moved. It is set only from a recorded
    source assignment, never from two rows that merely touch: a plain
    back-to-back pair stays two duties and the rest rule still rejects it. With
    it, linked_duty and proposed_shift are one duty for the rest, daily, weekly and
    consecutive-shift rules (see duty_slot). None changes nothing.

    PENDING_APPROVAL counts as committed. Nothing writes it in round 1; a later
    step that writes it for the accepted candidate before Safety must leave that
    row out, or ALREADY_ON_SHIFT blocks the candidate on their own assignment.
    """

    staff_id: int
    status: StaffStatus
    role_id: int
    skill_ids: frozenset[int]
    proposed_shift: ShiftSlot
    roster: tuple[RosterEntry, ...]
    unavailability: tuple[UnavailabilityPeriod, ...]
    target_role_ids: frozenset[int]
    target_skill_ids: frozenset[int]
    source_shift: SourceShift | None = None
    linked_duty: ShiftSlot | None = None

    def __post_init__(self) -> None:
        # Copy first: a caller-owned list or set could still change afterwards
        object.__setattr__(self, "skill_ids", frozenset(self.skill_ids))
        object.__setattr__(self, "roster", tuple(self.roster))
        object.__setattr__(self, "unavailability", tuple(self.unavailability))
        object.__setattr__(self, "target_role_ids", frozenset(self.target_role_ids))
        object.__setattr__(self, "target_skill_ids", frozenset(self.target_skill_ids))

        slots = {self.proposed_shift.shift_id: self.proposed_shift}
        for entry in self.roster:
            known = slots.setdefault(entry.shift.shift_id, entry.shift)
            if known != entry.shift:
                raise ValueError(f"Conflicting times for shift_id={entry.shift.shift_id}")

        linked = self.linked_duty
        if linked is not None:
            if linked.shift_id == self.proposed_shift.shift_id:
                raise ValueError("linked_duty must be a different shift from the proposed shift")
            if linked.end_at != self.proposed_shift.start_at:
                raise ValueError("linked_duty must end exactly when the proposed shift starts")
            if not any(
                entry.status in COMMITTED_ROSTER_STATUSES and entry.shift == linked
                for entry in self.roster
            ):
                raise ValueError("linked_duty must match a committed roster entry")


# --------------------------------------------------------------------------- #
# Day, week and hours (Q14)
# --------------------------------------------------------------------------- #
def hours(duration: timedelta) -> Fraction:
    """Exact hours of a duration, so a limit is never crossed by rounding."""
    return Fraction(duration // _MICROSECOND, _MICROSECONDS_PER_HOUR)


def shift_hours(shift: ShiftSlot) -> Fraction:
    """Hours of the whole shift. A shift is never split at midnight."""
    return hours(shift.end_at - shift.start_at)


def local_day(moment: datetime) -> date:
    """The Asia/Bangkok date of `moment`. A shift belongs to the day it starts on."""
    return moment.astimezone(APP_TIMEZONE).date()


def week_start(moment: datetime) -> datetime:
    """Monday 00:00 Asia/Bangkok of the week that holds `moment`.

    The week ends 7 days later. A shift belongs to the week it starts in.
    """
    day = local_day(moment)
    monday = day - timedelta(days=day.weekday())
    return datetime.combine(monday, time.min, tzinfo=APP_TIMEZONE)


# --------------------------------------------------------------------------- #
# Values of one candidate after adding the proposed shift
# --------------------------------------------------------------------------- #
def leave_overlaps_shift(
    leave_start: datetime, leave_end: datetime | None, shift_start: datetime, shift_end: datetime
) -> bool:
    """A leave period covers part of a shift. No end means it has not ended.

    Touching at a boundary is not overlapping. The UNAVAILABLE rule uses this, and
    unavailability_service.leave_overlaps_shift_sql() is the same rule in SQL.
    """
    return leave_start < shift_end and (leave_end is None or leave_end > shift_start)


def is_on_proposed_shift(context: CandidateContext) -> bool:
    """True when the candidate already holds a committed row on the proposed shift."""
    return any(
        entry.status in COMMITTED_ROSTER_STATUSES
        and entry.shift.shift_id == context.proposed_shift.shift_id
        for entry in context.roster
    )


def was_removed_from_proposed_shift(context: CandidateContext) -> bool:
    """True when a roster row of the candidate on the proposed shift is CANCELLED.

    The person left that shift or was taken off it (leave, ASSIGNMENT_CANCELLED),
    so the same shift is not offered to them again. A cancelled row on another
    shift says nothing about this one.
    """
    return any(
        entry.status is RosterStatus.CANCELLED
        and entry.shift.shift_id == context.proposed_shift.shift_id
        for entry in context.roster
    )


def other_committed_shifts(context: CandidateContext) -> tuple[ShiftSlot, ...]:
    """The candidate's committed shifts other than the proposed one, by start time.

    Repeated rows of one shift count once.
    """
    shifts = {
        entry.shift.shift_id: entry.shift
        for entry in context.roster
        if entry.status in COMMITTED_ROSTER_STATUSES
        and entry.shift.shift_id != context.proposed_shift.shift_id
    }
    return tuple(sorted(shifts.values(), key=_by_start))


def duty_slot(context: CandidateContext) -> ShiftSlot:
    """The continuous duty that holds the proposed shift.

    With a linked_duty it runs from the start of the kept source part to the end of
    the proposed shift and carries the proposed shift_id. Without one it is the
    proposed shift itself.
    """
    linked = context.linked_duty
    proposed = context.proposed_shift
    if linked is None:
        return proposed
    return ShiftSlot(proposed.shift_id, linked.start_at, proposed.end_at)


def other_duties(context: CandidateContext) -> tuple[ShiftSlot, ...]:
    """The committed shifts other than the proposed one and the linked part.

    The linked part is inside duty_slot, so the rest and consecutive-shift rules
    must not see it as a separate shift. Same as other_committed_shifts when there
    is no linked_duty.
    """
    linked = context.linked_duty
    if linked is None:
        return other_committed_shifts(context)
    return tuple(
        shift for shift in other_committed_shifts(context) if shift.shift_id != linked.shift_id
    )


def daily_hours(context: CandidateContext) -> Fraction:
    """Hours on the day of the proposed shift, the proposed shift included.

    A duty belongs to the day it starts on, so with a linked_duty the day is the
    one the kept source part starts on. The linked part is truncated and does not
    overlap the proposed shift, so it is summed once with the other shifts.
    """
    day = local_day(duty_slot(context).start_at)
    return shift_hours(context.proposed_shift) + sum(
        (
            shift_hours(shift)
            for shift in other_committed_shifts(context)
            if local_day(shift.start_at) == day
        ),
        Fraction(0),
    )


def weekly_hours(context: CandidateContext) -> Fraction:
    """Hours in the week of the proposed shift, the proposed shift included.

    As in daily_hours, a duty belongs to the week it starts in.
    """
    week = week_start(duty_slot(context).start_at)
    return shift_hours(context.proposed_shift) + sum(
        (
            shift_hours(shift)
            for shift in other_committed_shifts(context)
            if week_start(shift.start_at) == week
        ),
        Fraction(0),
    )


def projected_consecutive_shifts(context: CandidateContext) -> int:
    """Length of the run that holds the proposed shift once it is inserted.

    Shifts are in one run while the rest between them is at most 24 hours. Real
    time is used: a run does not reset at a day or week boundary. The proposed
    shift can join the run before it to the run after it. A moved candidate's
    duty (see duty_slot) counts once, not once per ward.
    """
    proposed = duty_slot(context)
    count = 0
    run_end: datetime | None = None
    holds_proposed = False
    for shift in sorted((*other_duties(context), proposed), key=_by_start):
        if run_end is not None and shift.start_at - run_end > MAX_REST_WITHIN_RUN:
            if holds_proposed:
                break
            count, run_end = 0, None
        count += 1
        holds_proposed = holds_proposed or shift.shift_id == proposed.shift_id
        # Overlapping shifts are SHIFT_CONFLICT's business, but the run still ends
        # at the latest end, not at the end of the shift that started last
        run_end = shift.end_at if run_end is None else max(run_end, shift.end_at)
    return count


def _by_start(shift: ShiftSlot) -> tuple[datetime, datetime, int]:
    return (shift.start_at, shift.end_at, shift.shift_id)
