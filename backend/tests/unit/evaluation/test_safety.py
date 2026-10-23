"""The safety evaluation (round 6 PR E1): repeatable, judged by the real Hard Rules."""

import math
import random

from app.evaluation import safety


def test_the_same_seed_gives_the_same_results() -> None:
    first = safety.run(60, seed=7, worlds=3)
    second = safety.run(60, seed=7, worlds=3)
    assert first[1] == second[1]
    assert [r.baseline for r in first[0]] == [r.baseline for r in second[0]]


def test_the_starting_roster_is_legal_under_the_hard_rules() -> None:
    world = safety.build_world(random.Random(3))
    for nurse in world.nurses:
        for shift in nurse.shifts:
            nurse.shifts.remove(shift)
            try:
                assert safety.judge(nurse, shift, frozenset()).passed, (nurse.staff_id, shift)
            finally:
                nurse.shifts.append(shift)


def test_nara_only_picks_people_who_pass_every_rule() -> None:
    rng = random.Random(11)
    world = safety.build_world(rng)
    by_id = {nurse.staff_id: nurse for nurse in world.nurses}
    shifts = {shift.slot.shift_id: shift.slot for shift in world.shifts}
    for number in range(40):
        result = safety.run_case(world, rng, number)
        assert result is not None
        if result.nara_pick is None:
            assert result.safe_in_ward == 0 and result.safe_in_other_ward == 0
            continue
        target = frozenset({safety.ICU_SKILL}) if result.needs_icu_skill else frozenset()
        dropped = by_id[result.dropped_staff_id]
        shift = shifts[result.shift_id]
        dropped.shifts.remove(shift)
        try:
            assert safety.judge(by_id[result.nara_pick], shift, target).passed
        finally:
            dropped.shifts.append(shift)
        # The other ward is used only when the ward has nobody safe
        assert result.nara_from_other_ward == (result.safe_in_ward == 0)


def test_the_baselines_pick_only_from_what_the_paper_roster_shows() -> None:
    rng = random.Random(5)
    world = safety.build_world(rng)
    by_id = {nurse.staff_id: nurse for nurse in world.nurses}
    shifts = {shift.slot.shift_id: shift.slot for shift in world.shifts}
    for number in range(40):
        result = safety.run_case(world, rng, number)
        assert result is not None
        dropped = by_id[result.dropped_staff_id]
        shift = shifts[result.shift_id]
        for name in safety.BASELINES:
            pick = result.baseline[name][0]
            if pick is None:
                continue
            nurse = by_id[pick]
            assert nurse.ward_id == dropped.ward_id and nurse is not dropped
            assert safety._free_on_paper(nurse, shift)


def test_wilson_interval_matches_the_formula() -> None:
    low, high = safety.wilson(712, 1000)
    # Checked by hand against the Wilson score formula: 0.6832 to 0.7392
    assert math.isclose(low, 0.6832, abs_tol=1e-4)
    assert math.isclose(high, 0.7392, abs_tol=1e-4)
    assert all(math.isnan(x) for x in safety.wilson(0, 0))
