"""Join explicitly linked, contiguous roster segments into one duty per staff member.

Callers pass only committed rows of one person. Adjacency without a transfer link
never merges duties. A missing source (outside the read window or cancelled) does
not make the destination disappear. The root shift supplies the duty's identity.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.constraints.context import ShiftSlot


@dataclass(frozen=True)
class DutySegment:
    assignment_id: int
    shift: ShiftSlot
    transferred_from_assignment_id: int | None = None


@dataclass(frozen=True)
class RecordedDuty:
    shift: ShiftSlot
    assignment_ids: frozenset[int]


def recorded_duties(segments: Sequence[DutySegment]) -> tuple[RecordedDuty, ...]:
    rows = {segment.assignment_id: segment for segment in segments}
    successors: dict[int, DutySegment] = {}
    for row in segments:
        source = (
            rows.get(row.transferred_from_assignment_id)
            if row.transferred_from_assignment_id is not None
            else None
        )
        if source is not None and source.shift.end_at == row.shift.start_at:
            if source.assignment_id in successors:
                raise ValueError("A source assignment has multiple transfer destinations")
            successors[source.assignment_id] = row
    destinations = {row.assignment_id for row in successors.values()}
    duties = []
    visited: set[int] = set()
    for root in segments:
        if root.assignment_id in destinations:
            continue
        last = root
        members = {root.assignment_id}
        visited.add(root.assignment_id)
        while last.assignment_id in successors:
            last = successors[last.assignment_id]
            if last.assignment_id in visited:
                raise ValueError("Cyclic transfer links")
            visited.add(last.assignment_id)
            members.add(last.assignment_id)
        duties.append(
            RecordedDuty(
                ShiftSlot(root.shift.shift_id, root.shift.start_at, last.shift.end_at),
                frozenset(members),
            )
        )
    if visited != set(rows):
        raise ValueError("Cyclic transfer links")
    return tuple(duties)


def joined_duties(segments: Sequence[DutySegment]) -> tuple[ShiftSlot, ...]:
    return tuple(duty.shift for duty in recorded_duties(segments))
