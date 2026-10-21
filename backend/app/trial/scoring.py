"""Judge each model on the four criteria of draft section 3.2, all by code.

1. format   every case ended SUCCEEDED, none INVALID_OUTPUT for its shape
2. numbers  every number in a sentence is in the payload (no UNVERIFIED_NUMBER)
3. identity no name, staff code or LINE ID of a person in the case
4. cost     the mean cost of one plan is under the cap

A case that never got an answer, because it was not run yet or because of the provider
(timeout, throttle, service or configuration error), is "incomplete", not a failure of the
model: the model is not judged until the case is run again. Every model is judged against
the whole frozen case set. Latency and retries are measured but never decide.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.domain.enums import LlmCallStatus
from app.domain.llm_numbers import unverified_numbers
from app.services.llm_service import UNVERIFIED_NUMBER

_LINE_ID = re.compile(r"\bU[0-9a-f]{32}\b")
# Written by run.py when the gateway refused an attempt (quota, input too large, not configured)
REFUSED = "REFUSED"
# Outcomes that say nothing about the model: run the case again before judging
UNJUDGED = frozenset(
    {
        LlmCallStatus.TIMEOUT.value,
        LlmCallStatus.THROTTLED.value,
        LlmCallStatus.SERVICE_ERROR.value,
        LlmCallStatus.CONFIG_ERROR.value,
        LlmCallStatus.IN_FLIGHT.value,
        REFUSED,
    }
)


@dataclass(frozen=True)
class Attempt:
    """One row of the raw results file."""

    case_key: str
    model: str
    attempt: int
    status: str
    text: str | None
    error_type: str | None
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    cost_usd: Decimal | None
    # Which experiment wrote the row; manifest.check_rows() compares them (PR B2 review)
    run_id: str
    provider: str
    prompt_version: str
    input_hash: str
    model_id: str


@dataclass
class ModelReport:
    model: str
    cases: int = 0
    incomplete: list[str] = field(default_factory=list)
    format_failures: list[str] = field(default_factory=list)
    number_failures: list[str] = field(default_factory=list)
    identity_failures: list[str] = field(default_factory=list)
    unknown_cost_cases: list[str] = field(default_factory=list)
    mean_cost_usd: Decimal | None = None
    retried_cases: int = 0
    max_duration_ms: int | None = None

    def passes(self, cost_cap_usd: Decimal) -> dict[str, bool]:
        """Each criterion; all False-safe when the model is not fully judged."""
        judged = not self.incomplete
        return {
            "format": judged and not self.format_failures,
            "numbers": judged and not self.number_failures,
            "identity": judged and not self.identity_failures,
            "cost": (
                judged
                and not self.unknown_cost_cases
                and self.mean_cost_usd is not None
                and self.mean_cost_usd < cost_cap_usd
            ),
        }

    def eligible(self, cost_cap_usd: Decimal) -> bool:
        return all(self.passes(cost_cap_usd).values())


def identity_leaks(text: str, forbidden: list[str]) -> list[str]:
    """Which forbidden strings, or LINE-ID-shaped strings, the sentence contains."""
    leaks = [item for item in forbidden if item and item in text]
    leaks.extend(match.group() for match in _LINE_ID.finditer(text))
    return leaks


def judge(
    attempts: list[Attempt],
    payloads: dict[str, dict[str, Any]],
    forbidden: dict[str, list[str]],
    models: Sequence[str],
) -> dict[str, ModelReport]:
    """One report per expected model, judged against every expected case.

    `payloads` and `forbidden` are keyed by case key and hold the whole frozen case set. A
    case with no recorded attempt is incomplete, so an interrupted run cannot qualify a
    model. A row for a model or case that is not expected is an error, not ignored.
    """
    grouped: dict[tuple[str, str], list[Attempt]] = defaultdict(list)
    for attempt in attempts:
        if attempt.model not in models or attempt.case_key not in payloads:
            raise ValueError(f"unexpected result row: {attempt.model} / {attempt.case_key}")
        grouped[(attempt.model, attempt.case_key)].append(attempt)
    reports: dict[str, ModelReport] = {}
    costs: dict[str, list[Decimal]] = defaultdict(list)
    for model, case_key in ((m, k) for m in models for k in sorted(payloads)):
        report = reports.setdefault(model, ModelReport(model, cases=len(payloads)))
        rows = grouped.get((model, case_key))
        if not rows:
            report.incomplete.append(case_key)
            continue
        rows.sort(key=lambda row: row.attempt)
        if len(rows) > 1:
            report.retried_cases += 1
        durations = [row.duration_ms for row in rows if row.duration_ms is not None]
        if durations:
            report.max_duration_ms = max(durations + [report.max_duration_ms or 0])
        case_costs = [row.cost_usd for row in rows if row.cost_usd is not None]
        if len(case_costs) < len(rows):
            report.unknown_cost_cases.append(case_key)
        else:
            costs[model].append(sum(case_costs, Decimal(0)))
        final = rows[-1]
        if final.status == LlmCallStatus.SUCCEEDED.value and final.text is not None:
            if unverified_numbers(final.text, payloads[case_key]):
                report.number_failures.append(case_key)
            if identity_leaks(final.text, forbidden.get(case_key, [])):
                report.identity_failures.append(case_key)
        elif final.status == LlmCallStatus.INVALID_OUTPUT.value:
            if final.error_type == UNVERIFIED_NUMBER:
                report.number_failures.append(case_key)
            else:
                report.format_failures.append(case_key)
        elif final.status == LlmCallStatus.TRUNCATED.value:
            report.format_failures.append(case_key)
        elif final.status in UNJUDGED:
            report.incomplete.append(case_key)
        else:
            report.format_failures.append(case_key)
    for model, report in reports.items():
        if costs[model]:
            report.mean_cost_usd = sum(costs[model], Decimal(0)) / len(costs[model])
    return reports


def choose(reports: dict[str, ModelReport], cost_cap_usd: Decimal) -> str | None:
    """The cheapest model that passes all four. None means: do not lower the bar, write a
    new prompt version and run the whole set again, or stay on the fake provider."""
    eligible = [r for r in reports.values() if r.eligible(cost_cap_usd)]
    if not eligible:
        return None
    return min(eligible, key=lambda r: r.mean_cost_usd or Decimal(0)).model
