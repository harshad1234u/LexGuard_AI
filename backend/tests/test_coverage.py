"""Phase 4: the coverage controller and its hard gate.

These tests encode the coverage invariant from docs/04_SECURITY_GROUNDING.md
sec. 12 and the Phase 2 repaired-PDF rule. They are pure functions over a
manifest - no PDF, no model, no I/O - which is the point: coverage is decided by
the application from its own counters.
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.documents.extraction import ExtractedPage, PageStatus
from app.documents.manifest import build_manifest
from app.verification.coverage import (
    BlockingReason,
    CoverageGateError,
    check_coverage,
    require_complete_coverage,
)


def manifest_of(
    statuses: list[PageStatus],
    *,
    is_repaired: bool = False,
    total_pages: int | None = None,
    failure_reason: str | None = None,
):
    """Build a manifest from a list of per-page statuses."""
    pages = [
        ExtractedPage(
            page_number=index + 1,
            status=status,
            text="text" if status is PageStatus.PROCESSED else "",
            image_count=1 if status is PageStatus.UNREADABLE else 0,
            failure_reason=failure_reason if status is PageStatus.FAILED else None,
        )
        for index, status in enumerate(statuses)
    ]
    return build_manifest(
        document_id="doc_test",
        total_pages=total_pages if total_pages is not None else len(statuses),
        is_repaired=is_repaired,
        pages=pages,
    )


class TestCompleteCoverage:
    def test_all_pages_processed_is_complete(self):
        report = check_coverage(manifest_of([PageStatus.PROCESSED] * 50))

        assert report.status == "complete"
        assert report.expected_pages == 50
        assert report.processed_pages == 50
        assert report.failed_pages == []
        assert report.blocking_reasons == []
        assert report.is_complete is True

    def test_blank_pages_do_not_prevent_completeness(self):
        """A blank page held no content to miss."""
        report = check_coverage(
            manifest_of([PageStatus.PROCESSED, PageStatus.EMPTY, PageStatus.PROCESSED])
        )
        assert report.status == "complete"
        assert report.processed_pages == 3


class TestIncompleteCoverage:
    def test_forty_nine_of_fifty_is_incomplete(self):
        """The canonical case from docs/01_PRD.md sec. 8."""
        report = check_coverage(
            manifest_of([PageStatus.PROCESSED] * 49 + [PageStatus.FAILED])
        )

        assert report.status == "incomplete"
        assert report.expected_pages == 50
        assert report.processed_pages == 49
        assert report.failed_pages == [50]
        assert BlockingReason.PAGES_FAILED in report.blocking_reasons

    def test_thirty_of_fifty_is_incomplete(self):
        report = check_coverage(
            manifest_of([PageStatus.PROCESSED] * 30 + [PageStatus.FAILED] * 20)
        )
        assert report.status == "incomplete"
        assert report.processed_pages == 30

    def test_missing_pages_are_reported_as_such(self):
        report = check_coverage(
            manifest_of(
                [PageStatus.PROCESSED] * 3 + [PageStatus.FAILED] * 2,
                failure_reason="page_missing",
            )
        )
        assert report.status == "incomplete"
        assert BlockingReason.PAGES_MISSING in report.blocking_reasons
        # A missing page is not also reported as a processing failure.
        assert BlockingReason.PAGES_FAILED not in report.blocking_reasons

    def test_unreadable_page_blocks_completeness(self):
        """A scanned page whose text was never captured is not coverage."""
        report = check_coverage(
            manifest_of([PageStatus.PROCESSED, PageStatus.UNREADABLE, PageStatus.PROCESSED])
        )

        assert report.status == "incomplete"
        assert report.unreadable_pages == [2]
        assert report.processed_pages == 2
        assert BlockingReason.PAGES_UNREADABLE in report.blocking_reasons


class TestRepairedDocuments:
    def test_repaired_pdf_cannot_become_complete(self):
        """Every recoverable page read, but the source was rebuilt to get there."""
        report = check_coverage(manifest_of([PageStatus.PROCESSED] * 10, is_repaired=True))

        assert report.status == "blocked_repaired"
        assert report.status != "complete"
        assert report.is_complete is False
        assert report.processed_pages == 10
        assert BlockingReason.SOURCE_REPAIRED in report.blocking_reasons

    def test_repaired_and_failed_reports_the_more_severe_verdict(self):
        report = check_coverage(
            manifest_of([PageStatus.PROCESSED] * 9 + [PageStatus.FAILED], is_repaired=True)
        )
        assert report.status == "incomplete"
        # Both problems are still surfaced.
        assert BlockingReason.SOURCE_REPAIRED in report.blocking_reasons
        assert BlockingReason.PAGES_FAILED in report.blocking_reasons

    @pytest.mark.parametrize("page_count", [1, 5, 50])
    def test_repair_blocks_completeness_at_any_size(self, page_count):
        report = check_coverage(
            manifest_of([PageStatus.PROCESSED] * page_count, is_repaired=True)
        )
        assert report.is_complete is False


class TestFailedAndPending:
    def test_no_manifest_is_pending(self):
        report = check_coverage(None, expected_pages=12)

        assert report.status == "pending"
        assert report.expected_pages == 12
        assert report.processed_pages == 0
        assert BlockingReason.NOT_EXTRACTED in report.blocking_reasons

    def test_nothing_readable_is_failed(self):
        report = check_coverage(manifest_of([PageStatus.FAILED] * 4))

        assert report.status == "failed"
        assert report.processed_pages == 0

    def test_zero_page_manifest_is_failed(self):
        report = check_coverage(manifest_of([], total_pages=0))
        assert report.status == "failed"
        assert BlockingReason.NO_PAGES in report.blocking_reasons


class TestHardGate:
    """require_complete_coverage is what stands between a document and the model."""

    def test_gate_passes_for_complete_coverage(self):
        report = check_coverage(manifest_of([PageStatus.PROCESSED] * 5))
        require_complete_coverage(report)  # must not raise

    @pytest.mark.parametrize(
        "statuses,is_repaired",
        [
            ([PageStatus.PROCESSED] * 4 + [PageStatus.FAILED], False),
            ([PageStatus.PROCESSED, PageStatus.UNREADABLE], False),
            ([PageStatus.PROCESSED] * 5, True),
            ([PageStatus.FAILED] * 3, False),
        ],
    )
    def test_gate_blocks_every_non_complete_verdict(self, statuses, is_repaired):
        report = check_coverage(manifest_of(statuses, is_repaired=is_repaired))
        with pytest.raises(CoverageGateError):
            require_complete_coverage(report)

    def test_gate_blocks_an_unextracted_document(self):
        with pytest.raises(CoverageGateError):
            require_complete_coverage(check_coverage(None, expected_pages=10))

    def test_gate_error_explains_itself_with_counts(self):
        report = check_coverage(manifest_of([PageStatus.PROCESSED] * 49 + [PageStatus.FAILED]))
        with pytest.raises(AppError) as exc:
            require_complete_coverage(report)

        assert exc.value.code == ErrorCode.COVERAGE_INCOMPLETE
        assert exc.value.status_code == 409
        assert exc.value.details["expected_pages"] == 50
        assert exc.value.details["processed_pages"] == 49
        assert exc.value.details["failed_pages"] == [50]

    def test_repaired_gate_error_names_the_repair(self):
        report = check_coverage(manifest_of([PageStatus.PROCESSED] * 3, is_repaired=True))
        with pytest.raises(AppError) as exc:
            require_complete_coverage(report)

        assert "source_repaired" in exc.value.details["blocking_reasons"]
        assert "repaired" in exc.value.message.lower()


class TestExplanations:
    def test_complete_explanation_is_plain(self):
        report = check_coverage(manifest_of([PageStatus.PROCESSED] * 2))
        assert report.explanation == "Every page of this document was processed."

    def test_every_blocking_reason_has_a_message(self):
        """A reason with no explanation would surface as an empty error to the user."""
        from app.verification.coverage import REASON_MESSAGES

        assert set(REASON_MESSAGES) == set(BlockingReason)
        assert all(REASON_MESSAGES[r].strip() for r in BlockingReason)
