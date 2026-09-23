"""Phase 14 workstream F: defined terms and cross-references.

The question here is not whether the system can resolve a reference - it
cannot, by design, and says so - but whether it knows the difference between
"the document says this" and "the document points somewhere I cannot see".

What is supported, what is refused, and what is still open is set out in
`PHASE_14_REPORT.md` sec. 8. Each row of that section has a test below.
"""

from __future__ import annotations

from app.schemas.findings import Evidence, ModelAnswer
from app.schemas.qa import AnswerStatus
from app.verification.qa import gate_answer, verify_answer
from app.verification.semantics import conflicting_definitions, defines_a_contested_term


class Document:
    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


def ask(pages: dict[int, str], answer: str, quote: str, page: int = 1):
    document = Document(pages)
    proposal = ModelAnswer(answer=answer, evidence=[Evidence(page=page, quote=quote)])
    return gate_answer(
        document_id="doc_definitions",
        question="What does this mean?",
        answer=proposal,
        verified=verify_answer(proposal, document),
        document=document,
    )


class TestPointerDefinitions:
    """A clause that points at a definition does not state one."""

    PAGE = '2.1 "Confidential Information" has the meaning given in Schedule 2 of this Agreement.'

    def test_asserting_the_content_of_a_pointer_is_refused(self):
        response = ask(
            {1: self.PAGE},
            "Confidential Information includes source code and customer lists.",
            '"Confidential Information" has the meaning given in Schedule 2',
        )
        assert response.status is AnswerStatus.NOT_FOUND
        assert "source code" not in response.answer

    def test_reporting_that_a_definition_exists_elsewhere_is_allowed(self):
        response = ask(
            {1: self.PAGE},
            "Confidential Information has the meaning given in Schedule 2 of this Agreement.",
            '"Confidential Information" has the meaning given in Schedule 2 of this Agreement.',
        )
        assert response.status is not AnswerStatus.NOT_FOUND


class TestCrossReferences:
    PAGE = "5.2 The Supplier shall comply with the Specifications set forth in Exhibit A."

    def test_a_reference_replaced_by_a_universal_is_refused(self):
        """"the Specifications in Exhibit A" is not "every requirement"."""
        response = ask(
            {1: self.PAGE},
            "The Supplier shall comply with every requirement of the Customer.",
            "comply with the Specifications set forth in Exhibit A",
        )
        assert response.status is AnswerStatus.NOT_FOUND

    def test_a_reference_carried_across_is_released(self):
        response = ask(
            {1: self.PAGE},
            "The Supplier shall comply with the Specifications set forth in Exhibit A.",
            "comply with the Specifications set forth in Exhibit A",
        )
        assert response.status is AnswerStatus.SUPPORTED

    def test_a_wrong_section_number_is_refused(self):
        page = "7.4 Termination for convenience is governed by Section 12.3 of this Agreement."
        response = ask(
            {1: page},
            "Termination for convenience is governed by Section 9.1 of this Agreement.",
            "Termination for convenience is governed by Section 12.3",
        )
        assert response.status is AnswerStatus.NOT_FOUND

    def test_the_content_of_a_missing_section_is_not_invented(self):
        page = "9.1 The Contractor shall observe the site rules set out in Annex 4."
        response = ask(
            {1: page},
            "Annex 4 requires hard hats and high-visibility clothing at all times.",
            "observe the site rules set out in Annex 4",
        )
        assert response.status is AnswerStatus.NOT_FOUND
        assert "hard hats" not in response.answer


class TestUndefinedSubstitution:
    def test_a_defined_term_swapped_for_an_undefined_one_is_refused(self):
        page = "4.1 The Provider shall deliver the Covered Services during the Term."
        response = ask(
            {1: page},
            "The Provider shall deliver all medical treatment during the Term.",
            "shall deliver the Covered Services during the Term",
        )
        assert response.status is AnswerStatus.NOT_FOUND

    def test_a_capitalised_term_is_not_read_as_the_ordinary_word(self):
        page = "3.3 The Services shall be performed with reasonable skill and care."
        response = ask(
            {1: page},
            "All services provided by any party shall be performed with reasonable skill and care.",
            "shall be performed with reasonable skill and care",
        )
        assert response.status is AnswerStatus.NOT_FOUND


class TestConflictingDefinitions:
    """Closed in Phase 14; recorded as undetected in Phase 13.

    Where a document defines one term twice and differently, an answer quoting
    either definition is right about its clause and wrong about the agreement,
    and every evidence check passes.
    """

    PAGES = {
        1: '1.1 "Business Day" means a day other than a Saturday or Sunday.',
        2: '14.2 "Business Day" means any day on which the Bank is open for business in Mumbai.',
    }

    def test_the_conflict_is_detected_across_pages(self):
        text = "\n".join(self.PAGES.values())
        assert "business day" in conflicting_definitions(text)

    def test_neither_definition_is_released_as_the_answer(self):
        response = ask(
            self.PAGES,
            "A Business Day is a day other than a Saturday or Sunday.",
            '"Business Day" means a day other than a Saturday or Sunday',
        )
        assert response.status is AnswerStatus.NOT_FOUND

    def test_the_other_definition_is_refused_too(self):
        response = ask(
            self.PAGES,
            "A Business Day is any day on which the Bank is open for business in Mumbai.",
            '"Business Day" means any day on which the Bank is open for business in Mumbai',
            page=2,
        )
        assert response.status is AnswerStatus.NOT_FOUND

    def test_a_single_definition_is_not_treated_as_contested(self):
        assert conflicting_definitions(self.PAGES[1]) == set()

    def test_a_definition_repeated_identically_is_not_a_conflict(self):
        text = (
            '1.1 "Business Day" means a day other than a Saturday or Sunday. '
            '20.4 "Business Day" means a day other than a Saturday or Sunday.'
        )
        assert conflicting_definitions(text) == set()

    def test_an_ordinary_clause_using_the_term_is_still_answerable(self):
        """Only evidence that *defines* the contested term is refused.

        A duty owed "within five Business Days" is a duty on either reading;
        refusing it as well would make one inconsistent definition swallow
        every clause that mentions the term.
        """
        pages = {
            **self.PAGES,
            3: "7.2 The Supplier shall issue an invoice within five Business Days of delivery.",
        }
        response = ask(
            pages,
            "The Supplier shall issue an invoice within five Business Days of delivery.",
            "The Supplier shall issue an invoice within five Business Days of delivery.",
            page=3,
        )
        assert response.status is AnswerStatus.SUPPORTED

    def test_the_conflict_check_does_not_decide_which_definition_governs(self):
        """Construction is legal reasoning. The system detects and declines."""
        contested = conflicting_definitions("\n".join(self.PAGES.values()))
        assert defines_a_contested_term(self.PAGES[1], contested)
        assert defines_a_contested_term(self.PAGES[2], contested)


class TestTypographicQuotesAreStillQuotes:
    """Phase 21B: the defect that made the check above ASCII-only.

    `_DEFINITION` delimits a defined term with a straight `"`. The detector ran
    its pattern against raw extracted text, so a contract exported from a word
    processor - which carries typographic quotes, and which is the ordinary
    case rather than an exotic one - produced no matches at all. Not a wrong
    verdict: no definitions found, therefore no conflicts, therefore no
    evidence refused. The failure was silent, which is what makes it worth a
    class of its own rather than a line in an existing one.

    Fixed by normalising the input before scanning it - the step every other
    comparison in the module already takes.
    """

    #: The same two conflicting definitions as `TestConflictingDefinitions`,
    #: written the way a word processor writes them.
    CURLY = {
        1: "1.1 “Business Day” means a day other than a Saturday or Sunday.",
        2: (
            "14.2 “Business Day” means any day on which the Bank is open "
            "for business in Mumbai."
        ),
    }

    def test_a_curly_quoted_conflict_is_detected(self):
        assert "business day" in conflicting_definitions(
            "\n".join(self.CURLY.values())
        )

    def test_a_straight_quoted_conflict_is_still_detected(self):
        """The fix must not trade one delimiter for the other."""
        text = (
            '1.1 "Business Day" means a day other than a Saturday or Sunday.\n'
            '14.2 "Business Day" means any day on which the Bank is open for '
            "business in Mumbai."
        )
        assert "business day" in conflicting_definitions(text)

    def test_quote_styles_mixed_across_clauses_still_conflict(self):
        """One clause typed, one pasted - the commonest real shape of this."""
        text = (
            '1.1 "Business Day" means a day other than a Saturday or Sunday.\n'
            "14.2 “Business Day” means any day on which the Bank is open "
            "for business in Mumbai."
        )
        assert "business day" in conflicting_definitions(text)

    def test_low_and_high_typographic_quotes_are_delimiters_too(self):
        """„ and ” are the same character to a reader, and now to this."""
        text = (
            "1.1 „Business Day” means a day other than a Saturday or Sunday.\n"
            "14.2 „Business Day” means any day on which the Bank is open "
            "for business in Mumbai."
        )
        assert "business day" in conflicting_definitions(text)

    def test_agreeing_curly_definitions_are_not_a_conflict(self):
        """The fix widens what is *seen*, never what is *flagged*."""
        text = (
            "1.1 “Business Day” means a day other than a Saturday or Sunday.\n"
            "20.4 “Business Day” means a day other than a Saturday or Sunday."
        )
        assert conflicting_definitions(text) == set()

    def test_a_single_curly_definition_is_not_contested(self):
        assert conflicting_definitions(self.CURLY[1]) == set()

    def test_prose_without_definitions_flags_nothing_in_either_style(self):
        for opener, closer in (('"', '"'), ("“", "”")):
            text = (
                "The Supplier shall issue an invoice within five Business Days.\n"
                f"Payment of {opener}the Fee{closer} is due within 15 days."
            )
            assert conflicting_definitions(text) == set()

    def test_a_curly_quoted_conflict_refuses_the_evidence_end_to_end(self):
        """The detector feeds the Q&A gate, so the fix must reach the answer.

        Without it this question was answered from one of two contradictory
        definitions, carrying a quote that verifies perfectly - the exact
        failure the Phase 14 check exists to prevent, reopened by nothing more
        than an input format.
        """
        response = ask(
            self.CURLY,
            "A Business Day is a day other than a Saturday or Sunday.",
            "“Business Day” means a day other than a Saturday or Sunday",
        )
        assert response.status is AnswerStatus.NOT_FOUND

    def test_an_ordinary_curly_quoted_clause_is_still_answerable(self):
        """Widening detection must not start swallowing ordinary clauses."""
        pages = {
            **self.CURLY,
            3: (
                "7.2 The Supplier shall issue an invoice within five Business "
                "Days of delivery."
            ),
        }
        response = ask(
            pages,
            "The Supplier shall issue an invoice within five Business Days of delivery.",
            "The Supplier shall issue an invoice within five Business Days of delivery.",
            page=3,
        )
        assert response.status is AnswerStatus.SUPPORTED
