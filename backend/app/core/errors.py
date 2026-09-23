"""Application error types and their API representation.

Every failure surfaced to the client carries a stable machine-readable
`code` so the frontend can render a specific state instead of a generic
"something went wrong" (PRD sec. 10, "clear error messages").
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    # --- Upload / validation (FR-01) ---
    EMPTY_FILE = "empty_file"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_EXTENSION = "unsupported_extension"
    UNSUPPORTED_MIME_TYPE = "unsupported_mime_type"
    SIGNATURE_MISMATCH = "signature_mismatch"
    CORRUPT_DOCUMENT = "corrupt_document"
    ENCRYPTED_DOCUMENT = "encrypted_document"
    NO_PAGES = "no_pages"
    TOO_MANY_PAGES = "too_many_pages"
    UNSAFE_FILENAME = "unsafe_filename"

    # --- Lifecycle ---
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_EXPIRED = "document_expired"
    EXTRACTION_FAILED = "extraction_failed"

    # --- Coverage gate (docs/04_SECURITY_GROUNDING.md sec. 12) ---
    COVERAGE_INCOMPLETE = "coverage_incomplete"

    # --- Model provider ---
    MODEL_NOT_CONFIGURED = "model_not_configured"
    MODEL_AUTH_FAILED = "model_auth_failed"
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_TIMEOUT = "model_timeout"
    MODEL_RATE_LIMITED = "model_rate_limited"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_INVALID_RESPONSE = "model_invalid_response"

    # --- Internal ---
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    """Base class for errors that are safe to report to the client."""

    status_code: int = 400

    def __init__(self, code: ErrorCode, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict:
        return {
            "error": {
                "code": str(self.code),
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationError(AppError):
    """The uploaded file was rejected before any processing took place."""

    status_code = 422


class PayloadTooLargeError(AppError):
    status_code = 413


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    """The document exists but is not in a state that permits this operation."""

    status_code = 409
