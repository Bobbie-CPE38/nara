"""Every number in an LLM sentence must come from its payload (round 6 PR B1, 6.28).

The model may quote a number, never compute one. This holds for the rank in "อันดับ N"
too. Any Unicode digits are read (Thai ๐-๙ included), as are decimals and thousands
separators ("1,234"). A quoted decimal may be a payload value rounded to the places it
shows (0.33 for 0.333...); a whole number must match exactly, so 3 never stands for 2.6.
Signs are ignored: a dash in "อันดับ 1-3" is not a minus.
"""

import re
from collections.abc import Iterator, Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# \d matches every Unicode decimal digit, and Decimal() reads all of them
_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def _parse(raw: str) -> tuple[Decimal, int] | None:
    digits = raw.replace(",", "")
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    _, _, fraction = digits.partition(".")
    return value, len(fraction)


def _numbers_in(text: str) -> Iterator[tuple[str, Decimal, int]]:
    for match in _NUMBER.finditer(text):
        parsed = _parse(match.group())
        if parsed is not None:
            yield match.group(), parsed[0], parsed[1]


def payload_numbers(payload: Any) -> set[Decimal]:
    """Every number of the payload's values, numbers inside strings included. Keys are not
    read: they are field names."""
    found: set[Decimal] = set()
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float | Decimal):
            try:
                found.add(abs(Decimal(str(value))))
            except InvalidOperation:  # nan, inf
                continue
        elif isinstance(value, str):
            found.update(number for _, number, _ in _numbers_in(value))
        elif isinstance(value, Mapping):
            stack.extend(value.values())
        elif isinstance(value, list | tuple):
            stack.extend(value)
    return found


def _matches(value: Decimal, places: int, allowed: set[Decimal]) -> bool:
    if value in allowed:
        return True
    if places == 0:
        return False
    step = Decimal(1).scaleb(-places)
    return any(number.quantize(step, rounding=ROUND_HALF_UP) == value for number in allowed)


def unverified_numbers(text: str, payload: Any) -> list[str]:
    """The numbers of `text`, as written, that the payload does not hold."""
    allowed = payload_numbers(payload)
    return [raw for raw, value, places in _numbers_in(text) if not _matches(value, places, allowed)]
