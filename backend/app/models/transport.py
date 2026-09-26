"""Provider-neutral transport vocabulary.

Every vendor module needs the same three things: a fixed vocabulary for *why*
a call failed, a way to recover an HTTP status from an error that carries none,
and a metadata-only log line. They live here so a second provider reuses them
instead of growing its own, subtly different, copy.

Nothing here makes a request. Each provider owns its own deadline and client
lifecycle (see `nemotron._invoke` for the Phase 22 pattern), because the SDKs
differ in what construction costs.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import StrEnum

from app.core.logging import get_logger
from app.models.errors import (
    ModelAuthError,
    ModelError,
    ModelNotConfiguredError,
    ModelNotFoundError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from app.models.payload import DocumentPayload


class ProviderFailureKind(StrEnum):
    """Why a provider call failed, as one of ten fixed values.

    Internal and operator-facing: recorded in logs, provenance and audit rows.
    The public `ErrorCategory` a client sees is deliberately coarser and is
    unchanged by this enum.
    """

    CONFIGURATION = "configuration"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    CAPACITY = "capacity"
    NETWORK = "network"
    TIMEOUT = "timeout"
    CONSTRUCTION_TIMEOUT = "construction_timeout"
    INVALID_RESPONSE = "invalid_response"
    SCHEMA_INVALID = "schema_invalid"
    UNKNOWN = "unknown"


#: The `reason` strings providers record, mapped onto the fixed kinds. The
#: reasons predate the enum (Phase 19) and tests assert them, so they stay; the
#: kind is derived from them rather than replacing them.
_REASON_KINDS: dict[str, ProviderFailureKind] = {
    "provider_capacity": ProviderFailureKind.CAPACITY,
    "upstream_server_error": ProviderFailureKind.CAPACITY,
    "service_unavailable": ProviderFailureKind.CAPACITY,
    "authentication_rejected": ProviderFailureKind.AUTH,
    "model_not_available": ProviderFailureKind.CONFIGURATION,
    "rate_limited": ProviderFailureKind.RATE_LIMIT,
    "upstream_timeout": ProviderFailureKind.TIMEOUT,
    "timeout": ProviderFailureKind.TIMEOUT,
    "construction_timeout": ProviderFailureKind.CONSTRUCTION_TIMEOUT,
    "network_failure": ProviderFailureKind.NETWORK,
    "unclassified": ProviderFailureKind.UNKNOWN,
    "empty_response": ProviderFailureKind.INVALID_RESPONSE,
    "no_json_object": ProviderFailureKind.INVALID_RESPONSE,
    "unreadable_content": ProviderFailureKind.INVALID_RESPONSE,
}

#: Fallback by error class when the reason is absent or unrecognised.
_CLASS_KINDS: dict[type[ModelError], ProviderFailureKind] = {
    ModelNotConfiguredError: ProviderFailureKind.CONFIGURATION,
    ModelAuthError: ProviderFailureKind.AUTH,
    ModelNotFoundError: ProviderFailureKind.CONFIGURATION,
    ModelRateLimitError: ProviderFailureKind.RATE_LIMIT,
    ModelTimeoutError: ProviderFailureKind.TIMEOUT,
    ModelUnavailableError: ProviderFailureKind.UNKNOWN,
    ModelResponseError: ProviderFailureKind.INVALID_RESPONSE,
}


def failure_kind(error: ModelError) -> ProviderFailureKind:
    """The fixed kind for a provider error. Never raises."""
    reason = str(error.details.get("reason", "")) if error.details else ""
    if reason.startswith("schema_invalid"):
        return ProviderFailureKind.SCHEMA_INVALID
    if reason in _REASON_KINDS:
        return _REASON_KINDS[reason]
    return _CLASS_KINDS.get(type(error), ProviderFailureKind.UNKNOWN)


@dataclass(frozen=True)
class ProviderDiagnosis:
    """Why a provider call failed, in terms safe to log.

    `error` is what the caller raises and the user eventually sees. `reason`
    and `status` exist only for operators: they are a fixed vocabulary and an
    HTTP status, never the upstream message, which may quote the document.
    """

    error: type
    reason: str
    status: int | None = None


def diagnose_message(message: str, status: int | None) -> ProviderDiagnosis:
    """Classify an already-redacted, lower-cased upstream error.

    Shared by every provider so one upstream condition gets one reason
    regardless of which SDK surfaced it. Order matters: capacity is checked
    first because a shared-endpoint 503 is transient, not a misconfiguration.
    """
    if status is None:
        status = status_from_message(message)

    def found(error: type, reason: str) -> ProviderDiagnosis:
        return ProviderDiagnosis(error=error, reason=reason, status=status)

    # NVIDIA's shared endpoint reports capacity as "ResourceExhausted" (503).
    # Classified exactly as before Phase 23.
    if "resourceexhausted" in message or "request limit reached" in message:
        return found(ModelUnavailableError, "provider_capacity")
    # Gemini spells it RESOURCE_EXHAUSTED and sends it with 429 for quota
    # limits - a rate limit, not an outage - and occasionally with 503.
    if "resource_exhausted" in message:
        if status == 429:
            return found(ModelRateLimitError, "rate_limited")
        return found(ModelUnavailableError, "provider_capacity")

    if status == 401 or status == 403 or "unauthor" in message or "forbidden" in message:
        return found(ModelAuthError, "authentication_rejected")
    if "api key not valid" in message or "permission_denied" in message:
        return found(ModelAuthError, "authentication_rejected")
    if status == 404 or "not found" in message or "unknown model" in message:
        return found(ModelNotFoundError, "model_not_available")
    if status == 429 or "rate limit" in message or "too many requests" in message:
        return found(ModelRateLimitError, "rate_limited")
    if status is not None and 500 <= status < 600:
        return found(ModelUnavailableError, "upstream_server_error")
    if "service unavailable" in message:
        return found(ModelUnavailableError, "service_unavailable")
    if "timeout" in message or "timed out" in message:
        return found(ModelTimeoutError, "upstream_timeout")
    if "connect" in message or "network" in message or "resolve" in message:
        return found(ModelUnavailableError, "network_failure")

    # Nothing matched. The user-facing result stays "temporarily unavailable";
    # the log records `unclassified` so an application bug wearing a provider
    # error's clothes stays visible.
    return found(ModelUnavailableError, "unclassified")


#: Status codes as providers embed them in an error message, e.g.
#: "{'code': 503}", "[429]" or "429 RESOURCE_EXHAUSTED".
_STATUS_IN_MESSAGE = re.compile(r"(?:'code':\s*|\"code\":\s*|\[)(\d{3})\b")


def status_from_message(message: str) -> int | None:
    """Recover an HTTP status from an error message that carries no response."""
    match = _STATUS_IN_MESSAGE.search(message)
    if match:
        code = int(match.group(1))
        if 100 <= code < 600:
            return code
    return None


def log_call(
    logger_name: str,
    provider: str,
    operation: str,
    payload: DocumentPayload | None,
    started: float,
    outcome: str,
    **extra,
) -> None:
    """Metadata only. No prompt, no document text, no key, no response body."""
    get_logger(logger_name).info(
        "model call provider=%s operation=%s document_id=%s pages=%d "
        "outcome=%s latency_ms=%d%s",
        provider,
        operation,
        payload.document_id if payload is not None else "none",
        len(payload.pages) if payload is not None else 0,
        outcome,
        int((time.perf_counter() - started) * 1000),
        "".join(f" {k}={v}" for k, v in extra.items()),
    )
