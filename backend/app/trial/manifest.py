"""The experiment manifest that sits next to a results file (round 6 PR B2).

A results file only means something for the experiment that wrote it: the run, the frozen
cases, the prompt, the provider and each model's real ID and prices. The manifest records
those. `run` refuses to resume, and `report` refuses to judge, a results file that has no
manifest or whose manifest or rows do not match the current experiment, so an old row can
never stand in for a call that has not been made, and fake results can never be mixed with
real ones.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.trial.scoring import Attempt


class ManifestMismatch(Exception):
    """The results file does not belong to this experiment."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    model_id: str
    input_price: Decimal
    output_price: Decimal


@dataclass(frozen=True)
class Manifest:
    run_id: str
    provider: str
    prompt_version: str
    cases_digest: str
    case_count: int
    max_attempts: int
    cost_cap_usd: str
    budget_usd: str
    models: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def cases_digest(hashes: dict[str, str]) -> str:
    """One digest of every case key with its input_hash."""
    text = json.dumps(sorted(hashes.items()), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def build(
    *,
    run_id: str,
    provider: str,
    prompt_version: str,
    hashes: dict[str, str],
    models: list[ModelSpec],
    max_attempts: int,
    cost_cap_usd: Decimal,
    budget_usd: Decimal,
) -> Manifest:
    return Manifest(
        run_id=run_id,
        provider=provider,
        prompt_version=prompt_version,
        cases_digest=cases_digest(hashes),
        case_count=len(hashes),
        max_attempts=max_attempts,
        cost_cap_usd=str(cost_cap_usd),
        budget_usd=str(budget_usd),
        models=sorted(
            (
                {
                    "name": m.name,
                    "model_id": m.model_id,
                    "input_price": str(m.input_price),
                    "output_price": str(m.output_price),
                }
                for m in models
            ),
            key=lambda m: m["name"],
        ),
    )


def path_for(results: Path) -> Path:
    return results.with_name(results.name + ".manifest.json")


def save(results: Path, manifest: Manifest) -> None:
    path_for(results).write_text(
        json.dumps(manifest.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
    )


def load(results: Path) -> Manifest | None:
    path = path_for(results)
    if not path.exists():
        return None
    return Manifest(**json.loads(path.read_text(encoding="utf-8")))


def differences(saved: Manifest, current: Manifest) -> list[str]:
    old, new = saved.as_dict(), current.as_dict()
    return [field for field in new if old.get(field) != new[field]]


def check_rows(rows: list[Attempt], manifest: Manifest, hashes: dict[str, str]) -> None:
    """Every row must come from this run, provider, prompt, case payload and model ID."""
    model_ids = {m["name"]: m["model_id"] for m in manifest.models}
    for number, row in enumerate(rows, start=1):
        problems = []
        if row.run_id != manifest.run_id:
            problems.append(f"run_id {row.run_id!r}")
        if row.provider != manifest.provider:
            problems.append(f"provider {row.provider!r}")
        if row.prompt_version != manifest.prompt_version:
            problems.append(f"prompt_version {row.prompt_version!r}")
        if hashes.get(row.case_key) != row.input_hash:
            problems.append(f"input_hash of {row.case_key}")
        if model_ids.get(row.model) != row.model_id:
            problems.append(f"model_id {row.model_id!r} for {row.model!r}")
        if problems:
            raise ManifestMismatch(f"result row {number} does not match: {', '.join(problems)}")
