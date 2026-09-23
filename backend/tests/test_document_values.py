"""Phase 17 - the deterministic value index.

Two properties are worth more than the rest and are asserted explicitly:

1. **No model is involved.** The index must work when the provider does not.
2. **No document prose is returned.** The response carries a value, a kind and
   a page. A surrounding sentence would turn an extraction surface into a
   claim surface, which is exactly what this feature exists not to be.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.documents.values import index_page, index_values
from app.schemas.documents import ValueKind
from tests.conftest import make_pdf, make_pdf_with_blank_pages


class FakeDocument:
    """The duck type `index_values` takes: page_count + page_text."""

    def __init__(self, pages: dict[int, str | None]):
        self.page_count = max(pages) if pages else 0
        self._pages = pages

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


def kinds_and_values(items) -> set[tuple[str, str]]:
    return {(str(item.kind), item.value) for item in items}


class TestExtraction:
    def test_currency_is_indexed_as_the_document_writes_it(self):
        found = index_page("The fee is Rs 50,000 per month.", 1)
        assert ("currency", "Rs 50,000") in kinds_and_values(found)

    def test_indian_grouping_is_indexed(self):
        found = index_page("Liability shall not exceed Rs 6,00,000 in aggregate.", 3)
        assert ("currency", "Rs 6,00,000") in kinds_and_values(found)

    def test_percentage_is_indexed(self):
        found = index_page("Interest accrues at 1.5% per month.", 2)
        assert ("percentage", "1.5%") in kinds_and_values(found)

    def test_durations_are_indexed(self):
        found = index_page("Terminate on 30 days notice within 12 months.", 2)
        values = kinds_and_values(found)
        assert ("duration", "30 days") in values
        assert ("duration", "12 months") in values

    def test_date_is_indexed_and_not_reformatted(self):
        found = index_page("This Agreement begins on 1 April 2026.", 1)
        assert ("date", "1 April 2026") in kinds_and_values(found)

    def test_original_casing_is_preserved(self):
        """The extractors scan casefolded text; the index must not misquote."""
        found = index_page("A fee of Rs 50,000 applies.", 1)
        assert all(item.value != "rs 50,000" for item in found)

    def test_a_value_split_across_a_line_break_is_still_one_value(self):
        found = index_page("a fee of Rs\n50,000 per month", 1)
        assert ("currency", "Rs 50,000") in kinds_and_values(found)

    def test_bare_numbers_are_not_indexed(self):
        """An unqualified figure carries no unit and would only be noise."""
        found = index_page("See clause 7 and paragraph 3 of Schedule A.", 1)
        assert found == []

    def test_multiple_values_on_one_page(self):
        found = index_page(
            "Pay Rs 50,000 within 15 days; interest 1.5%; notice 30 days.", 2
        )
        assert len(found) >= 4
        assert all(item.page == 2 for item in found)

    def test_a_repeated_value_is_listed_once_per_page(self):
        found = index_page("30 days notice. A further 30 days applies.", 2)
        assert [item.value for item in found].count("30 days") == 1

    def test_the_same_value_on_two_pages_is_kept_twice(self):
        """Two facts about two places. Collapsing them would hide one."""
        values = index_values(
            FakeDocument({1: "Notice of 30 days.", 2: "Also 30 days here."})
        )
        pages = sorted(item.page for item in values if item.value == "30 days")
        assert pages == [1, 2]

    def test_an_empty_page_yields_nothing(self):
        assert index_page("", 1) == []
        assert index_page("   \n  ", 1) == []

    def test_an_uncaptured_page_yields_nothing(self):
        assert index_values(FakeDocument({1: None, 2: "Rs 50,000"})) != []
        assert all(item.page == 2 for item in index_values(FakeDocument({1: None, 2: "Rs 50,000"})))

    def test_ordering_is_stable(self):
        text = "Rs 50,000 and 30 days and 1.5% and 1 April 2026."
        assert [i.kind for i in index_page(text, 1)] == [
            i.kind for i in index_page(text, 1)
        ]


class TestAmbiguousDates:
    def test_an_ambiguous_date_is_flagged_and_not_resolved(self):
        found = [i for i in index_page("Dated 04/05/2026.", 1) if i.kind is ValueKind.DATE]
        assert found, "the date was not detected at all"
        assert found[0].ambiguous is True
        assert found[0].value == "04/05/2026"

    def test_an_unambiguous_date_is_not_flagged(self):
        found = [i for i in index_page("Dated 1 April 2026.", 1) if i.kind is ValueKind.DATE]
        assert found and found[0].ambiguous is False


class TestValuesEndpoint:
    def test_a_processed_document_returns_its_values(self, client: TestClient):
        pdf = make_pdf(pages=2, text="The fee is Rs 50,000 payable within 15 days.")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        response = client.get(f"/api/v1/documents/{doc}/values")
        assert response.status_code == 200

        body = response.json()
        assert body["document_id"] == doc
        assert body["coverage_status"] == "complete"
        assert body["values"], "no values were indexed"
        assert {"currency", "duration"} <= {v["kind"] for v in body["values"]}

    def test_every_value_is_bound_to_a_real_page(self, client: TestClient):
        pdf = make_pdf(pages=3, text="Pay Rs 50,000 within 15 days.")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        values = client.get(f"/api/v1/documents/{doc}/values").json()["values"]
        assert values
        assert all(1 <= v["page"] <= 3 for v in values)

    def test_a_document_with_no_supported_values_returns_an_empty_list(
        self, client: TestClient
    ):
        """Not an error. The document was read; it simply carried no values."""
        pdf = make_pdf(pages=1, text="This agreement is governed by the laws of India.")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        response = client.get(f"/api/v1/documents/{doc}/values")
        assert response.status_code == 200
        assert response.json()["values"] == []

    def test_an_unextracted_document_is_refused(self, client: TestClient):
        pdf = make_pdf(pages=1, text="Rs 50,000")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]

        response = client.get(f"/api/v1/documents/{doc}/values")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "coverage_incomplete"

    def test_an_unknown_document_is_404(self, client: TestClient):
        assert client.get("/api/v1/documents/doc_missing/values").status_code == 404

    def test_a_discarded_document_is_404(self, client: TestClient):
        pdf = make_pdf(pages=1, text="Rs 50,000")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")
        client.delete(f"/api/v1/documents/{doc}")

        assert client.get(f"/api/v1/documents/{doc}/values").status_code == 404


class TestSafety:
    """The properties that make this an extraction surface, not a claim surface."""

    def test_no_surrounding_prose_is_returned(self, client: TestClient):
        sentence = "The Client shall pay the Service Provider a fee of Rs 50,000 per month."
        pdf = make_pdf(pages=1, text=sentence)
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        body = client.get(f"/api/v1/documents/{doc}/values").text
        for phrase in ("shall pay", "Service Provider", "The Client", "per month"):
            assert phrase not in body, f"document prose leaked: {phrase!r}"

    def test_a_value_carries_only_its_own_fields(self, client: TestClient):
        pdf = make_pdf(pages=1, text="A fee of Rs 50,000 applies.")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        for value in client.get(f"/api/v1/documents/{doc}/values").json()["values"]:
            assert set(value) == {"kind", "value", "page", "ambiguous"}

    def test_the_index_never_calls_a_model(self, client: TestClient, monkeypatch):
        """The feature must work when the provider is unavailable or absent.

        `get_model_provider` is replaced with something that fails loudly, so a
        model call anywhere on this path breaks the test rather than costing
        money.
        """
        import app.models as models

        def explode():  # pragma: no cover - only runs if the property breaks
            raise AssertionError("the value index must not call a model provider")

        monkeypatch.setattr(models, "get_model_provider", explode)

        pdf = make_pdf(pages=1, text="Pay Rs 50,000 within 15 days.")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        assert client.get(f"/api/v1/documents/{doc}/values").status_code == 200

    def test_document_text_is_not_trusted_as_markup(self, client: TestClient):
        """Extracted values are untrusted content; nothing may be interpreted."""
        pdf = make_pdf(pages=1, text="Pay Rs 50,000 <script>alert(1)</script> now.")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        body = client.get(f"/api/v1/documents/{doc}/values").json()
        assert all("<script>" not in v["value"] for v in body["values"])


class TestDemoContract:
    """The Phase 16 demo contract, indexed from its actual content.

    Nothing is hard-coded: the PDF is built from the committed generator's own
    clause text, so a change to that document changes this test's input.
    """

    @pytest.fixture
    def demo_pages(self) -> dict[int, str]:
        # Loaded by path rather than imported: `demo/` sits beside `backend/`
        # and is not on the test root's import path. Loading it here keeps the
        # dependency visible and changes no configuration.
        import importlib.util
        from pathlib import Path

        generator = Path(__file__).resolve().parents[2] / "demo" / "make_demo_contract.py"
        if not generator.exists():  # pragma: no cover - present in this repository
            pytest.skip("demo contract generator is not present")

        spec = importlib.util.spec_from_file_location("demo_contract_source", generator)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        PAGES = module.PAGES

        return {
            number: "\n".join(
                line.removeprefix("@title:") for line in lines if line
            )
            for number, lines in enumerate(PAGES, 1)
        }

    def test_the_known_values_are_extracted_from_the_document_text(self, demo_pages):
        found = {
            (item.page, item.value.casefold())
            for item in index_values(FakeDocument(demo_pages))
        }

        for page, value in (
            (1, "12 months"),
            (1, "60 days"),
            (1, "1 april 2026"),
            (2, "rs 50,000"),
            (2, "1.5%"),
            (2, "15 days"),
            (2, "30 days"),
            (3, "rs 6,00,000"),
            (3, "3 years"),
        ):
            assert (page, value) in found, f"{value!r} was not indexed on page {page}"


class TestExtractionState:
    """Telling "read it, found nothing" apart from "could not read it".

    Both produce `values: []`, and until Phase 18 both produced the same
    sentence in the UI. Only one of them means the document states no amounts;
    the other means the application never searched it. Reporting the second as
    the first is a false negative dressed as a finding, which is the failure
    this project exists to prevent, so the response has to carry enough for a
    reader to be told which happened.
    """

    def _values_for(self, client: TestClient, pdf: bytes) -> dict:
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")
        response = client.get(f"/api/v1/documents/{doc}/values")
        assert response.status_code == 200
        return response.json()

    def test_text_that_was_read_is_reported_as_read(self, client: TestClient):
        body = self._values_for(
            client, make_pdf(pages=2, text="This agreement is governed by the laws of India.")
        )

        assert body["values"] == []
        assert body["extraction"]["characters"] > 0
        assert body["extraction"]["pages_with_text"] == 2
        assert body["extraction"]["pages_total"] == 2

    def test_a_document_with_no_text_is_distinguishable_from_one_without_values(
        self, client: TestClient
    ):
        """The case the empty-state wording turns on.

        A PDF whose pages carry neither text nor images is `complete` - there
        is nothing unread, because there was nothing there - so coverage alone
        cannot separate it from a contract that simply states no amounts.
        """
        empty = self._values_for(client, make_pdf_with_blank_pages(total=2, blank={1, 2}))
        read = self._values_for(client, make_pdf(pages=2, text="Governed by the laws of India."))

        assert empty["coverage_status"] == read["coverage_status"] == "complete"
        assert empty["values"] == read["values"] == []

        # Identical coverage, identical values, different extraction - which is
        # the whole point of the field.
        assert empty["extraction"]["characters"] == 0
        assert empty["extraction"]["pages_with_text"] == 0
        assert read["extraction"]["characters"] > 0

    def test_counts_match_the_manifest(self, client: TestClient):
        """The two must never disagree; one document, one set of facts."""
        pdf = make_pdf(pages=3, text="Pay Rs 50,000 within 15 days.")
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("c.pdf", pdf, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        manifest = client.get(f"/api/v1/documents/{doc}/manifest").json()
        extraction = client.get(f"/api/v1/documents/{doc}/values").json()["extraction"]

        assert extraction["characters"] == sum(p["text_length"] for p in manifest["pages"])
        assert extraction["pages_with_text"] == sum(
            1 for p in manifest["pages"] if p["text_length"] > 0
        )
        assert extraction["pages_total"] == len(manifest["pages"])

    def test_extraction_counts_carry_no_document_text(self, client: TestClient):
        """Counts only. A length is safe to report; a sample is not."""
        pdf = make_pdf(pages=1, text="The Client shall pay Rs 50,000 to the Service Provider.")
        extraction = self._values_for(client, pdf)["extraction"]

        assert set(extraction) == {"characters", "pages_with_text", "pages_total"}
        assert all(isinstance(v, int) for v in extraction.values())


class TestBlankFormRegression:
    """The document from the Phase 18 report: a real, digital, text-bearing PDF
    that legitimately indexes to nothing.

    It is an Indian government model-draft *format* - a template whose monetary
    fields are unfilled dotted placeholders ("Sale Consideration : Rs………"). It
    has a full text layer on every page, so coverage is complete and correct,
    and it states no amounts, so the index is empty and correct. The two
    together produced a user report that looked like an extraction bug and was
    not one.

    The fixture reproduces the shape rather than shipping the original PDF.
    """

    @pytest.fixture
    def blank_form(self) -> bytes:
        import fitz

        clauses = [
            "7. (i) Sale Consideration :  Rs………………………(Rupees …………..only)",
            "   (ii) Advance Amount :  Rs…………………....(Rupees…………...only)",
            "8. Stamp Duty paid Rs.…………………………………………………",
            "9. Market Value of the property:  Rs……………………………………",
            "   Age  : …………..years    Date of execution : ……/……/………",
        ]
        document = fitz.open()
        try:
            for index in range(5):
                page = document.new_page()
                page.insert_text((60, 60), f"FORMAT - model draft. Page {index + 1}")
                for offset, line in enumerate(clauses):
                    page.insert_text((60, 90 + offset * 18), line, fontsize=9)
            return document.tobytes()
        finally:
            document.close()

    def test_the_form_extracts_text_on_every_page(self, client: TestClient, blank_form: bytes):
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("form.pdf", blank_form, "application/pdf")},
        ).json()["document_id"]
        manifest = client.post(f"/api/v1/documents/{doc}/extract").json()["manifest"]

        assert [p["status"] for p in manifest["pages"]] == ["processed"] * 5
        assert all(p["text_length"] > 0 for p in manifest["pages"])
        assert all(p["image_count"] == 0 for p in manifest["pages"])

    def test_unfilled_placeholders_yield_no_values(self, client: TestClient, blank_form: bytes):
        """`Rs………` is a field, not an amount. Inventing one would be worse."""
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("form.pdf", blank_form, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        body = client.get(f"/api/v1/documents/{doc}/values").json()
        assert body["coverage_status"] == "complete"
        assert body["values"] == []

    def test_the_empty_result_is_reported_as_read_not_unreadable(
        self, client: TestClient, blank_form: bytes
    ):
        """The regression proper.

        This document must never be described to a user as possibly scanned.
        Its text was read in full; it simply contains no values.
        """
        doc = client.post(
            "/api/v1/documents/upload",
            files={"file": ("form.pdf", blank_form, "application/pdf")},
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{doc}/extract")

        extraction = client.get(f"/api/v1/documents/{doc}/values").json()["extraction"]
        assert extraction["characters"] > 0, "a text PDF must not look unreadable"
        assert extraction["pages_with_text"] == 5
