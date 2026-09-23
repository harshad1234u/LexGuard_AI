"""Deterministic comparison of the values a legal claim turns on.

A quote can occur verbatim in the document and the claim built on it can still
be wrong: the source says thirty days, the model says sixty. Quote matching
alone will not catch that, so every value in a claim is extracted and must be
found in the evidence before the claim can be called verified
(docs/04_SECURITY_GROUNDING.md sec. 6).

Design rules:

* Conservative by default. Where equivalence cannot be established with
  confidence the answer is UNKNOWN, never "probably equal". An unresolved
  comparison downgrades a finding; it never promotes one.
* No unit conversion. "1 month" is not rewritten as "30 days" - the document's
  own unit is the one that matters, and month lengths differ.
* Exact arithmetic. Values are `Decimal`, so 50000 == 50000.00 and nothing is
  lost to float rounding.

All regexes here run against untrusted document and model text. They are kept
free of nested quantifiers so no input can force catastrophic backtracking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum, auto

from app.verification.text import collapse_for_numbers


class NumericKind(StrEnum):
    INTEGER = "integer"
    DECIMAL = "decimal"
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    DURATION = "duration"


class Comparison(StrEnum):
    """Outcome of comparing claimed values against source values."""

    MATCH = auto()
    MISMATCH = auto()
    UNKNOWN = auto()
    """Could not be established either way - downgrades, never promotes."""


# --- Currency ---------------------------------------------------------------

_CURRENCY_CODES = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "rupees": "INR",
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}

# Number body: digits with optional grouping and decimals. Grouping is captured
# as written - "5,00,000" and "50,000" must not collapse into each other.
_NUMBER_BODY = r"\d[\d,]*(?:\.\d+)?"

#: Continental grouping: dots separate thousands and a comma opens the
#: decimals, as European and Latin-American drafting writes an amount.
#:
#: Read as an Anglo-American number, "€1.400.000,00" is not a near miss - it is
#: a different figure by three orders of magnitude. `_NUMBER_BODY` matched only
#: its leading "€1.400", so Phase 14 measured a claim of "€1.400" being
#: released as supported against a document reading "€1.400.000,00", with the
#: residue "000,00" scanned separately as a bare 0.
#:
#: Unambiguous by construction, which is why it can be read at all: groups are
#: exactly three digits and there is at least one of them, a shape US grouping
#: never produces (it uses commas there, and its decimals are not three digits
#: preceded by a dot). The lookarounds keep it from biting a chunk out of a
#: longer Anglo-American number such as "1,400,000.000".
#:
#: Forms that remain genuinely ambiguous - a bare "€1.400", which is either
#: one thousand four hundred or one and four tenths - are deliberately NOT
#: read here. They stay with `_NUMBER_BODY`, and a claim restating them in the
#: other convention fails to match and is withheld.
#: The trailing guard is `(?!\.\d)` rather than `(?![\d.])`: a figure that ends
#: a sentence is followed by a dot, and rejecting that made the regex backtrack
#: and give up its decimals, so "€1.400.000,01." was read as €1.400.000 and
#: compared equal to €1.400.000,00 - a cent difference silently discarded.
_CONTINENTAL_BODY = r"(?<![\d,.])\d{1,3}(?:\.\d{3})+(?:,\d+)?(?!\d)(?!\.\d)"

_CURRENCY_SYMBOLS = r"₹|us\$|\$|€|£|rs\.?|inr|usd|eur|gbp"

_CURRENCY_PREFIX_CONTINENTAL = re.compile(
    r"(" + _CURRENCY_SYMBOLS + r")\s*(" + _CONTINENTAL_BODY + r")",
    re.IGNORECASE,
)
_CURRENCY_SUFFIX_CONTINENTAL = re.compile(
    r"(" + _CONTINENTAL_BODY + r")\s*(inr|usd|eur|gbp|rupees)\b",
    re.IGNORECASE,
)
_CONTINENTAL_NUMBER = re.compile(_CONTINENTAL_BODY)

_CURRENCY_PREFIX = re.compile(
    r"(" + _CURRENCY_SYMBOLS + r")\s*(" + _NUMBER_BODY + r")",
    re.IGNORECASE,
)
_CURRENCY_SUFFIX = re.compile(
    r"(" + _NUMBER_BODY + r")\s*(inr|usd|eur|gbp|rupees)\b",
    re.IGNORECASE,
)
_PERCENTAGE = re.compile(
    # The word boundary applies only to the spelled-out forms. "%" is not a word
    # character, so a trailing \b there would reject "10% per annum".
    r"(" + _NUMBER_BODY + r")\s*(?:%|(?:per\s?cent(?:um)?|percent)\b)",
    re.IGNORECASE,
)

_DURATION_UNITS = {
    "day": "day",
    "days": "day",
    "week": "week",
    "weeks": "week",
    "month": "month",
    "months": "month",
    "year": "year",
    "years": "year",
    "hour": "hour",
    "hours": "hour",
}
_DURATION = re.compile(
    r"(" + _NUMBER_BODY + r")\s*(?:business\s+|working\s+|calendar\s+)?"
    r"(days?|weeks?|months?|years?|hours?)\b",
    re.IGNORECASE,
)

#: Cardinals written as words. Legal drafting usually gives both forms
#: ("sixty (60) days"), where the digits are what this module reads, but not
#: always: the EU Standard Contractual Clauses say "within one month of
#: suspension" with no figure anywhere. Until Phase 13 a claim restating that
#: as "six months" changed the deadline sixfold and no value was in dispute as
#: far as the verifier could tell.
#:
#: Deliberately limited to durations. A bare spelled-out number elsewhere in a
#: sentence ("one of the parties") is not a quantity, and reading it as one
#: would manufacture mismatches out of ordinary prose.
#:
#: Phase 14 extended this to the teens and to hyphenated compounds. The gap was
#: measured, not guessed: against "within forty-five (45) days of receipt" the
#: faithful answer "within 45 days" was REJECTED, because "forty-five" was not
#: in this table, `_DURATION` cannot reach "days" across the "(45)", and an
#: INTEGER never supports a DURATION. Hyphenated cardinals are how commercial
#: drafting writes most periods - twenty-one days, forty-five days, ninety-nine
#: years - so the hole sat under a large share of real notice periods.
_CARDINAL_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_CARDINAL_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_CARDINAL_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_CARDINAL_WORDS = {
    **_CARDINAL_UNITS,
    **_CARDINAL_TEENS,
    **_CARDINAL_TENS,
    # "twenty-one" ... "ninety-nine", in both the hyphenated and the spaced
    # form drafters use interchangeably.
    **{
        f"{tens_word}{separator}{unit_word}": tens + unit
        for tens_word, tens in _CARDINAL_TENS.items()
        for unit_word, unit in _CARDINAL_UNITS.items()
        for separator in ("-", " ")
    },
}
#: The parenthesised repeat - "sixty (60) days" - is how most commercial
#: drafting writes a period, and neither pattern read it before Phase 13:
#: `_DURATION` cannot get from "60" to "days" across the ")", so "60" fell
#: through to the bare-integer scan and an INTEGER never supports a DURATION.
#: The effect was a mismatch between "sixty (60) days" and "60 days", which is
#: the same deadline written two ways - a false positive waiting on any
#: faithful paraphrase of a real notice period.
#: Longest alternative first, so "forty-five" is preferred over "forty".
_CARDINAL_ALTERNATION = "|".join(sorted(_CARDINAL_WORDS, key=len, reverse=True))

#:
#: The parenthesised numeral is captured rather than skipped. Skipping it meant
#: it was never checked against anything: the span was consumed by this
#: pattern, so the bare-integer scan never saw it either, and "forty-five (46)
#: days" was read as 45 days and matched a document saying "forty-five (45)
#: days". Phase 14's mutation run found this on seven separate claims - it is
#: the most quietly dangerous kind of edit, because the numeral is what a
#: reader's eye goes to and the word is what the verifier was reading.
_WORD_DURATION = re.compile(
    r"\b(" + _CARDINAL_ALTERNATION + r")\s+"
    r"(?:\(\s*(\d[\d,]*)\s*\)\s*)?"
    r"(?:business\s+|working\s+|calendar\s+)?"
    r"(days?|weeks?|months?|years?|hours?)\b",
    re.IGNORECASE,
)

_PLAIN_NUMBER = re.compile(_NUMBER_BODY)


@dataclass(frozen=True)
class NumericToken:
    """One value found in text, with the unit that gives it meaning."""

    kind: NumericKind
    value: Decimal
    raw: str
    unit: str | None = None
    """Duration unit ("day", "month", ...), never converted."""
    currency: str | None = None

    def matches(self, other: NumericToken) -> bool:
        """Whether `other` (from the source) supports this claimed value."""
        if self.value != other.value:
            return False

        if self.kind is NumericKind.DURATION or other.kind is NumericKind.DURATION:
            # A duration is only supported by the same duration in the same unit.
            return (
                self.kind is other.kind
                and self.unit is not None
                and self.unit == other.unit
            )

        if self.kind is NumericKind.PERCENTAGE or other.kind is NumericKind.PERCENTAGE:
            # A bare "10" in the source does not establish "10%".
            return self.kind is other.kind

        if self.kind is NumericKind.CURRENCY and other.kind is NumericKind.CURRENCY:
            # Both currencies known and different -> different amounts of money.
            if self.currency and other.currency:
                return self.currency == other.currency
            return True

        # Plain integers and decimals compare on value alone, and a currency
        # amount may be supported by the same bare figure on the page.
        return True


def _to_decimal(raw: str) -> Decimal | None:
    """Parse a written number. Grouping commas are positional, not values."""
    try:
        return Decimal(raw.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _to_decimal_continental(raw: str) -> Decimal | None:
    """Parse "1.400.000,00": dots group, the comma opens the decimals."""
    try:
        return Decimal(raw.replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _spans_overlap(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    return any(span[0] < end and start < span[1] for start, end in taken)


def extract_numbers(text: str) -> list[NumericToken]:
    """Find every value in `text`, most specific interpretation first.

    Order matters: a figure already claimed as currency, a percentage or a
    duration must not also be counted as a bare integer, or "30 days" would
    yield both a duration and a stray 30 that any other 30 could satisfy.
    """
    if not text:
        return []

    source = collapse_for_numbers(text)
    tokens: list[NumericToken] = []
    taken: list[tuple[int, int]] = []

    # Dates first: the year in "1 January 2027" is not a quantity.
    for match in _iter_date_matches(source):
        taken.append(match.span())

    for pattern, builder in (
        # Continental grouping first. Its digits would otherwise be claimed by
        # the Anglo-American patterns, which read "1.400.000,00" as "1.400".
        (_CURRENCY_PREFIX_CONTINENTAL, _build_currency_prefix_continental),
        (_CURRENCY_SUFFIX_CONTINENTAL, _build_currency_suffix_continental),
        (_CONTINENTAL_NUMBER, _build_continental),
        (_CURRENCY_PREFIX, _build_currency_prefix),
        (_CURRENCY_SUFFIX, _build_currency_suffix),
        (_PERCENTAGE, _build_percentage),
        (_DURATION, _build_duration),
        (_WORD_DURATION, _build_word_duration),
    ):
        for match in pattern.finditer(source):
            if _spans_overlap(match.span(), taken):
                continue
            built = builder(match)
            if built is not None:
                # A builder may return more than one token: a spelled-out
                # duration whose parenthesised numeral disagrees with it is two
                # claimed values, not one, and both have to be accounted for.
                tokens.extend(built if isinstance(built, list) else [built])
                taken.append(match.span())

    for match in _PLAIN_NUMBER.finditer(source):
        if _spans_overlap(match.span(), taken):
            continue
        value = _to_decimal(match.group(0))
        if value is None:
            continue
        kind = NumericKind.DECIMAL if "." in match.group(0) else NumericKind.INTEGER
        tokens.append(NumericToken(kind=kind, value=value, raw=match.group(0)))
        taken.append(match.span())

    return tokens


def _build_currency_prefix_continental(match: re.Match[str]) -> NumericToken | None:
    value = _to_decimal_continental(match.group(2))
    if value is None:
        return None
    symbol = match.group(1).lower().rstrip(".")
    return NumericToken(
        kind=NumericKind.CURRENCY,
        value=value,
        raw=match.group(0),
        currency=_CURRENCY_CODES.get(symbol) or _CURRENCY_CODES.get(symbol + "."),
    )


def _build_currency_suffix_continental(match: re.Match[str]) -> NumericToken | None:
    value = _to_decimal_continental(match.group(1))
    if value is None:
        return None
    return NumericToken(
        kind=NumericKind.CURRENCY,
        value=value,
        raw=match.group(0),
        currency=_CURRENCY_CODES.get(match.group(2).lower()),
    )


def _build_continental(match: re.Match[str]) -> NumericToken | None:
    """A continentally grouped figure with no currency attached to it."""
    value = _to_decimal_continental(match.group(0))
    if value is None:
        return None
    kind = NumericKind.DECIMAL if "," in match.group(0) else NumericKind.INTEGER
    return NumericToken(kind=kind, value=value, raw=match.group(0))


def _build_currency_prefix(match: re.Match[str]) -> NumericToken | None:
    value = _to_decimal(match.group(2))
    if value is None:
        return None
    symbol = match.group(1).lower().rstrip(".")
    return NumericToken(
        kind=NumericKind.CURRENCY,
        value=value,
        raw=match.group(0),
        currency=_CURRENCY_CODES.get(symbol) or _CURRENCY_CODES.get(symbol + "."),
    )


def _build_currency_suffix(match: re.Match[str]) -> NumericToken | None:
    value = _to_decimal(match.group(1))
    if value is None:
        return None
    return NumericToken(
        kind=NumericKind.CURRENCY,
        value=value,
        raw=match.group(0),
        currency=_CURRENCY_CODES.get(match.group(2).lower()),
    )


def _build_percentage(match: re.Match[str]) -> NumericToken | None:
    value = _to_decimal(match.group(1))
    if value is None:
        return None
    return NumericToken(kind=NumericKind.PERCENTAGE, value=value, raw=match.group(0))


def _build_duration(match: re.Match[str]) -> NumericToken | None:
    value = _to_decimal(match.group(1))
    if value is None:
        return None
    return NumericToken(
        kind=NumericKind.DURATION,
        value=value,
        raw=match.group(0),
        unit=_DURATION_UNITS[match.group(2).lower()],
    )


def _build_word_duration(match: re.Match[str]) -> list[NumericToken] | None:
    """"one month" -> the same token "1 month" would produce.

    Runs after `_DURATION`, and the overlap check in `extract_numbers` means
    the digit form wins wherever a drafter gave both: "sixty (60) days" is read
    once, as 60 days, not twice.

    Where the two forms disagree - "forty-five (46) days" - both are returned.
    Returning only the word would let the numeral pass unchecked, and returning
    only the numeral would do the same to the word. Two tokens means the text
    is supported only by a source that contains both readings, which nothing
    sensible does, so a disagreement withholds rather than picks a winner.
    """
    unit = _DURATION_UNITS[match.group(3).lower()]
    word_value = Decimal(_CARDINAL_WORDS[match.group(1).lower()])
    tokens = [
        NumericToken(
            kind=NumericKind.DURATION, value=word_value, raw=match.group(0), unit=unit
        )
    ]

    numeral = match.group(2)
    if numeral is not None:
        numeral_value = _to_decimal(numeral)
        if numeral_value is not None and numeral_value != word_value:
            tokens.append(
                NumericToken(
                    kind=NumericKind.DURATION,
                    value=numeral_value,
                    raw=match.group(0),
                    unit=unit,
                )
            )
    return tokens


# --- Dates ------------------------------------------------------------------

_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_ALTERNATION = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
_DAY_MONTH_YEAR = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_ALTERNATION + r")\.?,?\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_DAY_YEAR = re.compile(
    r"\b(" + _MONTH_ALTERNATION + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.IGNORECASE,
)

_DATE_PATTERNS = (_ISO_DATE, _DAY_MONTH_YEAR, _MONTH_DAY_YEAR, _NUMERIC_DATE)


@dataclass(frozen=True)
class DateToken:
    """A date found in text.

    `resolved` is None when the written form has more than one reading - most
    often DD/MM versus MM/DD, or a two-digit year whose century is a guess. Such
    a date is never silently assigned a value.
    """

    raw: str
    resolved: date | None
    ambiguous: bool

    @property
    def is_resolved(self) -> bool:
        return self.resolved is not None and not self.ambiguous


def _iter_date_matches(text: str):
    seen: list[tuple[int, int]] = []
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            if _spans_overlap(match.span(), seen):
                continue
            seen.append(match.span())
            yield match


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_dates(text: str) -> list[DateToken]:
    """Find every date, marking any whose reading is not certain."""
    if not text:
        return []

    source = collapse_for_numbers(text)
    tokens: list[DateToken] = []

    for match in _iter_date_matches(source):
        raw = match.group(0)
        pattern_matched = match.re

        if pattern_matched is _ISO_DATE:
            resolved = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            tokens.append(DateToken(raw=raw, resolved=resolved, ambiguous=resolved is None))

        elif pattern_matched is _DAY_MONTH_YEAR:
            resolved = _safe_date(
                int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1))
            )
            tokens.append(DateToken(raw=raw, resolved=resolved, ambiguous=resolved is None))

        elif pattern_matched is _MONTH_DAY_YEAR:
            resolved = _safe_date(
                int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2))
            )
            tokens.append(DateToken(raw=raw, resolved=resolved, ambiguous=resolved is None))

        else:  # _NUMERIC_DATE
            tokens.append(_resolve_numeric_date(raw, match))

    return tokens


def _resolve_numeric_date(raw: str, match: re.Match[str]) -> DateToken:
    """Resolve d/m/y only when the written form admits a single reading."""
    first, second, year_text = int(match.group(1)), int(match.group(2)), match.group(3)

    if len(year_text) != 4:
        # "01/01/27" could be 1927 or 2027. Conventions exist; none of them are
        # facts about this document.
        return DateToken(raw=raw, resolved=None, ambiguous=True)

    year = int(year_text)

    if first == second:
        # Same under either reading.
        return DateToken(raw=raw, resolved=_safe_date(year, first, second), ambiguous=False)
    if first > 12 and second <= 12:
        return DateToken(raw=raw, resolved=_safe_date(year, second, first), ambiguous=False)
    if second > 12 and first <= 12:
        return DateToken(raw=raw, resolved=_safe_date(year, first, second), ambiguous=False)

    # Both <= 12 and different: DD/MM and MM/DD give different real dates.
    return DateToken(raw=raw, resolved=None, ambiguous=True)


# --- Comparison -------------------------------------------------------------


@dataclass
class ValueComparison:
    """Result of checking claimed values against source values."""

    result: Comparison
    unmatched: list[NumericToken]
    unresolved_dates: list[DateToken]
    mismatched_dates: list[DateToken]

    @property
    def has_currency_mismatch(self) -> bool:
        return any(t.kind is NumericKind.CURRENCY for t in self.unmatched)


def compare_numbers(claim_text: str, source_text: str) -> ValueComparison:
    """Check that every value asserted in `claim_text` occurs in `source_text`.

    Values present in the source but absent from the claim are ignored: a claim
    need not restate the whole document, it must only avoid asserting figures
    the document does not support.
    """
    claimed = extract_numbers(claim_text)
    available = extract_numbers(source_text)

    unmatched = [
        token for token in claimed if not any(token.matches(other) for other in available)
    ]

    claimed_dates = extract_dates(claim_text)
    source_dates = extract_dates(source_text)
    mismatched_dates: list[DateToken] = []
    unresolved_dates: list[DateToken] = []

    for claimed_date in claimed_dates:
        outcome = _compare_one_date(claimed_date, source_dates)
        if outcome is Comparison.MISMATCH:
            mismatched_dates.append(claimed_date)
        elif outcome is Comparison.UNKNOWN:
            unresolved_dates.append(claimed_date)

    if unmatched or mismatched_dates:
        result = Comparison.MISMATCH
    elif unresolved_dates:
        result = Comparison.UNKNOWN
    else:
        result = Comparison.MATCH

    return ValueComparison(
        result=result,
        unmatched=unmatched,
        unresolved_dates=unresolved_dates,
        mismatched_dates=mismatched_dates,
    )


def _compare_one_date(claimed: DateToken, source_dates: list[DateToken]) -> Comparison:
    """Compare one claimed date against the dates available in the source."""
    if not source_dates:
        # The claim asserts a date the source does not state at all.
        return Comparison.MISMATCH

    # An identical written form needs no interpretation.
    if any(claimed.raw == candidate.raw for candidate in source_dates):
        return Comparison.MATCH

    if not claimed.is_resolved:
        return Comparison.UNKNOWN

    resolved_sources = [c for c in source_dates if c.is_resolved]
    if any(claimed.resolved == candidate.resolved for candidate in resolved_sources):
        return Comparison.MATCH

    if len(resolved_sources) != len(source_dates):
        # Some source date could not be read; it might have been the match.
        return Comparison.UNKNOWN

    return Comparison.MISMATCH
