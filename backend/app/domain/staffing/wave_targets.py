"""Wave targets and the order they are filled in (round 1 contract, section 8.3).

A wave asks for slightly more than the gap: every target is ceil(gap * 11 / 10).
One person counts toward every target they match, so a wave never holds more
people than the sum of its targets.

Round 4 PR T4 makes the fill per time slice. elementary_slices() cuts the short
slices of a case gap wherever a person starts or ends inside them, covers() says
who is present for a whole slice (the rule of intervals_closed()), and
fill_targets_by_slice() runs fill_targets() once per piece in time order. A person
chosen in an earlier piece counts as already selected in a later piece they cover,
so a member needed only in a later piece is still kept. Credits of one person are
merged: PRIMARY beats RESERVE and the window is the hull of the pieces where the
credit was given. A person who only counts toward a later piece, as already
selected, gets no new rows there. With slices=None the result is exactly
fill_targets() (the legacy single whole-shift slice).

No database access, clock reads, or writes. Two callers:
  * the Solver, to record which targets each member of the first wave fills;
  * contact_candidate, to choose the people of a later wave from the plan.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import SelectionType, TargetType
from app.domain.workflow.case_status import GapFiller, IntervalGap

# (HEADCOUNT, None), (ROLE, role_id) or (SKILL, skill_id)
_Key = tuple[TargetType, int | None]

_HEADCOUNT: _Key = (TargetType.HEADCOUNT, None)


def wave_target(gap: int) -> int:
    """ceil(gap * 11 / 10), in integers so that rounding can never change it."""
    if gap < 0:
        raise ValueError("A gap must be non-negative")
    return (gap * 11 + 9) // 10


@dataclass(frozen=True)
class TargetCredit:
    """One target a person is counted toward: one CANDIDATE_ITEM_TARGET row."""

    target_type: TargetType
    selection_type: SelectionType
    role_id: int | None = None
    skill_id: int | None = None
    # The window where the credit counts; None is the whole input. Not stored in
    # CANDIDATE_ITEM_TARGET (no time columns): it goes into the plan snapshot
    start_at: datetime | None = None
    end_at: datetime | None = None


@dataclass(frozen=True)
class Slice:
    """One elementary piece [start_at, end_at) of a short slice, with the gaps of its parent."""

    start_at: datetime
    end_at: datetime
    headcount_gap: int
    role_gaps: Mapping[int, int]
    skill_gaps: Mapping[int, int]

    @property
    def seconds(self) -> int:
        return int((self.end_at - self.start_at).total_seconds())


def is_short(interval: IntervalGap) -> bool:
    """True when the slice still misses headcount, a role or a skill."""
    return (
        interval.headcount_gap > 0
        or any(gap > 0 for gap in interval.role_gaps.values())
        or any(gap > 0 for gap in interval.skill_gaps.values())
    )


def covers(person: GapFiller, start: datetime, end: datetime) -> bool:
    """True when the person is present for all of [start, end).

    The presence rule of case_status.intervals_closed(): None means from the shift
    start or until the shift end.
    """
    return (person.start_at is None or person.start_at <= start) and (
        person.end_at is None or person.end_at >= end
    )


def elementary_slices(intervals: Iterable[IntervalGap], people: Iterable[GapFiller]) -> list[Slice]:
    """The short slices, each cut where a person starts or ends strictly inside it.

    Time order, half-open [start, end). Within a piece every person is either
    present for all of it or not at all.
    """
    persons = list(people)
    pieces: list[Slice] = []
    for interval in intervals:
        if not is_short(interval):
            continue
        cuts = {interval.start_at, interval.end_at}
        for person in persons:
            for point in (person.start_at, person.end_at):
                if point is not None and interval.start_at < point < interval.end_at:
                    cuts.add(point)
        points = sorted(cuts)
        pieces.extend(
            Slice(start, end, interval.headcount_gap, interval.role_gaps, interval.skill_gaps)
            for start, end in zip(points, points[1:], strict=False)
        )
    return sorted(pieces, key=lambda piece: (piece.start_at, piece.end_at))


def fill_targets(
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    candidates: Sequence[GapFiller],
    already_selected: Sequence[GapFiller] = (),
) -> dict[int, tuple[TargetCredit, ...]]:
    """Choose people until every target is zero or nobody is left.

    `candidates` is in preference order: the Solver passes ranking_key order,
    contact_candidate passes rank order. The result maps a staff ID to the
    targets that person is counted toward, in the order the people were chosen.
    A person who was not needed is absent.

    Targets are filled skills first, then roles, then headcount. Within skills
    and within roles the one the fewest candidates match comes first, then the
    lower ID. For each target the person who closes the most open targets is
    chosen, then the earlier one in `candidates`.

    A chosen person lowers every open target they match by one. The first `gap`
    people of a target are PRIMARY, the rest up to the target are RESERVE.
    """
    staff_ids = [person.staff_id for person in candidates]
    if len(staff_ids) != len(set(staff_ids)):
        raise ValueError("A candidate is listed twice")
    preference = {staff_id: index for index, staff_id in enumerate(staff_ids)}

    gaps: dict[_Key, int] = {_HEADCOUNT: headcount_gap}
    gaps.update({(TargetType.ROLE, role_id): gap for role_id, gap in role_gaps.items()})
    gaps.update({(TargetType.SKILL, skill_id): gap for skill_id, gap in skill_gaps.items()})
    remaining = {key: wave_target(gap) for key, gap in gaps.items()}
    credited: Counter[_Key] = Counter()

    def keys_of(person: GapFiller) -> list[_Key]:
        """The targets the person matches, in the order their rows are written."""
        return [
            *((TargetType.SKILL, skill_id) for skill_id in sorted(person.skill_ids)),
            (TargetType.ROLE, person.role_id),
            _HEADCOUNT,
        ]

    def open_keys(person: GapFiller) -> list[_Key]:
        return [key for key in keys_of(person) if remaining.get(key, 0) > 0]

    # First-wave replacements fill only vacancies, without applying 1.1 twice.
    if set(staff_ids) & {person.staff_id for person in already_selected}:
        raise ValueError("A selected candidate is also listed for replacement")
    for person in already_selected:
        for key in open_keys(person):
            credited[key] += 1
            remaining[key] -= 1

    def best_first(person: GapFiller) -> tuple[int, int]:
        return (len(open_keys(person)), -preference[person.staff_id])

    holders = Counter(key for person in candidates for key in keys_of(person))

    def scarcest_first(key: _Key) -> tuple[int, int]:
        return (holders[key], key[1] or 0)

    order: list[_Key] = [
        *sorted((key for key in remaining if key[0] is TargetType.SKILL), key=scarcest_first),
        *sorted((key for key in remaining if key[0] is TargetType.ROLE), key=scarcest_first),
        _HEADCOUNT,
    ]

    unused = list(candidates)
    selected: dict[int, tuple[TargetCredit, ...]] = {}
    for target in order:
        while remaining[target] > 0:
            matching = [person for person in unused if target in keys_of(person)]
            if not matching:
                break
            chosen = max(matching, key=best_first)
            credits: list[TargetCredit] = []
            for key in open_keys(chosen):
                target_type, item_id = key
                credits.append(
                    TargetCredit(
                        target_type=target_type,
                        selection_type=(
                            SelectionType.PRIMARY
                            if credited[key] < gaps[key]
                            else SelectionType.RESERVE
                        ),
                        role_id=item_id if target_type is TargetType.ROLE else None,
                        skill_id=item_id if target_type is TargetType.SKILL else None,
                    )
                )
                credited[key] += 1
                remaining[key] -= 1
            selected[chosen.staff_id] = tuple(credits)
            unused.remove(chosen)
    return selected


def fill_targets_by_slice(
    *,
    slices: Sequence[Slice] | None,
    candidates: Sequence[GapFiller],
    already_selected: Sequence[GapFiller] = (),
    counted: Sequence[GapFiller] = (),
    headcount_gap: int = 0,
    role_gaps: Mapping[int, int] | None = None,
    skill_gaps: Mapping[int, int] | None = None,
) -> dict[int, tuple[TargetCredit, ...]]:
    """fill_targets() once per elementary slice, in time order.

    slices=None is the legacy single whole-shift slice: the result is exactly
    fill_targets() with headcount_gap, role_gaps and skill_gaps (the only use of
    those three arguments; `counted` is not used there).

    For each slice the residual gap is the slice gap minus the `counted` people
    present for the whole slice, counted by unique staff and floored at 0. People
    chosen in earlier slices and `already_selected`, restricted to those present
    for this slice, count as already selected; candidates not present for the
    whole slice are not offered for it. `candidates` is in preference order.

    The result maps a staff ID to their merged credits, people in the order they
    were first chosen. The same (target, role, skill) in two slices is one credit:
    PRIMARY beats RESERVE, and the window is the hull of the slices where it was
    given. A person who is already selected in a slice gets no new rows there.
    """
    if slices is None:
        return fill_targets(
            headcount_gap=headcount_gap,
            role_gaps={} if role_gaps is None else role_gaps,
            skill_gaps={} if skill_gaps is None else skill_gaps,
            candidates=candidates,
            already_selected=already_selected,
        )
    taken = {person.staff_id for person in already_selected}
    by_id = {person.staff_id: person for person in candidates}
    chosen: dict[int, GapFiller] = {}
    credits: dict[int, dict[_Key, tuple[SelectionType, datetime, datetime]]] = {}
    for piece in slices:
        start, end = piece.start_at, piece.end_at
        present = {person.staff_id: person for person in counted if covers(person, start, end)}
        by_role = Counter(person.role_id for person in present.values())
        by_skill = Counter(skill_id for person in present.values() for skill_id in person.skill_ids)
        picked = fill_targets(
            headcount_gap=max(0, piece.headcount_gap - len(present)),
            role_gaps={
                role_id: max(0, gap - by_role[role_id]) for role_id, gap in piece.role_gaps.items()
            },
            skill_gaps={
                skill_id: max(0, gap - by_skill[skill_id])
                for skill_id, gap in piece.skill_gaps.items()
            },
            candidates=[
                person
                for person in candidates
                if person.staff_id not in taken
                and person.staff_id not in chosen
                and covers(person, start, end)
            ],
            already_selected=[
                person
                for person in (*already_selected, *chosen.values())
                if covers(person, start, end)
            ],
        )
        for staff_id, rows in picked.items():
            chosen[staff_id] = by_id[staff_id]
            merged = credits.setdefault(staff_id, {})
            for row in rows:
                key: _Key = (
                    row.target_type,
                    row.role_id if row.target_type is TargetType.ROLE else row.skill_id,
                )
                known = merged.get(key)
                if known is None:
                    merged[key] = (row.selection_type, start, end)
                else:
                    kind = (
                        SelectionType.PRIMARY
                        if SelectionType.PRIMARY in (known[0], row.selection_type)
                        else SelectionType.RESERVE
                    )
                    merged[key] = (kind, min(known[1], start), max(known[2], end))
    return {
        staff_id: tuple(
            TargetCredit(
                target_type=target_type,
                selection_type=kind,
                role_id=item_id if target_type is TargetType.ROLE else None,
                skill_id=item_id if target_type is TargetType.SKILL else None,
                start_at=first,
                end_at=last,
            )
            for (target_type, item_id), (kind, first, last) in merged.items()
        )
        for staff_id, merged in credits.items()
    }
