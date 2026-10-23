"""Safety of a hurried manual pick against nara's Hard Rules (round 6 PR E1).

Question: when a nurse drops out of a night shift and the head nurse picks a replacement
from the paper roster, how often does that pick break a safety rule? And how often can
nara still find a safe person, in the ward or in another ward?

Method (all synthetic, seeded, no database):
  * Two wards (ICU and Medicine), 16 RNs each, a 12-hour day shift (07-19) and night
    shift (19-07), two weeks of roster. The roster is built shift by shift and every
    assignment passes the same Hard Rules first, so the starting roster is legal.
  * A case: on a random night of the second week one rostered ICU nurse drops out.
    The replacement must be an RN, and must hold the ICU skill when the shift is left
    with fewer ICU-skilled nurses than it needs.
  * Three manual baselines pick from the head nurse's own ward, seeing only what a
    paper roster shows: name, role, skills, who works a shift that starts on that day
    (the night itself or the day shift before it), and the leave written on the roster.
      B1 first free nurse in roster order
      B2 the free nurse with the fewest shifts this week on the roster
      B3 a random free nurse
    "Free" means: an RN, not rostered on any shift that starts on that day, and not on
    leave written on the roster that day.
  * Every pick, and every candidate nara considers, is judged by
    app.domain.constraints.evaluator.evaluate(), the function the Solver, wave
    selection and Safety use. Ten of the eleven Hard Rules can fail here:
    SOURCE_WARD_MINIMUM_VIOLATION needs a move out of another shift (a source shift),
    which these cases do not model. nara takes only candidates that pass every rule, from the
    ward first and then the other ward.

What this does NOT measure: how often real head nurses make mistakes. The rates depend
on the synthetic roster and on the baselines written above, and are reported as such.

Run:  python -m app.evaluation.safety --cases 1000 --seed 20261023 --out results/
"""

import argparse
import csv
import json
import math
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from app.core.clock import APP_TIMEZONE
from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.context import (
    CandidateContext,
    HardRulePolicy,
    RosterEntry,
    ShiftSlot,
    UnavailabilityPeriod,
    week_start,
)
from app.domain.constraints.evaluator import HardRuleResult, evaluate
from app.domain.enums import RosterStatus, StaffStatus

# The demo policy of the seed (backend/app/seed/base_data.py), so the numbers match the app
POLICY = HardRulePolicy(
    require_active_staff=True,
    prevent_shift_conflict=True,
    require_matching_role=True,
    require_matching_skill=True,
    preserve_source_ward_minimum=True,
    preserve_minimum_staffing=True,
    minimum_rest_hours=Decimal(11),
    maximum_daily_hours=Decimal(12),
    maximum_weekly_hours=Decimal(52),
    maximum_consecutive_shifts=7,
)

RN = 1
ICU_SKILL = 1
BLS_SKILL = 2
WARDS = {1: "ICU", 2: "Medicine"}
NURSES_PER_WARD = 16
# Nurses each shift needs, and how many of them must hold the ICU skill
NEEDED_PER_SHIFT = {1: (4, 2), 2: (4, 0)}
# Share of nurses who hold the ICU skill
ICU_SKILL_SHARE = {1: 0.6, 2: 0.15}
LEAVE_SHARE = 0.08  # nurses with a written leave of 1-3 days in the two weeks
DAYS = 14
BASELINES = ("B1_first_free", "B2_fewest_shifts", "B3_random_free")
# Needs CandidateContext.source_shift, which no case here sets, so it can never fail
NOT_MODELLED_RULES = (HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION,)


@dataclass
class Nurse:
    staff_id: int
    ward_id: int
    skill_ids: frozenset[int]
    leave: list[UnavailabilityPeriod] = field(default_factory=list)
    shifts: list[ShiftSlot] = field(default_factory=list)


@dataclass(frozen=True)
class Shift:
    slot: ShiftSlot
    ward_id: int
    day: int
    night: bool


def _slot(shift_id: int, start: datetime, hours: int = 12) -> ShiftSlot:
    return ShiftSlot(shift_id, start, start + timedelta(hours=hours))


def _context(nurse: Nurse, shift: ShiftSlot, target_skills: frozenset[int]) -> CandidateContext:
    return CandidateContext(
        staff_id=nurse.staff_id,
        status=StaffStatus.ACTIVE,
        role_id=RN,
        skill_ids=nurse.skill_ids,
        proposed_shift=shift,
        roster=tuple(RosterEntry(s, RosterStatus.ASSIGNED) for s in nurse.shifts),
        unavailability=tuple(nurse.leave),
        target_role_ids=frozenset({RN}),
        target_skill_ids=target_skills,
    )


def judge(nurse: Nurse, shift: ShiftSlot, target_skills: frozenset[int]) -> HardRuleResult:
    return evaluate(_context(nurse, shift, target_skills), POLICY)


def _on_leave(nurse: Nurse, shift: ShiftSlot) -> bool:
    return any(
        period.start_at < shift.end_at and (period.end_at is None or period.end_at > shift.start_at)
        for period in nurse.leave
    )


@dataclass
class World:
    nurses: list[Nurse]
    shifts: list[Shift]
    first_day: datetime


def build_world(rng: random.Random, nurses_per_ward: int = NURSES_PER_WARD) -> World:
    """Two wards and a legal two-week roster, built shift by shift through the Hard Rules."""
    # Start on a Monday so the two weeks are two whole rule weeks
    first_day = datetime(2026, 10, 5, tzinfo=APP_TIMEZONE)
    nurses: list[Nurse] = []
    for ward_id in WARDS:
        for index in range(nurses_per_ward):
            skills = {BLS_SKILL}
            if rng.random() < ICU_SKILL_SHARE[ward_id]:
                skills.add(ICU_SKILL)
            nurses.append(Nurse(ward_id * 100 + index + 1, ward_id, frozenset(skills)))
    for nurse in nurses:
        if rng.random() < LEAVE_SHARE:
            start_day = rng.randrange(DAYS)
            length = rng.randint(1, 3)
            start = datetime.combine(
                (first_day + timedelta(days=start_day)).date(), time.min, tzinfo=APP_TIMEZONE
            )
            nurse.leave.append(UnavailabilityPeriod(start, start + timedelta(days=length)))

    shifts: list[Shift] = []
    shift_id = 1
    for day in range(DAYS):
        date = first_day + timedelta(days=day)
        for night in (False, True):
            start = date.replace(hour=19 if night else 7)
            for ward_id in WARDS:
                shifts.append(Shift(_slot(shift_id, start), ward_id, day, night))
                shift_id += 1

    for shift in shifts:
        needed, needed_icu = NEEDED_PER_SHIFT[shift.ward_id]
        ward_nurses = [n for n in nurses if n.ward_id == shift.ward_id]
        rng.shuffle(ward_nurses)
        # Fill the ICU-skilled places first, then the rest, each with a legal nurse
        chosen: list[Nurse] = []
        for need_skill, count in ((frozenset({ICU_SKILL}), needed_icu), (frozenset(), needed)):
            for nurse in ward_nurses:
                if len(chosen) >= count:
                    break
                if nurse in chosen:
                    continue
                if judge(nurse, shift.slot, need_skill).passed:
                    chosen.append(nurse)
        for nurse in chosen:
            nurse.shifts.append(shift.slot)
    return World(nurses, shifts, first_day)


def _weekly_loads(world: World) -> list[int]:
    """Shifts of each nurse in each of the two weeks: how full the starting roster is."""
    return [
        _shifts_this_week(nurse, world.first_day + timedelta(days=7 * week))
        for nurse in world.nurses
        for week in (0, 1)
    ]


def _shifts_this_week(nurse: Nurse, moment: datetime) -> int:
    week = week_start(moment)
    return sum(1 for shift in nurse.shifts if week_start(shift.start_at) == week)


def _free_on_paper(nurse: Nurse, shift: ShiftSlot) -> bool:
    """What a hurried look at the paper roster calls free for this night."""
    day = shift.start_at.astimezone(APP_TIMEZONE).date()
    works_that_day = any(s.start_at.astimezone(APP_TIMEZONE).date() == day for s in nurse.shifts)
    return not works_that_day and not _on_leave(nurse, shift)


@dataclass
class CaseResult:
    case: int
    shift_id: int
    dropped_staff_id: int
    needs_icu_skill: bool
    free_on_paper: int
    safe_in_ward: int
    safe_in_other_ward: int
    baseline: dict[str, tuple[int | None, tuple[str, ...]]]
    nara_pick: int | None
    nara_from_other_ward: bool
    # The rules nara's own pick breaks: always empty by design, and counted to show it
    nara_broken_rules: tuple[str, ...] = ()


def run_case(world: World, rng: random.Random, number: int) -> CaseResult | None:
    """One drop-out on a random ICU night of the second week, judged for every baseline."""
    nights = [s for s in world.shifts if s.ward_id == 1 and s.night and s.day >= 7]
    shift = rng.choice(nights)
    rostered = [n for n in world.nurses if shift.slot in n.shifts]
    if not rostered:
        return None
    dropped = rng.choice(rostered)
    staying = [n for n in rostered if n is not dropped]
    _, needed_icu = NEEDED_PER_SHIFT[shift.ward_id]
    icu_left = sum(1 for n in staying if ICU_SKILL in n.skill_ids)
    needs_skill = ICU_SKILL in dropped.skill_ids and icu_left < needed_icu
    target = frozenset({ICU_SKILL}) if needs_skill else frozenset()

    # The dropped nurse's row is taken off for the case, then put back
    dropped.shifts.remove(shift.slot)
    try:
        own = [n for n in world.nurses if n.ward_id == shift.ward_id and n is not dropped]
        other = [n for n in world.nurses if n.ward_id != shift.ward_id]
        on_paper = [n for n in own if _free_on_paper(n, shift.slot)]

        picks: dict[str, Nurse | None] = {
            "B1_first_free": on_paper[0] if on_paper else None,
            "B2_fewest_shifts": min(
                on_paper,
                key=lambda n: (_shifts_this_week(n, shift.slot.start_at), n.staff_id),
                default=None,
            ),
            "B3_random_free": rng.choice(on_paper) if on_paper else None,
        }
        baseline: dict[str, tuple[int | None, tuple[str, ...]]] = {}
        for name, nurse in picks.items():
            if nurse is None:
                baseline[name] = (None, ())
                continue
            failed = judge(nurse, shift.slot, target).failed_rules
            baseline[name] = (nurse.staff_id, tuple(code.value for code in failed))

        safe_own = [n for n in own if judge(n, shift.slot, target).passed]
        safe_other = [n for n in other if judge(n, shift.slot, target).passed]
        fewest: Callable[[Nurse], tuple[int, int]] = lambda n: (  # noqa: E731
            _shifts_this_week(n, shift.slot.start_at),
            n.staff_id,
        )
        nara = min(safe_own, key=fewest, default=None) or min(safe_other, key=fewest, default=None)
        return CaseResult(
            case=number,
            shift_id=shift.slot.shift_id,
            dropped_staff_id=dropped.staff_id,
            needs_icu_skill=needs_skill,
            free_on_paper=len(on_paper),
            safe_in_ward=len(safe_own),
            safe_in_other_ward=len(safe_other),
            baseline=baseline,
            nara_pick=None if nara is None else nara.staff_id,
            nara_from_other_ward=nara is not None and not safe_own,
            nara_broken_rules=()
            if nara is None
            else tuple(code.value for code in judge(nara, shift.slot, target).failed_rules),
        )
    finally:
        dropped.shifts.append(shift.slot)


def wilson(successes: int, total: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval of a proportion."""
    if total == 0:
        return (math.nan, math.nan)
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return (centre - half, centre + half)


def run(
    cases: int, seed: int, worlds: int = 20, nurses_per_ward: int = NURSES_PER_WARD
) -> tuple[list[CaseResult], dict[str, object]]:
    """`cases` cases spread over `worlds` independent rosters."""
    rng = random.Random(seed)
    results: list[CaseResult] = []
    per_world = math.ceil(cases / worlds)
    number = 0
    loads: list[int] = []
    while len(results) < cases:
        world = build_world(rng, nurses_per_ward)
        loads.extend(_weekly_loads(world))
        for _ in range(per_world):
            if len(results) >= cases:
                break
            result = run_case(world, rng, number)
            number += 1
            if result is not None:
                results.append(result)
    summary = summarise(results, seed, worlds)
    summary["nurses_per_ward"] = nurses_per_ward
    summary["roster_shifts_per_nurse_week"] = {str(k): v for k, v in sorted(Counter(loads).items())}
    summary["roster_mean_shifts_per_nurse_week"] = round(sum(loads) / len(loads), 2)
    return results, summary


def summarise(results: Sequence[CaseResult], seed: int, worlds: int) -> dict[str, object]:
    total = len(results)
    summary: dict[str, object] = {
        "seed": seed,
        "rosters": worlds,
        "cases": total,
        "policy": {
            "minimum_rest_hours": 11,
            "maximum_daily_hours": 12,
            "maximum_weekly_hours": 52,
            "maximum_consecutive_shifts": 7,
        },
        "rules_that_can_fail_here": len(HardRuleCode) - len(NOT_MODELLED_RULES),
        "rules_not_modelled": [code.value for code in NOT_MODELLED_RULES],
        "avg_free_on_paper": round(sum(r.free_on_paper for r in results) / total, 2),
        "needs_icu_skill_share": round(sum(r.needs_icu_skill for r in results) / total, 4),
    }
    for name in BASELINES:
        picked = [r for r in results if r.baseline[name][0] is not None]
        unsafe = [r for r in picked if r.baseline[name][1]]
        low, high = wilson(len(unsafe), len(picked))
        rules = Counter(code for r in unsafe for code in r.baseline[name][1])
        summary[name] = {
            "picked": len(picked),
            "no_one_free_on_paper": total - len(picked),
            "unsafe": len(unsafe),
            "unsafe_rate": round(len(unsafe) / len(picked), 4) if picked else None,
            "unsafe_rate_95ci": [round(low, 4), round(high, 4)],
            "broken_rules": dict(rules.most_common()),
        }
    filled = [r for r in results if r.nara_pick is not None]
    other = [r for r in filled if r.nara_from_other_ward]
    low, high = wilson(len(filled), total)
    summary["nara"] = {
        "safe_pick_found": len(filled),
        "safe_pick_rate": round(len(filled) / total, 4),
        "safe_pick_rate_95ci": [round(low, 4), round(high, 4)],
        "unsafe_picks": sum(1 for r in filled if r.nara_broken_rules),
        "from_other_ward": len(other),
        "no_safe_person_in_ward": sum(1 for r in results if r.safe_in_ward == 0),
        "no_safe_person_anywhere": total - len(filled),
    }
    return summary


def write(results: Sequence[CaseResult], summary: dict[str, object], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "safety_cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "case",
                "shift_id",
                "dropped_staff_id",
                "needs_icu_skill",
                "free_on_paper",
                "safe_in_ward",
                "safe_in_other_ward",
                *(f"{b}_pick" for b in BASELINES),
                *(f"{b}_broken_rules" for b in BASELINES),
                "nara_pick",
                "nara_from_other_ward",
                "nara_broken_rules",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.case,
                    r.shift_id,
                    r.dropped_staff_id,
                    r.needs_icu_skill,
                    r.free_on_paper,
                    r.safe_in_ward,
                    r.safe_in_other_ward,
                    *(r.baseline[b][0] for b in BASELINES),
                    *(";".join(r.baseline[b][1]) for b in BASELINES),
                    r.nara_pick,
                    r.nara_from_other_ward,
                    ";".join(r.nara_broken_rules),
                ]
            )
    (out / "safety_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--worlds", type=int, default=20)
    parser.add_argument("--nurses", type=int, default=NURSES_PER_WARD, help="RNs per ward")
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args()
    results, summary = run(args.cases, args.seed, args.worlds, args.nurses)
    write(results, summary, args.out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
