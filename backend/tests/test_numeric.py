"""Phase 5: numeric, currency, duration and date comparison.

Pure functions over strings - no PDF, no model, no I/O.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.verification.numeric import (
    Comparison,
    NumericKind,
    compare_numbers,
    extract_dates,
    extract_numbers,
)


def kinds(text: str) -> list[NumericKind]:
    return [t.kind for t in extract_numbers(text)]


def values(text: str) -> list[Decimal]:
    return [t.value for t in extract_numbers(text)]


class TestExtraction:
    def test_plain_integer(self):
        tokens = extract_numbers("There are 30 signatories.")
        assert [t.kind for t in tokens] == [NumericKind.INTEGER]
        assert tokens[0].value == Decimal(30)

    def test_decimal(self):
        assert values("a rate of 2.5 units") == [Decimal("2.5")]
        assert kinds("a rate of 2.5 units") == [NumericKind.DECIMAL]

    def test_thousands_separators_are_positional_not_values(self):
        """The whole point: grouping must not be normalised away."""
        assert values("Rs. 50,000") == [Decimal(50000)]
        assert values("Rs. 5,00,000") == [Decimal(500000)]
        assert values("Rs. 50,000") != values("Rs. 5,00,000")

    @pytest.mark.parametrize(
        "text,code",
        [
            ("₹50,000", "INR"),
            ("Rs. 50,000", "INR"),
            ("INR 50,000", "INR"),
            ("50,000 INR", "INR"),
            ("$50,000", "USD"),
            ("USD 50,000", "USD"),
            ("€50,000", "EUR"),
            ("£50,000", "GBP"),
        ],
    )
    def test_currency_forms_and_codes(self, text, code):
        tokens = extract_numbers(text)
        assert len(tokens) == 1
        assert tokens[0].kind is NumericKind.CURRENCY
        assert tokens[0].value == Decimal(50000)
        assert tokens[0].currency == code

    def test_percentage(self):
        tokens = extract_numbers("interest of 10% per annum")
        assert tokens[0].kind is NumericKind.PERCENTAGE
        assert tokens[0].value == Decimal(10)

    def test_percent_spelled_out(self):
        assert extract_numbers("10 percent")[0].kind is NumericKind.PERCENTAGE

    @pytest.mark.parametrize(
        "text,value,unit",
        [
            ("30 days", 30, "day"),
            ("30 business days", 30, "day"),
            ("12 months", 12, "month"),
            ("2 years", 2, "year"),
            ("6 weeks", 6, "week"),
        ],
    )
    def test_duration_keeps_its_unit(self, text, value, unit):
        token = extract_numbers(text)[0]
        assert token.kind is NumericKind.DURATION
        assert token.value == Decimal(value)
        assert token.unit == unit

    def test_duration_is_not_also_counted_as_a_bare_integer(self):
        """Otherwise any stray 30 elsewhere could satisfy '30 days'."""
        assert kinds("30 days") == [NumericKind.DURATION]

    def test_year_inside_a_date_is_not_a_quantity(self):
        assert extract_numbers("dated 1 January 2027") == []

    def test_empty_text(self):
        assert extract_numbers("") == []


class TestNumericComparison:
    def test_same_integer_matches(self):
        assert compare_numbers("30 signatories", "there are 30 signatories").result is Comparison.MATCH

    def test_different_integer_mismatches(self):
        assert compare_numbers("60 signatories", "there are 30 signatories").result is Comparison.MISMATCH

    def test_same_duration_matches(self):
        assert compare_numbers("30 days notice", "30 days' written notice").result is Comparison.MATCH

    def test_different_duration_mismatches(self):
        """The canonical failure from docs/04_SECURITY_GROUNDING.md sec. 6."""
        assert compare_numbers("60 days notice", "30 days' written notice").result is Comparison.MISMATCH

    def test_same_value_different_unit_mismatches(self):
        """Units are never converted: 1 month is not 30 days."""
        assert compare_numbers("1 month notice", "1 year notice").result is Comparison.MISMATCH

    def test_duration_not_satisfied_by_a_bare_number(self):
        assert compare_numbers("30 days", "clause 30 of the agreement").result is Comparison.MISMATCH

    def test_same_currency_matches(self):
        assert compare_numbers("a fee of ₹50,000", "the fee is Rs. 50,000").result is Comparison.MATCH

    def test_different_currency_amount_mismatches(self):
        assert compare_numbers("a fee of ₹5,00,000", "the fee is ₹50,000").result is Comparison.MISMATCH

    def test_same_amount_different_currency_mismatches(self):
        assert compare_numbers("a fee of $50,000", "the fee is ₹50,000").result is Comparison.MISMATCH

    def test_currency_mismatch_is_flagged_as_such(self):
        comparison = compare_numbers("a fee of ₹5,00,000", "the fee is ₹50,000")
        assert comparison.has_currency_mismatch is True

    def test_same_percentage_matches(self):
        assert compare_numbers("10% interest", "interest of 10% per annum").result is Comparison.MATCH

    def test_different_percentage_mismatches(self):
        assert compare_numbers("15% interest", "interest of 10% per annum").result is Comparison.MISMATCH

    def test_percentage_not_satisfied_by_a_bare_number(self):
        assert compare_numbers("10% interest", "clause 10 applies").result is Comparison.MISMATCH

    def test_decimal_precision_is_exact(self):
        assert compare_numbers("50000.00", "50,000").result is Comparison.MATCH
        assert compare_numbers("50000.01", "50,000").result is Comparison.MISMATCH

    def test_claim_without_numbers_is_vacuously_matched(self):
        assert compare_numbers("The agreement may be terminated.", "30 days").result is Comparison.MATCH

    def test_source_may_contain_numbers_the_claim_omits(self):
        """A claim need not restate the whole document."""
        assert compare_numbers("30 days notice", "30 days' notice under clause 14, page 37").result is Comparison.MATCH

    def test_unmatched_token_is_reported(self):
        comparison = compare_numbers("60 days", "30 days")
        assert [t.raw for t in comparison.unmatched] == ["60 days"]


class TestDateExtraction:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1 January 2027", date(2027, 1, 1)),
            ("1st January 2027", date(2027, 1, 1)),
            ("1 Jan 2027", date(2027, 1, 1)),
            ("January 1, 2027", date(2027, 1, 1)),
            ("Jan 1st, 2027", date(2027, 1, 1)),
            ("2027-01-01", date(2027, 1, 1)),
            ("01/01/2027", date(2027, 1, 1)),
            ("15/03/2027", date(2027, 3, 15)),
            ("03/15/2027", date(2027, 3, 15)),
        ],
    )
    def test_unambiguous_forms_resolve(self, text, expected):
        tokens = extract_dates(text)
        assert len(tokens) == 1
        assert tokens[0].resolved == expected
        assert tokens[0].is_resolved is True

    def test_day_month_ambiguity_is_not_guessed(self):
        """03/04/2027 is two different real dates depending on convention."""
        token = extract_dates("03/04/2027")[0]
        assert token.ambiguous is True
        assert token.resolved is None

    def test_two_digit_year_is_ambiguous(self):
        token = extract_dates("01/01/27")[0]
        assert token.ambiguous is True

    def test_impossible_date_does_not_resolve(self):
        assert extract_dates("2027-02-30")[0].is_resolved is False

    def test_no_dates(self):
        assert extract_dates("no dates at all") == []


class TestDateComparison:
    def test_identical_dates_match(self):
        assert compare_numbers("due 1 January 2027", "payable on 1 January 2027").result is Comparison.MATCH

    def test_different_dates_mismatch(self):
        assert compare_numbers("due 1 January 2027", "payable on 1 February 2027").result is Comparison.MISMATCH

    def test_normalizable_formats_match(self):
        """Different notation, provably the same day."""
        assert compare_numbers("due 01/01/2027", "payable on 1 January 2027").result is Comparison.MATCH

    def test_iso_and_long_form_match(self):
        assert compare_numbers("due 2027-03-15", "payable on 15 March 2027").result is Comparison.MATCH

    def test_ambiguous_date_is_unknown_not_assumed_equal(self):
        """03/04/2027 could be the source's date - could is not good enough."""
        comparison = compare_numbers("due 03/04/2027", "payable on 3 April 2027")
        assert comparison.result is Comparison.UNKNOWN
        assert len(comparison.unresolved_dates) == 1

    def test_claimed_date_absent_from_source_mismatches(self):
        assert compare_numbers("due 1 January 2027", "no date here").result is Comparison.MISMATCH

    def test_unknown_never_outranks_a_mismatch(self):
        """A definite contradiction must not be softened by a separate uncertainty."""
        comparison = compare_numbers(
            "60 days, due 03/04/2027", "30 days, due 3 April 2027"
        )
        assert comparison.result is Comparison.MISMATCH
