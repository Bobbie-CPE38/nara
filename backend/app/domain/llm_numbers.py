"""Every number in an LLM sentence must come from its payload (round 6 PR B1, 6.28).

The model may quote a number, never compute one. This holds for the rank in "อันดับ N"
too. Any Unicode digits are read (Thai ๐-๙ included), as are decimals and thousands
separators ("1,234"). A quoted decimal may be a payload value rounded to the places it
shows (0.33 for 0.333...); a whole number must match exactly, so 3 never stands for 2.6.
Signs are ignored: a dash in "อันดับ 1-3" is not a minus.

A number is read whole, and a form this checker cannot verify counts as unverified
rather than being read in pieces: ".5", "1e3", "5k", "1/2", "1,2", "1.2.3", and number
characters that are not digits ("½", "²", "Ⅻ").

A timestamp the sentence copies character for character from a payload string
("2026-10-22T23:00:00+07:00") is one value, not the numbers "22T23" and "23T07" glued by
the T. A timestamp written any other way is read like any other numbers, so a converted
time zone or a changed digit still fails.
"""

import re
import unicodedata
from collections.abc import Iterator, Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# \d matches every Unicode decimal digit, and Decimal() reads all of them. A token is
# everything glued to a digit that could change its value
_TOKEN = re.compile(r"[.,]?\d(?:[\d.,/]|[A-Za-z])*")
_WELL_FORMED = re.compile(r"\d+(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?")
# Payload values are trusted data, so their strings are only scanned for plain numbers
_PAYLOAD_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_ISO_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")


def _parse(raw: str) -> tuple[Decimal, int] | None:
    digits = raw.replace(",", "")
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    _, _, fraction = digits.partition(".")
    return value, len(fraction)


def _tokens(text: str) -> Iterator[tuple[str, tuple[Decimal, int] | None]]:
    """(token as written, (value, decimal places)), or None for a form not verifiable."""
    for match in _TOKEN.finditer(text):
        # A full stop or comma after a number ends the sentence or the list item
        raw = match.group().rstrip(".,")
        yield raw, _parse(raw) if _WELL_FORMED.fullmatch(raw) else None
    for char in text:
        if not char.isdecimal() and unicodedata.numeric(char, None) is not None:
            yield char, None


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
            for match in _PAYLOAD_NUMBER.finditer(value):
                parsed = _parse(match.group())
                if parsed is not None:
                    found.add(parsed[0])
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


def _payload_strings(payload: Any) -> set[str]:
    found: set[str] = set()
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, Mapping):
            stack.extend(value.values())
        elif isinstance(value, list | tuple):
            stack.extend(value)
    return found


def unverified_numbers(text: str, payload: Any) -> list[str]:
    """The numbers of `text`, as written, that the payload does not hold or that are in a
    form this checker cannot verify."""
    allowed = payload_numbers(payload)
    strings = _payload_strings(payload)
    # A timestamp copied whole from the payload is verified as a whole
    text = _ISO_TIMESTAMP.sub(lambda m: " " if m.group() in strings else m.group(), text)
    return [
        raw
        for raw, parsed in _tokens(text)
        if parsed is None or not _matches(parsed[0], parsed[1], allowed)
    ]
