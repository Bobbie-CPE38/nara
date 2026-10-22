"""Model trial tools (round 6 PR B2): the case set, the four criteria and the run guards."""

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.constants import LLM_TRIAL_MAX_ATTEMPTS
from app.domain.enums import LlmCallStatus
from app.services import explanation_service, llm_service
from app.trial import cases as case_set
from app.trial import manifest as manifest_mod
from app.trial import run, scoring

CAP = Decimal("0.01")
NOVA = "nova-lite,global.amazon.nova-2-lite-v1:0,0.41,3.39"


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
        "run_id": "r1",
        "provider": "bedrock",
        "prompt_version": explanation_service.PROMPT_VERSION,
        "input_hash": "h-" + case_key,
        "model_id": "id-" + model,
    }
    return scoring.Attempt(**(base | kw))


def _judge(attempts, forbidden=None, models=("m",), case_keys=None):
    """Judge against the case keys given, or else the cases that have a row."""
    payload = {"candidates": [{"rank": 1}], "candidate_count": 1}
    keys = case_keys or sorted({a.case_key for a in attempts})
    return scoring.judge(
        attempts, {k: payload for k in keys}, {k: forbidden or [] for k in keys}, models
    )


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
    reports = _judge(rows, models=("cheap", "mid", "dear"))
    assert scoring.choose(reports, CAP) == "mid"
    assert scoring.choose({"cheap": reports["cheap"]}, CAP) is None


# --- a model is judged against every expected case (PR B2 review, P2 1) --------------------


def test_29_of_30_cases_absent_leaves_the_model_incomplete_and_not_chosen():
    keys = [f"case-{n:02d}" for n in range(1, 31)]
    reports = _judge([_attempt()], case_keys=keys)
    report = reports["m"]
    assert report.cases == 30
    assert report.incomplete == keys[1:]
    assert not any(report.passes(CAP).values())
    assert scoring.choose(reports, CAP) is None


def test_a_model_with_no_rows_at_all_is_incomplete_not_missing():
    reports = _judge([_attempt(model="a")], models=("a", "b"))
    assert reports["b"].incomplete == ["case-01"]
    assert scoring.choose(reports, CAP) == "a"


def test_a_row_for_an_unexpected_model_or_case_is_an_error():
    with pytest.raises(ValueError, match="unexpected"):
        _judge([_attempt(model="x")])
    with pytest.raises(ValueError, match="unexpected"):
        _judge([_attempt(case_key="case-99")], case_keys=["case-01"])


# --- the manifest binds results to the experiment (PR B2 review, P2 2) ---------------------


def _manifest(**changes):
    hashes = {"case-01": "h-case-01"}
    base = {
        "run_id": "r1",
        "provider": "bedrock",
        "prompt_version": explanation_service.PROMPT_VERSION,
        "hashes": hashes,
        "models": [run.parse_model("m,id-m,0.41,3.39")],
        "max_attempts": LLM_TRIAL_MAX_ATTEMPTS,
        "cost_cap_usd": run.DEFAULT_COST_CAP_PER_PLAN_USD,
        "budget_usd": run.DEFAULT_TRIAL_BUDGET_USD,
    }
    return manifest_mod.build(**(base | changes)), hashes


def test_matching_rows_pass_the_manifest_check():
    manifest, hashes = _manifest()
    manifest_mod.check_rows([_attempt()], manifest, hashes)


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "r2"},
        {"provider": "fake"},
        {"prompt_version": "rank-explanation-v99"},
        {"input_hash": "another-payload"},
        {"model_id": "a-different-model"},
    ],
)
def test_a_row_from_another_experiment_is_refused(change):
    manifest, hashes = _manifest()
    with pytest.raises(manifest_mod.ManifestMismatch):
        manifest_mod.check_rows([_attempt(**change)], manifest, hashes)


def test_resume_refuses_results_without_a_manifest(tmp_path: Path):
    out = tmp_path / "results.jsonl"
    out.write_text('{"old": "row"}\n', encoding="utf-8")
    manifest, hashes = _manifest()
    with pytest.raises(SystemExit, match="no manifest"):
        run.prepare_results(out, manifest, hashes)


def test_resume_refuses_a_manifest_of_another_experiment(tmp_path: Path):
    out = tmp_path / "results.jsonl"
    saved, hashes = _manifest()
    run.prepare_results(out, saved, hashes)
    for change in (
        {"run_id": "r2"},
        {"provider": "fake"},
        {"models": [run.parse_model("m,other-id,0.41,3.39")]},  # same name, another model
        {"models": [run.parse_model("m,id-m,9,9")]},  # same model, other prices
        {"hashes": {"case-01": "changed"}},
        {"prompt_version": "rank-explanation-v99"},
        {"cost_cap_usd": Decimal("1")},
    ):
        current, current_hashes = _manifest(**change)
        with pytest.raises(SystemExit, match="another experiment"):
            run.prepare_results(out, current, current_hashes)


def test_resume_accepts_the_same_experiment_and_returns_its_rows(tmp_path: Path):
    out = tmp_path / "results.jsonl"
    manifest, hashes = _manifest()
    assert run.prepare_results(out, manifest, hashes) == []
    run._append(out, _attempt())
    assert [r.case_key for r in run.prepare_results(out, manifest, hashes)] == ["case-01"]


def test_resume_refuses_a_row_that_was_changed_after_the_manifest(tmp_path: Path):
    out = tmp_path / "results.jsonl"
    manifest, hashes = _manifest()
    run.prepare_results(out, manifest, hashes)
    run._append(out, _attempt(run_id="an-older-run"))
    with pytest.raises(SystemExit, match="does not match"):
        run.prepare_results(out, manifest, hashes)


def test_report_needs_the_manifest_and_the_same_cases(tmp_path: Path):
    cases = case_set.generate_cases()
    out = tmp_path / "results.jsonl"
    out.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="no manifest"):
        run.report(cases, out)
    manifest, _ = _manifest()  # one case only: not this cases file
    manifest_mod.save(out, manifest)
    with pytest.raises(SystemExit, match="cases file"):
        run.report(cases, out)


def test_report_reads_the_cost_cap_from_the_manifest_and_has_no_flag_for_it():
    with pytest.raises(SystemExit):
        run.main(["report", "--cases", "c", "--results", "r", "--cost-cap-usd", "1"])


def test_a_dry_run_report_says_it_is_fake(tmp_path: Path, capsys):
    cases = case_set.generate_cases()[:2]
    hashes = {c.key: c.input_hash for c in cases}
    out = tmp_path / "results.jsonl"
    manifest = manifest_mod.build(
        run_id="d1",
        provider="fake",
        prompt_version=explanation_service.PROMPT_VERSION,
        hashes=hashes,
        models=[run.parse_model("m,id-m,1,1")],
        max_attempts=LLM_TRIAL_MAX_ATTEMPTS,
        cost_cap_usd=run.DEFAULT_COST_CAP_PER_PLAN_USD,
        budget_usd=run.DEFAULT_TRIAL_BUDGET_USD,
    )
    manifest_mod.save(out, manifest)
    run.report(cases, out)
    shown = capsys.readouterr().out
    assert "FAKE PROVIDER" in shown
    assert "incomplete" in shown  # no rows were written: nothing is judged


# --- the acceptance cost cap and the trial budget (PR B2 review, P2 3) ---------------------


def test_defaults_follow_the_agreed_prices_and_workflow_6_28():
    per_call = (Decimal(5000) * Decimal("0.41") + Decimal(1024) * Decimal("3.39")) / 1_000_000
    assert run.DEFAULT_COST_CAP_PER_PLAN_USD == per_call == Decimal("0.00552136")
    demo_month = per_call * 100 * 30
    assert Decimal(20) - demo_month == run.DEFAULT_TRIAL_BUDGET_USD == Decimal("3.43592")


def test_a_plan_costing_0_007_fails_the_default_cap():
    report = _judge([_attempt(cost_usd=Decimal("0.007"))])["m"]
    assert not report.passes(run.DEFAULT_COST_CAP_PER_PLAN_USD)["cost"]
    assert report.passes(Decimal("0.01"))["cost"]  # the old, looser default


# --- run guards --------------------------------------------------------------------------


def test_results_inside_the_code_or_repo_folder_are_refused(tmp_path: Path):
    code, repo = tmp_path / "repo" / "backend", tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    code.mkdir()
    roots = run.protected_roots(code)
    assert roots == [code, repo]
    for inside in (code / "r.jsonl", repo / "docs" / "r.jsonl", repo):
        with pytest.raises(SystemExit):
            run.ensure_outside_repo(inside, roots)
    run.ensure_outside_repo(tmp_path / "elsewhere" / "r.jsonl", roots)


def test_a_container_that_mounts_only_backend_still_accepts_paths_outside_it(tmp_path: Path):
    # /app holds the code and has no .git above it. The old parents[3] resolved to "/", which
    # is the ancestor of every absolute path, so every output path was refused
    code = tmp_path / "app"
    code.mkdir()
    roots = run.protected_roots(code)
    assert roots == [code]
    run.ensure_outside_repo(tmp_path / "tmp" / "out.jsonl", roots)
    with pytest.raises(SystemExit):
        run.ensure_outside_repo(code / "out.jsonl", roots)


def test_the_filesystem_root_is_never_protected():
    assert run.protected_roots(Path(Path.cwd().anchor)) == []
    run.ensure_outside_repo(Path.home() / "nara-trial" / "results.jsonl", [])


def test_the_real_code_folder_is_protected_and_home_is_not():
    assert run.CODE_ROOT.name == "backend" or run.CODE_ROOT.name == "app"
    assert run.CODE_ROOT in run.protected_roots()
    run.ensure_outside_repo(Path.home() / "nara-trial" / "results.jsonl")


def test_model_spec_keeps_a_model_id_that_contains_a_colon():
    spec = run.parse_model(NOVA)
    assert spec.model_id == "global.amazon.nova-2-lite-v1:0"
    assert spec.output_price == Decimal("3.39")


def test_worst_case_of_the_planned_run_fits_the_trial_budget():
    cases = case_set.generate_cases()
    models = [run.parse_model(NOVA)] * 3
    assert run.worst_case_usd(cases, models) < run.DEFAULT_TRIAL_BUDGET_USD


def test_real_run_needs_bedrock_and_dry_run_needs_fake(monkeypatch, tmp_path: Path):
    cases = case_set.generate_cases()[:1]
    models = [run.parse_model("a,b,1,1")]
    args = (cases, models, "r", tmp_path / "o.jsonl", Decimal(1), CAP)
    monkeypatch.setattr(run.settings, "llm_provider", "fake")
    with pytest.raises(SystemExit, match="bedrock"):
        run.run_trial(*args, dry_run=False)
    monkeypatch.setattr(run.settings, "llm_provider", "bedrock")
    with pytest.raises(SystemExit, match="fake"):
        run.run_trial(*args, dry_run=True)


def test_status_values_the_scorer_reads_exist():
    names = {s.value for s in LlmCallStatus}
    assert scoring.UNJUDGED - {scoring.REFUSED} <= names


def test_attempt_rows_carry_the_fields_the_manifest_checks():
    fields = {f.name for f in dataclasses.fields(scoring.Attempt)}
    assert {"run_id", "provider", "prompt_version", "input_hash", "model_id"} <= fields
