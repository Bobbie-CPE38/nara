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


# 95% Wilson intervals from scipy.stats.binomtest(k, n).proportion_ci(method="wilson"),
# computed outside the app (scipy is not a dependency of the backend) and frozen here
SCIPY_WILSON = {
    (712, 1000): (0.6832, 0.7392),
    (242, 1000): (0.2165, 0.2695),
    (742, 1000): (0.7140, 0.7682),
    (953, 1000): (0.9381, 0.9645),
}


def test_wilson_interval_matches_scipy() -> None:
    for (successes, total), (low, high) in SCIPY_WILSON.items():
        ours = safety.wilson(successes, total)
        assert math.isclose(ours[0], low, abs_tol=1e-4), (successes, ours)
        assert math.isclose(ours[1], high, abs_tol=1e-4), (successes, ours)
    assert all(math.isnan(x) for x in safety.wilson(0, 0))


def test_nara_unsafe_picks_are_counted_and_the_unmodelled_rule_is_reported() -> None:
    results, summary = safety.run(80, seed=13, worlds=4)
    nara = summary["nara"]
    assert isinstance(nara, dict)
    assert nara["unsafe_picks"] == sum(1 for r in results if r.nara_broken_rules) == 0
    assert summary["rules_that_can_fail_here"] == 10
    assert summary["rules_not_modelled"] == ["SOURCE_WARD_MINIMUM_VIOLATION"]
