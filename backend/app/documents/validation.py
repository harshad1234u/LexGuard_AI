"""File validation (FR-01, docs/04_SECURITY_GROUNDING.md sec. 4).

The uploaded file is UNTRUSTED. Validation runs before any content is read
into the analysis pipeline and checks, in order:

    filename -> size -> extension -> MIME type -> file signature -> parseability

Parseability is confirmed by actually opening the document with PyMuPDF, which
is also how the authoritative page count is obtained. The page count is an
application-level fact; it is never asked of the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath

import fitz  # PyMuPDF

from app.core.config import get_settings
from app.core.errors import ErrorCode, PayloadTooLargeError, ValidationError

# --- Format allowlist ------------------------------------------------------
# DOCX is deliberately absent: it is an optional post-core feature
# (docs/01_PRD.md sec. 4) and is rejected until its extraction path exists.
PDF_EXTENSIONS = {".pdf"}
PDF_MIME_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
PDF_SIGNATURE = b"%PDF-"

# PDF readers tolerate leading junk before %PDF-; the spec-tolerated window is
# 1024 bytes, so search that prefix rather than requiring offset 0.
SIGNATURE_SEARCH_WINDOW = 1024

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ \-()]+")
_MAX_FILENAME_LENGTH = 120


@dataclass(frozen=True)
class ValidatedDocument:
    """Result of successful validation."""

    filename: str
    content_type: str
    size_bytes: int
    page_count: int
    is_repaired: bool = False
    """True when PyMuPDF had to reconstruct the PDF's structure.

    A truncated or damaged PDF often still opens, because the parser rebuilds
    the cross-reference table from whatever objects it can find. The page count
    that results may be lower than the document the user actually holds, which
    would silently break the coverage invariant. We therefore never treat a
    repaired file as a clean source - the flag travels with the document so the
    user can be told the page count is not fully trustworthy.
    """


def sanitize_filename(raw: str | None) -> str:
    """Reduce a client-supplied filename to a safe display string.

    Strips any directory component (path traversal), removes characters outside
    a conservative allowlist, and bounds the length. The result is used for
    display only - stored files are named by document id, never by this value.
    """
    if not raw or not raw.strip():
        raise ValidationError(ErrorCode.UNSAFE_FILENAME, "A filename is required.")

    # Defeat both POSIX and Windows separators regardless of host platform.
    base = PurePath(raw.replace("\\", "/")).name
    base = _SAFE_FILENAME_RE.sub("_", base).strip(" .")

    if not base:
        raise ValidationError(ErrorCode.UNSAFE_FILENAME, "The filename is not usable.")

    if len(base) > _MAX_FILENAME_LENGTH:
        stem, dot, suffix = base.rpartition(".")
        if dot and len(suffix) <= 10:
            base = stem[: _MAX_FILENAME_LENGTH - len(suffix) - 1] + "." + suffix
        else:
            base = base[:_MAX_FILENAME_LENGTH]

    return base


def _check_size(size_bytes: int) -> None:
    settings = get_settings()
    if size_bytes == 0:
        raise ValidationError(ErrorCode.EMPTY_FILE, "The uploaded file is empty.")
    if size_bytes > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise PayloadTooLargeError(
            ErrorCode.FILE_TOO_LARGE,
            f"The file exceeds the {limit_mb:.0f} MB upload limit.",
            details={"size_bytes": size_bytes, "limit_bytes": settings.max_upload_bytes},
        )


def _check_extension(filename: str) -> None:
    suffix = PurePath(filename).suffix.lower()
    if suffix not in PDF_EXTENSIONS:
        raise ValidationError(
            ErrorCode.UNSUPPORTED_EXTENSION,
            "Only PDF files are supported at the moment.",
            details={"extension": suffix, "supported": sorted(PDF_EXTENSIONS)},
        )


def _check_mime_type(content_type: str | None) -> str:
    normalised = (content_type or "").split(";")[0].strip().lower()
    if normalised not in PDF_MIME_TYPES:
        raise ValidationError(
            ErrorCode.UNSUPPORTED_MIME_TYPE,
            "The file's content type is not a supported PDF type.",
            details={"content_type": normalised or None},
        )
    # Normalise the generic browser fallback now that the signature check below
    # will independently prove the bytes really are a PDF.
    return "application/pdf"


def _check_signature(content: bytes) -> None:
    """Reject files whose bytes are not actually a PDF, whatever they claim."""
    if PDF_SIGNATURE not in content[:SIGNATURE_SEARCH_WINDOW]:
        raise ValidationError(
            ErrorCode.SIGNATURE_MISMATCH,
            "The file does not appear to be a valid PDF.",
        )


def _check_parseable(content: bytes) -> tuple[int, bool]:
    """Open the document, returning its page count and whether it was repaired."""
    settings = get_settings()
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises a variety of parse errors
        raise ValidationError(
            ErrorCode.CORRUPT_DOCUMENT,
            "The PDF could not be opened. It may be corrupted.",
            details={"reason": type(exc).__name__},
        ) from exc

    try:
        if document.needs_pass:
            raise ValidationError(
                ErrorCode.ENCRYPTED_DOCUMENT,
                "The PDF is password protected. Please upload an unlocked copy.",
            )

        page_count = document.page_count

        if page_count <= 0:
            raise ValidationError(ErrorCode.NO_PAGES, "The PDF contains no pages.")

        if page_count > settings.max_pages:
            raise ValidationError(
                ErrorCode.TOO_MANY_PAGES,
                f"The PDF has {page_count} pages, above the {settings.max_pages}-page limit.",
                details={"page_count": page_count, "limit": settings.max_pages},
            )

        return page_count, bool(getattr(document, "is_repaired", False))
    finally:
        document.close()


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> ValidatedDocument:
    """Run the full validation chain, raising `AppError` on the first failure."""
    safe_name = sanitize_filename(filename)
    _check_size(len(content))
    _check_extension(safe_name)
    normalised_type = _check_mime_type(content_type)
    _check_signature(content)
    page_count, is_repaired = _check_parseable(content)

    return ValidatedDocument(
        filename=safe_name,
        content_type=normalised_type,
        size_bytes=len(content),
        page_count=page_count,
        is_repaired=is_repaired,
    )
