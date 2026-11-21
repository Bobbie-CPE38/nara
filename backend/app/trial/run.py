"""Command line of the model trial (round 6 PR B2, draft section 3.2).

    python -m app.trial.run generate --out <cases.json>
    python -m app.trial.run run --cases <cases.json> --out <results.jsonl> --run-id <id> \\
        --model nova-lite,global.amazon.nova-2-lite-v1:0,0.41,3.39 [--model ...]
    python -m app.trial.run report --cases <cases.json> --results <results.jsonl>

`run` calls the real model unless the provider is `fake` and --dry-run is given. Every call
goes through llm_gateway.call() as MODEL_TRIAL, so it is counted against this run's own cap
(cases x models x attempts) and written to llm_call_log. The results file holds the raw
sentences: it must live outside the repository.

`run` writes a manifest next to the results file (run, cases, prompt, provider, model IDs and
prices, the cost cap). It resumes only a file whose manifest matches, and `report` judges
against that manifest, so the acceptance cost cap cannot be changed at report time.
"""

import argparse
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import LLM_TRIAL_MAX_ATTEMPTS
from app.domain.enums import LlmRefusal
from app.services import explanation_service, llm_gateway, llm_service
from app.trial import cases as case_set
from app.trial import manifest as manifest_mod
from app.trial import scoring
from app.trial.manifest import Manifest, ModelSpec

# The backend folder: /app in the container, which mounts only ./backend
CODE_ROOT = Path(__file__).resolve().parents[2]
# docs/workflow.md 6.28: Nova 2 Lite Standard in Singapore, 0.41 input and 3.39 output USD
# per million tokens, 5,000 input and 1,024 output tokens per call = 0.00552136 USD per call.
# The Demo's full quota is 100 calls x 30 days = 16.56408 USD, so the trial may spend the rest
# of the 20 USD month: 3.43592 USD. The cap of one plan is the cost of one such call.
DEFAULT_COST_CAP_PER_PLAN_USD = Decimal("0.00552136")
DEFAULT_TRIAL_BUDGET_USD = Decimal("3.43592")


def parse_model(text: str) -> ModelSpec:
    """name,model_id,input USD per million tokens,output USD per million tokens"""
    parts = text.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("use name,model_id,input_price,output_price")
    name, model_id, input_price, output_price = parts
    return ModelSpec(name, model_id, Decimal(input_price), Decimal(output_price))


def find_repo_root(start: Path) -> Path | None:
    """The folder with a .git above `start`, or None (the container has no .git)."""
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None


def protected_roots(code_root: Path = CODE_ROOT) -> list[Path]:
    """Folders raw results must stay out of: the backend folder and the repository around it.

    Neither is derived from a fixed folder depth, and the filesystem root is never one of
    them, so a container that mounts only ./backend still accepts a path like /tmp/out.jsonl.
    """
    roots = [code_root]
    repo = find_repo_root(code_root)
    if repo is not None:
        roots.append(repo)
    return [root for root in roots if root.parent != root]


def ensure_outside_repo(path: Path, roots: list[Path] | None = None) -> None:
    resolved = path.resolve()
    for root in protected_roots() if roots is None else roots:
        if resolved == root or root in resolved.parents:
            raise SystemExit(f"{path} is inside {root}: raw results must stay outside the repo")


def worst_case_usd(cases: list[case_set.Case], models: list[ModelSpec]) -> Decimal:
    """Every attempt of every pair, at the estimated prompt size and a full-length answer."""
    total = Decimal(0)
    max_output = settings.llm_max_output_tokens
    for case in cases:
        tokens = llm_gateway.estimate_input_tokens(explanation_service.llm_request(case.payload))
        for model in models:
            per_call = (
                Decimal(tokens) * model.input_price + Decimal(max_output) * model.output_price
            ) / Decimal(1_000_000)
            total += per_call * LLM_TRIAL_MAX_ATTEMPTS
    return total


def read_results(path: Path) -> list[scoring.Attempt]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        cost = raw.pop("cost_usd")
        try:
            rows.append(scoring.Attempt(**raw, cost_usd=None if cost is None else Decimal(cost)))
        except TypeError as error:
            raise SystemExit(f"{path} is in an older format and cannot be used: {error}") from error
    return rows


def _append(path: Path, row: scoring.Attempt) -> None:
    data = asdict(row)
    data["cost_usd"] = None if row.cost_usd is None else str(row.cost_usd)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def prepare_results(out: Path, current: Manifest, hashes: dict[str, str]) -> list[scoring.Attempt]:
    """Create or check the manifest of `out` and return the rows it already holds.

    A results file with no manifest, or a manifest or row from another experiment (other
    run, cases, prompt, provider, model ID or prices), is refused: resuming it would skip
    calls the current experiment has not made.
    """
    saved = manifest_mod.load(out)
    if saved is None:
        if out.exists() and out.stat().st_size > 0:
            raise SystemExit(f"{out} has results but no manifest: use a new --out file")
        manifest_mod.save(out, current)
        return []
    changed = manifest_mod.differences(saved, current)
    if changed:
        raise SystemExit(f"{out} belongs to another experiment (differs in: {', '.join(changed)})")
    rows = read_results(out)
    try:
        manifest_mod.check_rows(rows, current, hashes)
    except manifest_mod.ManifestMismatch as error:
        raise SystemExit(str(error)) from error
    return rows


def run_trial(
    cases: list[case_set.Case],
    models: list[ModelSpec],
    run_id: str,
    out: Path,
    budget_usd: Decimal,
    cost_cap_usd: Decimal,
    dry_run: bool,
) -> int:
    from app.db.session import SessionLocal

    if dry_run and settings.llm_provider != "fake":
        raise SystemExit("--dry-run is only for LLM_PROVIDER=fake; this would call the real model")
    if not dry_run and settings.llm_provider not in {"bedrock", "lambda"}:
        raise SystemExit("a real run needs LLM_PROVIDER=bedrock or lambda (or --dry-run with fake)")
    ensure_outside_repo(out)
    worst = worst_case_usd(cases, models)
    print(f"worst case {worst:.4f} USD for the whole run, budget {budget_usd} USD")
    if worst > budget_usd and not dry_run:
        raise SystemExit("the worst case is over the budget: lower the cases or models first")

    hashes = {c.key: c.input_hash for c in cases}
    current = manifest_mod.build(
        run_id=run_id,
        provider=settings.llm_provider,
        prompt_version=explanation_service.PROMPT_VERSION,
        hashes=hashes,
        models=models,
        max_attempts=LLM_TRIAL_MAX_ATTEMPTS,
        cost_cap_usd=cost_cap_usd,
        budget_usd=budget_usd,
    )
    done = prepare_results(out, current, hashes)

    cap = len(cases) * len(models) * LLM_TRIAL_MAX_ATTEMPTS
    with SessionLocal() as db:
        run = llm_gateway.create_trial_run(db, run_id, cap)
        db.commit()
        print(f"trial run {run_id}: cap {run.cap}, used {run.used}")
        for model in models:
            settings.llm_model_id = model.model_id
            settings.llm_input_price_per_mtok_usd = model.input_price
            settings.llm_output_price_per_mtok_usd = model.output_price
            for case in cases:
                if not run_pair(db, case, model, current, out, done):
                    print("trial quota exhausted: stopping")
                    return 1
    return 0


def _row(
    manifest: Manifest, case: case_set.Case, model: ModelSpec, attempt: int, **fields: Any
) -> scoring.Attempt:
    return scoring.Attempt(
        case_key=case.key,
        model=model.name,
        attempt=attempt,
        run_id=manifest.run_id,
        provider=manifest.provider,
        prompt_version=manifest.prompt_version,
        input_hash=case.input_hash,
        model_id=model.model_id,
        **fields,
    )


def run_pair(
    db: Session,
    case: case_set.Case,
    model: ModelSpec,
    manifest: Manifest,
    out: Path,
    done: list[scoring.Attempt],
) -> bool:
    """Run one case on one model until it ends or its attempts are used. False: stop the run.

    A pair whose last recorded attempt is a provider fault is run again, with the next
    attempt number, until LLM_TRIAL_MAX_ATTEMPTS. `done` has been checked against the manifest.
    """
    past = [r for r in done if r.case_key == case.key and r.model == model.name]
    if past and past[-1].status not in scoring.UNJUDGED:
        return True
    request = explanation_service.llm_request(case.payload)
    for attempt in range(len(past) + 1, LLM_TRIAL_MAX_ATTEMPTS + 1):
        subject = llm_gateway.model_trial(
            trial_run_id=manifest.run_id,
            trial_case_key=f"{case.key}/{model.name}",
            prompt_version=manifest.prompt_version,
            attempt=attempt,
            input_hash=case.input_hash,
        )
        result = llm_gateway.call(db, request, subject)
        if isinstance(result, LlmRefusal):
            refused = _row(
                manifest, case, model, attempt,
                status=scoring.REFUSED, text=None, error_type=result.value,
                input_tokens=None, output_tokens=None, duration_ms=None, cost_usd=None,
            )  # fmt: skip
            _append(out, refused)
            return result != LlmRefusal.QUOTA_EXHAUSTED
        if result.model_id is not None and result.model_id != model.model_id:
            # Through the Lambda proxy the model is the proxy's own: a different one would
            # put results under the wrong model in the manifest
            raise SystemExit(
                f"the provider called {result.model_id}, not {model.model_id}: "
                "give --model the proxy's model ID"
            )
        row = _row(
            manifest, case, model, attempt,
            status=result.status.value, text=result.text, error_type=result.error_type,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            duration_ms=result.duration_ms, cost_usd=llm_service.estimate_cost(result),
        )  # fmt: skip
        _append(out, row)
        print(f"{case.key} {model.name} attempt {attempt}: {row.status}")
        if not llm_service.is_retryable(result.status):
            break
    return True


def report(cases: list[case_set.Case], results: Path) -> int:
    saved = manifest_mod.load(results)
    if saved is None:
        raise SystemExit(f"{results} has no manifest: only a file written by `run` can be judged")
    hashes = {c.key: c.input_hash for c in cases}
    if saved.cases_digest != manifest_mod.cases_digest(hashes):
        raise SystemExit("the cases file is not the one this results file was run with")
    rows = read_results(results)
    try:
        manifest_mod.check_rows(rows, saved, hashes)
    except manifest_mod.ManifestMismatch as error:
        raise SystemExit(str(error)) from error

    cost_cap = Decimal(saved.cost_cap_usd)
    payloads = {c.key: c.payload for c in cases}
    forbidden = {c.key: c.forbidden for c in cases}
    names = [m["name"] for m in saved.models]
    reports = scoring.judge(rows, payloads, forbidden, names)
    if saved.provider == "fake":
        print("FAKE PROVIDER: this is a dry run, not a trial of any model")
    print(f"run {saved.run_id}, provider {saved.provider}, cost cap {cost_cap} USD per plan")
    for name, rep in sorted(reports.items()):
        verdict = rep.passes(cost_cap)
        mean = "unknown" if rep.mean_cost_usd is None else f"{rep.mean_cost_usd:.6f}"
        print(f"\n{name}: {rep.cases} cases, mean cost per plan {mean} USD")
        print("  " + ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in verdict.items()))
        for label, items in (
            ("incomplete (not judged)", rep.incomplete),
            ("format failures", rep.format_failures),
            ("number failures", rep.number_failures),
            ("identity leaks", rep.identity_failures),
            ("cost unknown", rep.unknown_cost_cases),
        ):
            if items:
                print(f"  {label}: {', '.join(items)}")
        timeout_ms = settings.llm_request_timeout_seconds * 1000
        print(
            f"  retried cases {rep.retried_cases}, slowest {rep.max_duration_ms} ms "
            f"(timeout {timeout_ms:.0f} ms)"
        )
    chosen = scoring.choose(reports, cost_cap)
    print(f"\nchosen: {chosen or 'none: do not lower the criteria; new prompt version or fake'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.trial.run")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--out", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--cases", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--model", type=parse_model, action="append", required=True)
    run.add_argument("--budget-usd", type=Decimal, default=DEFAULT_TRIAL_BUDGET_USD)
    run.add_argument("--cost-cap-usd", type=Decimal, default=DEFAULT_COST_CAP_PER_PLAN_USD)
    run.add_argument("--dry-run", action="store_true")
    rep = sub.add_parser("report")
    rep.add_argument("--cases", type=Path, required=True)
    rep.add_argument("--results", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "generate":
        case_set.save_cases(case_set.generate_cases(), args.out)
        print(f"wrote {args.out}")
        return 0
    cases = case_set.load_cases(args.cases)
    if args.command == "run":
        return run_trial(
            cases,
            args.model,
            args.run_id,
            args.out,
            args.budget_usd,
            args.cost_cap_usd,
            args.dry_run,
        )
    return report(cases, args.results)


if __name__ == "__main__":
    sys.exit(main())
