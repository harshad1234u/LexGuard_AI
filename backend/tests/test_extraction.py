"""Phase 3: page-level extraction and manifest construction.

Entirely deterministic and offline - no model is involved in deciding what was
extracted (docs/06_EVALUATION_PLAN.md, "API Usage Strategy").
"""

from __future__ import annotations

import pytest

from app.documents.extraction import (
    ExtractedPage,
    PageStatus,
    PyMuPDFTextExtractor,
    extract_pages,
)
from app.documents.ingestion import ingest_document
from app.documents.manifest import build_manifest
from app.documents.storage import document_store
from app.documents.validation import validate_upload
from tests.conftest import (
    make_pdf,
    make_pdf_with_blank_pages,
    make_pdf_with_image_only_page,
)


def store(content: bytes):
    validated = validate_upload(
        filename="contract.pdf", content_type="application/pdf", content=content
    )
    return document_store.create(validated, content)


class ExplodingExtractor:
    """Fails on chosen pages, to simulate a mid-document extraction failure."""

    name = "exploding"

    def __init__(self, fail_on: set[int]):
        self.fail_on = fail_on
        self._delegate = PyMuPDFTextExtractor()

    def extract(self, page, page_number: int) -> ExtractedPage:
        if page_number in self.fail_on:
            raise RuntimeError("simulated extraction failure")
        result = self._delegate.extract(page, page_number)
        result.extraction_method = self.name
        return result


class TestExtractPages:
    def test_single_page_pdf(self):
        record = store(make_pdf(pages=1))
        pages = extract_pages(record.source_path, expected_pages=1)

        assert len(pages) == 1
        assert pages[0].page_number == 1
        assert pages[0].status is PageStatus.PROCESSED
        assert pages[0].text_length > 0

    def test_multi_page_pdf_extracts_each_page_independently(self):
        record = store(make_pdf(pages=12))
        pages = extract_pages(record.source_path, expected_pages=12)

        assert [p.page_number for p in pages] == list(range(1, 13))
        assert all(p.status is PageStatus.PROCESSED for p in pages)
        # Each page carries its own text, not one blob repeated.
        assert "Page 7." in pages[6].text
        assert "Page 7." not in pages[0].text

    def test_fifty_page_pdf_is_fully_covered(self):
        record = store(make_pdf(pages=50))
        pages = extract_pages(record.source_path, expected_pages=50)

        assert len(pages) == 50
        assert sum(1 for p in pages if p.is_covered) == 50

    def test_blank_page_is_empty_not_failed(self):
        record = store(make_pdf_with_blank_pages(total=4, blank={3}))
        pages = extract_pages(record.source_path, expected_pages=4)

        assert pages[2].status is PageStatus.EMPTY
        assert pages[2].text_length == 0
        # A genuinely blank page had no content to miss, so it still counts.
        assert pages[2].is_covered is True

    def test_image_only_page_is_unreadable_not_empty(self):
        """A scanned page must not be mistaken for a blank one."""
        record = store(make_pdf_with_image_only_page(total=3, image_page=2))
        pages = extract_pages(record.source_path, expected_pages=3)

        assert pages[1].status is PageStatus.UNREADABLE
        assert pages[1].image_count > 0
        assert pages[1].is_covered is False

    def test_page_failure_is_recorded_without_aborting_the_document(self):
        record = store(make_pdf(pages=40))
        pages = extract_pages(
            record.source_path, expected_pages=40, extractor=ExplodingExtractor({31})
        )

        assert len(pages) == 40
        assert pages[30].status is PageStatus.FAILED
        assert pages[30].failure_reason == "RuntimeError"
        # Pages after the failure are still processed.
        assert pages[39].status is PageStatus.PROCESSED

    def test_missing_pages_are_reported_not_omitted(self):
        """Asking for more pages than exist yields FAILED records, not a short list."""
        record = store(make_pdf(pages=3))
        pages = extract_pages(record.source_path, expected_pages=5)

        assert len(pages) == 5
        assert [p.page_number for p in pages if p.status is PageStatus.FAILED] == [4, 5]
        assert all(p.failure_reason == "page_missing" for p in pages[3:])

    def test_unopenable_source_fails_every_page(self, tmp_path):
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"not a pdf")
        pages = extract_pages(broken, expected_pages=3)

        assert len(pages) == 3
        assert all(p.status is PageStatus.FAILED for p in pages)
        assert all(p.failure_reason == "document_unreadable" for p in pages)


class TestManifest:
    def test_manifest_counts_each_category(self):
        pages = [
            ExtractedPage(1, PageStatus.PROCESSED, text="abc"),
            ExtractedPage(2, PageStatus.EMPTY),
            ExtractedPage(3, PageStatus.UNREADABLE, image_count=1),
            ExtractedPage(4, PageStatus.FAILED, failure_reason="RuntimeError"),
        ]
        manifest = build_manifest(
            document_id="doc_x", total_pages=4, is_repaired=False, pages=pages
        )

        assert manifest.processed_pages == [1, 2]
        assert manifest.empty_pages == [2]
        assert manifest.unreadable_pages == [3]
        assert manifest.failed_pages == [4]
        assert manifest.total_text_length == 3

    def test_manifest_orders_pages_regardless_of_input_order(self):
        pages = [
            ExtractedPage(3, PageStatus.PROCESSED, text="c"),
            ExtractedPage(1, PageStatus.PROCESSED, text="a"),
            ExtractedPage(2, PageStatus.PROCESSED, text="b"),
        ]
        manifest = build_manifest(
            document_id="doc_x", total_pages=3, is_repaired=False, pages=pages
        )
        assert [p.page_number for p in manifest.pages] == [1, 2, 3]

    def test_manifest_carries_no_page_text(self):
        """Manifests are logged and serialised, so they must hold metadata only."""
        record = store(make_pdf(pages=2, text="Highly confidential clause."))
        manifest, _ = ingest_document(record)

        assert "confidential" not in manifest.model_dump_json().lower()
        assert all(p.text_length > 0 for p in manifest.pages)


class TestIngestion:
    def test_ingestion_attaches_manifest_and_text_to_the_record(self):
        record = store(make_pdf(pages=5))
        manifest, coverage = ingest_document(record)

        assert record.manifest is manifest
        assert len(record.pages) == 5
        assert coverage.status == "complete"
        assert record.status == "ingested"

    def test_page_text_is_retrievable_for_covered_pages(self):
        record = store(make_pdf(pages=3))
        ingest_document(record)

        assert "Page 2." in (record.page_text(2) or "")
        assert record.page_text(99) is None

    def test_page_text_is_none_for_uncovered_pages(self):
        record = store(make_pdf_with_image_only_page(total=2, image_page=2))
        ingest_document(record)

        assert record.page_text(1) is not None
        # The page exists but its content was never captured.
        assert record.page_text(2) is None

    def test_total_extraction_failure_marks_ingestion_failed(self):
        record = store(make_pdf(pages=3))
        record.source_path.write_bytes(b"corrupted after validation")

        _, coverage = ingest_document(record)
        assert coverage.status == "failed"
        assert record.status == "ingestion_failed"

    def test_ingestion_is_idempotent(self):
        record = store(make_pdf(pages=4))
        first, _ = ingest_document(record)
        second, coverage = ingest_document(record)

        assert len(record.pages) == 4
        assert first.pages == second.pages
        assert coverage.status == "complete"


@pytest.mark.parametrize("page_count", [1, 2, 17])
def test_extraction_always_returns_exactly_the_expected_page_count(page_count):
    record = store(make_pdf(pages=page_count))
    pages = extract_pages(record.source_path, expected_pages=page_count)
    assert len(pages) == page_count
