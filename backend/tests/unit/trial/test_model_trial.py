"""Model trial tools (round 6 PR B2): the case set, the four criteria and the run guards."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import LlmCallStatus
from app.services import llm_service
from app.trial import cases as case_set
from app.trial import run, scoring

CAP = Decimal("0.01")


def _attempt(case_key="case-01", model="m", attempt=1, status="SUCCEEDED", text="อันดับ 1", **kw):
    base = {
        "case_key": case_key,
        "model": model,
        "attempt": attempt,
        "status": status,
        "text": text,
        "error_type": None,
        "input_tokens": 1000,
        "output_tokens": 100,
        "duration_ms": 900,
        "cost_usd": Decimal("0.001"),
    }
    return scoring.Attempt(**(base | kw))


def _judge(attempts, forbidden=None):
    payload = {"candidates": [{"rank": 1}], "candidate_count": 1}
    keys = {a.case_key for a in attempts}
    return scoring.judge(attempts, {k: payload for k in keys}, {k: forbidden or [] for k in keys})


# --- the case set ------------------------------------------------------------------------


def test_case_set_is_30_cases_covering_every_shape():
    cases = case_set.generate_cases()
    assert len(cases) == case_set.CASE_COUNT
    assert {c.kind for c in cases} == set(case_set.KINDS)
    assert len({c.key for c in cases}) == len(cases)


def test_case_set_is_deterministic():
    first = case_set.generate_cases()
    second = case_set.generate_cases()
    assert [c.input_hash for c in first] == [c.input_hash for c in second]


def test_over_ten_cases_are_cut_to_ten_candidates():
    for case in (c for c in case_set.generate_cases() if c.kind == "over_ten"):
        assert case.payload["candidate_count"] > 10
        assert len(case.payload["candidates"]) == 10


def test_partial_cases_use_the_partial_plan_meaning():
    for case in case_set.generate_cases():
        partial = "breaks ties only" in case.payload["plan_penalty"]["meaning"]
        assert partial == (case.kind == "partial")


def test_ties_cases_have_equal_scores():
    for case in (c for c in case_set.generate_cases() if c.kind == "ties"):
        keys = [(c["total"], str(c["ranking_key"])) for c in case.payload["candidates"]]
        assert len(keys) != len(set(keys))


def test_payloads_hold_no_person_and_forbidden_strings_are_not_in_them():
    for case in case_set.generate_cases():
        text = str(case.payload)
        # "staff_id" is named once in ranking_key.order as the last tie-break, never as a value
        assert all("staff_id" not in c for c in case.payload["candidates"])
        assert not any(item in text for item in case.forbidden)


def test_saved_cases_round_trip_and_detect_edits(tmp_path: Path):
    path = tmp_path / "cases.json"
    cases = case_set.generate_cases()
    case_set.save_cases(cases, path)
    assert [c.input_hash for c in case_set.load_cases(path)] == [c.input_hash for c in cases]
    path.write_text(path.read_text(encoding="utf-8").replace('"gap": 1', '"gap": 9', 1), "utf-8")
    with pytest.raises(ValueError, match="input_hash"):
        case_set.load_cases(path)


# --- the four criteria -------------------------------------------------------------------


def test_a_clean_model_passes_all_four():
    report = _judge([_attempt()])["m"]
    assert report.eligible(CAP)


def test_unverified_number_fails_numbers_not_format():
    row = _attempt(status="INVALID_OUTPUT", text=None, error_type=llm_service.UNVERIFIED_NUMBER)
    report = _judge([row])["m"]
    assert report.number_failures == ["case-01"]
    assert not report.passes(CAP)["numbers"]
    assert report.format_failures == []


def test_invalid_output_without_number_error_fails_format():
    report = _judge([_attempt(status="INVALID_OUTPUT", text=None, error_type=None)])["m"]
    assert report.format_failures == ["case-01"]
    assert not report.passes(CAP)["format"]


def test_a_name_in_the_sentence_fails_identity():
    report = _judge([_attempt(text="อันดับ 1 คือ สมชาย ใจดี")], ["สมชาย ใจดี"])["m"]
    assert report.identity_failures == ["case-01"]


def test_a_line_id_shaped_string_fails_identity_even_if_unlisted():
    leak = "U" + "a" * 32
    report = _judge([_attempt(text=f"อันดับ 1 {leak}")])["m"]
    assert report.identity_failures == ["case-01"]


def test_a_number_outside_the_payload_fails_even_when_the_status_is_succeeded():
    report = _judge([_attempt(text="อันดับ 7")])["m"]
    assert report.number_failures == ["case-01"]


def test_provider_fault_means_not_judged_not_failed():
    row = _attempt(status="THROTTLED", text=None)
    report = _judge([row])["m"]
    assert report.incomplete == ["case-01"]
    assert report.format_failures == []
    assert not any(report.passes(CAP).values())


def test_a_retry_that_succeeds_judges_the_final_attempt_and_sums_the_cost():
    rows = [
        _attempt(attempt=1, status="TIMEOUT", text=None, cost_usd=Decimal("0.002")),
        _attempt(attempt=2, cost_usd=Decimal("0.003")),
    ]
    report = _judge(rows)["m"]
    assert report.eligible(CAP)
    assert report.retried_cases == 1
    assert report.mean_cost_usd == Decimal("0.005")


def test_cost_over_the_cap_or_unknown_fails_cost():
    expensive = _judge([_attempt(cost_usd=Decimal("0.02"))])["m"]
    assert not expensive.passes(CAP)["cost"]
    unknown = _judge([_attempt(cost_usd=None)])["m"]
    assert unknown.unknown_cost_cases == ["case-01"]
    assert not unknown.passes(CAP)["cost"]


def test_choose_takes_the_cheapest_passing_model_and_never_lowers_the_bar():
    rows = [
        _attempt(model="cheap", text="อันดับ 9"),  # number failure
        _attempt(model="mid", cost_usd=Decimal("0.004")),
        _attempt(model="dear", cost_usd=Decimal("0.009")),
    ]
    reports = _judge(rows)
    assert scoring.choose(reports, CAP) == "mid"
    assert scoring.choose({"cheap": reports["cheap"]}, CAP) is None


# --- run guards --------------------------------------------------------------------------


def test_results_inside_the_repo_are_refused():
    with pytest.raises(SystemExit):
        run.ensure_outside_repo(run.REPO_ROOT / "results.jsonl")
    run.ensure_outside_repo(Path.home() / "nara-trial" / "results.jsonl")


def test_model_spec_keeps_a_model_id_that_contains_a_colon():
    spec = run.parse_model("nova-lite,global.amazon.nova-2-lite-v1:0,0.41,3.39")
    assert spec.model_id == "global.amazon.nova-2-lite-v1:0"
    assert spec.output_price == Decimal("3.39")


def test_worst_case_of_the_planned_run_fits_the_trial_budget():
    cases = case_set.generate_cases()
    models = [run.parse_model("nova-lite,global.amazon.nova-2-lite-v1:0,0.41,3.39")] * 3
    assert run.worst_case_usd(cases, models) < run.DEFAULT_TRIAL_BUDGET_USD


def test_real_run_needs_bedrock_and_dry_run_needs_fake(monkeypatch, tmp_path: Path):
    cases = case_set.generate_cases()[:1]
    models = [run.parse_model("a,b,1,1")]
    monkeypatch.setattr(run.settings, "llm_provider", "fake")
    with pytest.raises(SystemExit, match="bedrock"):
        run.run_trial(cases, models, "r", tmp_path / "o.jsonl", Decimal(1), dry_run=False)
    monkeypatch.setattr(run.settings, "llm_provider", "bedrock")
    with pytest.raises(SystemExit, match="fake"):
        run.run_trial(cases, models, "r", tmp_path / "o.jsonl", Decimal(1), dry_run=True)


def test_status_values_the_scorer_reads_exist():
    names = {s.value for s in LlmCallStatus}
    assert scoring.UNJUDGED - {scoring.REFUSED} <= names
