"""Wave targets and the order they are filled in (round 1 contract, section 8.3).

A wave asks for slightly more than the gap: every target is ceil(gap * 11 / 10).
One person counts toward every target they match, so a wave never holds more
people than the sum of its targets.

No database access, clock reads, or writes. Two callers:
  * the Solver, to record which targets each member of the first wave fills;
  * contact_candidate, to choose the people of a later wave from the plan.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.enums import SelectionType, TargetType
from app.domain.workflow.case_status import GapFiller

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


def fill_targets(
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    candidates: Sequence[GapFiller],
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
