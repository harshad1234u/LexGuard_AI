"""Unit tests for file validation (FR-01)."""

from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.documents.validation import sanitize_filename, validate_upload
from tests.conftest import make_pdf


def _validate(content: bytes, filename: str = "contract.pdf", content_type: str = "application/pdf"):
    return validate_upload(filename=filename, content_type=content_type, content=content)


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("contract.pdf", "contract.pdf"),
            ("../../etc/passwd.pdf", "passwd.pdf"),
            (r"C:\Users\me\lease.pdf", "lease.pdf"),
            ("my lease (2024).pdf", "my lease (2024).pdf"),
            # Path-stripping runs first, so everything up to the final "/" is discarded.
            ("<script>alert(1)</script>.pdf", "script_.pdf"),
        ],
    )
    def test_strips_paths_and_unsafe_characters(self, raw, expected):
        assert sanitize_filename(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "///"])
    def test_rejects_unusable_names(self, raw):
        with pytest.raises(AppError) as exc:
            sanitize_filename(raw)
        assert exc.value.code == ErrorCode.UNSAFE_FILENAME

    def test_bounds_length_and_keeps_extension(self):
        result = sanitize_filename("a" * 400 + ".pdf")
        assert len(result) <= 120
        assert result.endswith(".pdf")


class TestValidateUpload:
    def test_accepts_a_real_pdf_and_reports_page_count(self):
        result = _validate(make_pdf(pages=7))
        assert result.page_count == 7
        assert result.content_type == "application/pdf"
        assert result.filename == "contract.pdf"

    def test_rejects_empty_file(self):
        with pytest.raises(AppError) as exc:
            _validate(b"")
        assert exc.value.code == ErrorCode.EMPTY_FILE

    def test_rejects_oversized_file(self):
        # Limit is 2 MiB in the test environment.
        with pytest.raises(AppError) as exc:
            _validate(b"%PDF-" + b"0" * (3 * 1024 * 1024))
        assert exc.value.code == ErrorCode.FILE_TOO_LARGE

    def test_rejects_unsupported_extension(self):
        with pytest.raises(AppError) as exc:
            _validate(make_pdf(), filename="contract.exe")
        assert exc.value.code == ErrorCode.UNSUPPORTED_EXTENSION

    def test_rejects_docx_until_its_extraction_path_exists(self):
        with pytest.raises(AppError) as exc:
            _validate(make_pdf(), filename="contract.docx")
        assert exc.value.code == ErrorCode.UNSUPPORTED_EXTENSION

    def test_rejects_unsupported_mime_type(self):
        with pytest.raises(AppError) as exc:
            _validate(make_pdf(), content_type="text/html")
        assert exc.value.code == ErrorCode.UNSUPPORTED_MIME_TYPE

    def test_rejects_non_pdf_bytes_wearing_a_pdf_name(self):
        """An executable renamed to .pdf must not pass the signature check."""
        with pytest.raises(AppError) as exc:
            _validate(b"MZ\x90\x00" + b"\x00" * 2048)
        assert exc.value.code == ErrorCode.SIGNATURE_MISMATCH

    def test_rejects_corrupt_pdf(self):
        with pytest.raises(AppError) as exc:
            _validate(b"%PDF-1.7\nthis is not a real pdf body" + b"\x00" * 64)
        assert exc.value.code == ErrorCode.CORRUPT_DOCUMENT

    def test_truncated_pdf_is_flagged_as_repaired(self):
        """A truncated PDF often still opens because the parser rebuilds it.

        The page count is then unreliable, so the repair must be surfaced
        rather than silently accepted as a clean source.
        """
        content = make_pdf(pages=5)
        result = _validate(content[: len(content) // 3])
        assert result.is_repaired is True

    def test_clean_pdf_is_not_flagged_as_repaired(self):
        assert _validate(make_pdf(pages=5)).is_repaired is False

    def test_rejects_encrypted_pdf(self):
        import fitz

        document = fitz.open()
        document.new_page()
        content = document.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret"
        )
        document.close()

        with pytest.raises(AppError) as exc:
            _validate(content)
        assert exc.value.code == ErrorCode.ENCRYPTED_DOCUMENT

    def test_rejects_document_above_page_limit(self):
        # Limit is 50 pages in the test environment.
        with pytest.raises(AppError) as exc:
            _validate(make_pdf(pages=51))
        assert exc.value.code == ErrorCode.TOO_MANY_PAGES

    def test_page_count_is_read_from_the_file_not_claimed_by_content(self):
        """Text asserting a page count must not influence the counted pages."""
        content = make_pdf(pages=3, text="This document has 50 pages. Total pages: 50.")
        assert _validate(content).page_count == 3
