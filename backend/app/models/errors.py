"""Provider failures, translated into application-safe errors.

Two rules govern everything here.

First, no secret ever escapes. `redact()` strips the API key from any string
before it is logged or raised, because a client library's exception message is
outside our control and may echo a request it was given.

Second, no provider internals reach the client. A user sees "the analysis
service is temporarily unavailable", not a stack trace, a URL, or a vendor
error body - which could also contain fragments of their own document.

Those safe sentences come in two vocabularies. The provider has no opinion
about which feature called it, so the same failure can be an analysis failure
or a failure to answer a question, and a reader has only the sentence to tell
them which. `SAFE_MESSAGES` speaks for the analysis, `QUESTION_SAFE_MESSAGES`
for `/ask`, and `as_question_error` moves a failure from the first to the
second without touching its class, code or status.
"""

from __future__ import annotations

from app.core.errors import AppError, ErrorCode

#: Replacement for any secret found in text bound for a log or a response.
REDACTION = "[redacted]"


def redact(text: str, *secrets: str | None) -> str:
    """Remove any of `secrets` from `text`.

    Called on every provider error message before it is logged or wrapped.
    """
    result = text
    for secret in secrets:
        if secret and len(secret) >= 8:
            result = result.replace(secret, REDACTION)
    return result


class ModelError(AppError):
    """Base class for model-provider failures.

    502 by default: the request was fine, an upstream dependency was not.
    """

    status_code = 502


class ModelNotConfiguredError(ModelError):
    """No API key is present, so no model can be reached."""

    status_code = 503


class ModelAuthError(ModelError):
    """The provider rejected our credentials. A server-side misconfiguration."""

    status_code = 502


class ModelNotFoundError(ModelError):
    """The configured model identifier is not available to this account."""

    status_code = 502


class ModelTimeoutError(ModelError):
    status_code = 504


class ModelRateLimitError(ModelError):
    status_code = 429


class ModelUnavailableError(ModelError):
    """Network failure, or the provider returned a server error."""

    status_code = 503


class ModelResponseError(ModelError):
    """The model replied, but not with something we can use.

    Malformed JSON, or output that fails schema validation. Deliberately an
    error rather than a partial result: a half-parsed analysis is exactly the
    kind of thing that should never be presented as findings.
    """

    status_code = 502


#: Messages safe to show a user - no vendor detail, no document content.
SAFE_MESSAGES: dict[type[ModelError], str] = {
    ModelNotConfiguredError: "Document analysis is not available: the service is not configured.",
    ModelAuthError: "Document analysis is temporarily unavailable.",
    ModelNotFoundError: "Document analysis is temporarily unavailable.",
    ModelTimeoutError: "The analysis took too long to complete. Please try again.",
    ModelRateLimitError: "The analysis service is busy. Please try again shortly.",
    ModelUnavailableError: "The analysis service is temporarily unavailable.",
    ModelResponseError: "The analysis could not be completed. Please try again.",
}

#: The same failures, worded for the question path.
#:
#: A provider outage during `/ask` is not a failure of the document analysis,
#: and the sentence a reader sees is the only thing that tells them which of
#: the two happened. Same classes, same codes, same statuses, same details -
#: only the wording differs, so a client switching on `code` is unaffected.
#:
#: Kept beside `SAFE_MESSAGES` rather than assembled in the route, because the
#: rule that binds them is that every entry in one has a counterpart in the
#: other; a test asserts exactly that.
QUESTION_SAFE_MESSAGES: dict[type[ModelError], str] = {
    ModelNotConfiguredError: "Questions cannot be answered: the service is not configured.",
    ModelAuthError: "Answering questions about this document is temporarily unavailable.",
    ModelNotFoundError: "Answering questions about this document is temporarily unavailable.",
    ModelTimeoutError: (
        "The question took too long to answer and was stopped. No answer was "
        "shown, because none could be checked against your document in time."
    ),
    ModelRateLimitError: "The question service is busy. Please try again shortly.",
    ModelUnavailableError: (
        "The question service is temporarily unavailable. No answer was "
        "generated or shown. You can ask again later."
    ),
    ModelResponseError: "The question could not be answered. Please try again.",
}

DEFAULT_CODES: dict[type[ModelError], ErrorCode] = {
    ModelNotConfiguredError: ErrorCode.MODEL_NOT_CONFIGURED,
    ModelAuthError: ErrorCode.MODEL_AUTH_FAILED,
    ModelNotFoundError: ErrorCode.MODEL_NOT_FOUND,
    ModelTimeoutError: ErrorCode.MODEL_TIMEOUT,
    ModelRateLimitError: ErrorCode.MODEL_RATE_LIMITED,
    ModelUnavailableError: ErrorCode.MODEL_UNAVAILABLE,
    ModelResponseError: ErrorCode.MODEL_INVALID_RESPONSE,
}


def make_error(kind: type[ModelError], *, detail: str | None = None) -> ModelError:
    """Build a provider error with its safe message and stable code.

    `detail` is a short diagnostic category (an exception class name, say) for
    logs and debugging. It must already be redacted and must never contain
    document text.
    """
    error = kind(
        DEFAULT_CODES[kind],
        SAFE_MESSAGES[kind],
        details={"reason": detail} if detail else {},
    )
    return error


def as_question_error(error: ModelError) -> ModelError:
    """Re-word a provider failure so it reads as a failure to answer.

    The provider phrases its failures for the analysis - it is the same call
    either way and it has no opinion about which feature asked - so `/ask` is
    the only place that knows the failure belongs to a question. Everything a
    client switches on is carried over unchanged: class, code, HTTP status and
    the `reason` detail. Only the human sentence differs.

    An unrecognised subclass is returned untouched, so adding an error type
    without a question wording degrades to the analysis sentence rather than
    to no message at all.
    """
    message = QUESTION_SAFE_MESSAGES.get(type(error))
    if message is None:
        return error
    return type(error)(error.code, message, details=dict(error.details))
