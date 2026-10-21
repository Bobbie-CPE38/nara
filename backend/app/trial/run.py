"""Command line of the model trial (round 6 PR B2, draft section 3.2).

    python -m app.trial.run generate --out <cases.json>
    python -m app.trial.run run --cases <cases.json> --out <results.jsonl> --run-id <id> \\
        --model nova-lite,global.amazon.nova-2-lite-v1:0,0.41,3.39 [--model ...]
    python -m app.trial.run report --cases <cases.json> --results <results.jsonl>

`run` calls the real model unless the provider is `fake` and --dry-run is given. Every call
goes through llm_gateway.call() as MODEL_TRIAL, so it is counted against this run's own cap
(cases x models x attempts) and written to llm_call_log. The results file holds the raw
sentences: it must live outside the repository.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import LLM_TRIAL_MAX_ATTEMPTS
from app.domain.enums import LlmRefusal
from app.services import explanation_service, llm_gateway, llm_service
from app.trial import cases as case_set
from app.trial import scoring

REPO_ROOT = Path(__file__).resolve().parents[3]
# Draft 3.2 step 6: the monthly 20 USD minus the Demo's full 30-day quota (16.32 USD)
DEFAULT_TRIAL_BUDGET_USD = Decimal("3.68")
# Draft 3.2: the cost cap of one plan. PR 0 fixes the number; pass it with --cost-cap-usd
DEFAULT_COST_CAP_PER_PLAN_USD = Decimal("0.01")


@dataclass(frozen=True)
class ModelSpec:
    name: str
    model_id: str
    input_price: Decimal
    output_price: Decimal


def parse_model(text: str) -> ModelSpec:
    """name,model_id,input USD per million tokens,output USD per million tokens"""
    parts = text.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("use name,model_id,input_price,output_price")
    name, model_id, input_price, output_price = parts
    return ModelSpec(name, model_id, Decimal(input_price), Decimal(output_price))


def ensure_outside_repo(path: Path) -> None:
    resolved = path.resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise SystemExit(f"{path} is inside the repository: raw results must stay outside it")


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
        rows.append(scoring.Attempt(**raw, cost_usd=None if cost is None else Decimal(cost)))
    return rows


def _append(path: Path, row: scoring.Attempt) -> None:
    data = asdict(row)
    data["cost_usd"] = None if row.cost_usd is None else str(row.cost_usd)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def run_trial(
    cases: list[case_set.Case],
    models: list[ModelSpec],
    run_id: str,
    out: Path,
    budget_usd: Decimal,
    dry_run: bool,
) -> int:
    from app.db.session import SessionLocal

    if dry_run and settings.llm_provider != "fake":
        raise SystemExit("--dry-run is only for LLM_PROVIDER=fake; this would call the real model")
    if not dry_run and settings.llm_provider != "bedrock":
        raise SystemExit("a real run needs LLM_PROVIDER=bedrock (or --dry-run with fake)")
    ensure_outside_repo(out)
    worst = worst_case_usd(cases, models)
    print(f"worst case {worst:.4f} USD for the whole run, budget {budget_usd} USD")
    if worst > budget_usd and not dry_run:
        raise SystemExit("the worst case is over the budget: lower the cases or models first")

    cap = len(cases) * len(models) * LLM_TRIAL_MAX_ATTEMPTS
    done = read_results(out)
    with SessionLocal() as db:
        run = llm_gateway.create_trial_run(db, run_id, cap)
        db.commit()
        print(f"trial run {run_id}: cap {run.cap}, used {run.used}")
        for model in models:
            settings.llm_model_id = model.model_id
            settings.llm_input_price_per_mtok_usd = model.input_price
            settings.llm_output_price_per_mtok_usd = model.output_price
            for case in cases:
                if not run_pair(db, case, model, run_id, out, done):
                    print("trial quota exhausted: stopping")
                    return 1
    return 0


def run_pair(
    db: Session,
    case: case_set.Case,
    model: ModelSpec,
    run_id: str,
    out: Path,
    done: list[scoring.Attempt],
) -> bool:
    """Run one case on one model until it ends or its attempts are used. False: stop the run.

    A pair whose last recorded attempt is a provider fault is run again, with the next
    attempt number, until LLM_TRIAL_MAX_ATTEMPTS.
    """
    past = [r for r in done if r.case_key == case.key and r.model == model.name]
    if past and past[-1].status not in scoring.UNJUDGED:
        return True
    request = explanation_service.llm_request(case.payload)
    for attempt in range(len(past) + 1, LLM_TRIAL_MAX_ATTEMPTS + 1):
        subject = llm_gateway.model_trial(
            trial_run_id=run_id,
            trial_case_key=f"{case.key}/{model.name}",
            prompt_version=explanation_service.PROMPT_VERSION,
            attempt=attempt,
            input_hash=case.input_hash,
        )
        result = llm_gateway.call(db, request, subject)
        if isinstance(result, LlmRefusal):
            row = scoring.Attempt(
                case.key, model.name, attempt, scoring.REFUSED, None, result.value,
                None, None, None, None,
            )  # fmt: skip
            _append(out, row)
            return result != LlmRefusal.QUOTA_EXHAUSTED
        row = scoring.Attempt(
            case.key, model.name, attempt, result.status.value, result.text, result.error_type,
            result.input_tokens, result.output_tokens, result.duration_ms,
            llm_service.estimate_cost(result),
        )  # fmt: skip
        _append(out, row)
        print(f"{case.key} {model.name} attempt {attempt}: {row.status}")
        if not llm_service.is_retryable(result.status):
            break
    return True


def report(cases: list[case_set.Case], results: Path, cost_cap: Decimal) -> int:
    payloads = {c.key: c.payload for c in cases}
    forbidden = {c.key: c.forbidden for c in cases}
    reports = scoring.judge(read_results(results), payloads, forbidden)
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
    run.add_argument("--dry-run", action="store_true")
    rep = sub.add_parser("report")
    rep.add_argument("--cases", type=Path, required=True)
    rep.add_argument("--results", type=Path, required=True)
    rep.add_argument("--cost-cap-usd", type=Decimal, default=DEFAULT_COST_CAP_PER_PLAN_USD)
    args = parser.parse_args(argv)

    if args.command == "generate":
        case_set.save_cases(case_set.generate_cases(), args.out)
        print(f"wrote {args.out}")
        return 0
    cases = case_set.load_cases(args.cases)
    if args.command == "run":
        return run_trial(cases, args.model, args.run_id, args.out, args.budget_usd, args.dry_run)
    return report(cases, args.results, args.cost_cap_usd)


if __name__ == "__main__":
    sys.exit(main())
