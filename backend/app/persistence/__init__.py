"""Optional metadata persistence (Phase 23).

The default is `NullRepository`: nothing is stored, exactly as before Phase 23
(ADR-005). When Supabase is configured, `SupabaseRepository` stores metadata
and *released* content only - see `app.persistence.supabase` for what that
means and docs/09_DECISIONS.md (ADR-005 amendment) for why.

Every write is called after the output gate has decided, and every write
method takes gated types (`AnalysisResult`, `AskResponse`), never a model
proposal. A repository failure is logged and swallowed: persistence can never
change what a user is shown, and never fail a request.
"""

from __future__ import annotations

import threading
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.analysis import AnalysisResult
from app.schemas.findings import LanguageCode
from app.schemas.qa import AskResponse

logger = get_logger(__name__)


class Repository(Protocol):
    """What the application may persist. Metadata and released content only."""

    enabled: bool

    def record_document(
        self, *, document_id: str, filename: str, page_count: int, detected_language: str
    ) -> None: ...

    def record_analysis(
        self,
        *,
        document_id: str,
        analysis_id: str,
        status: str,
        duration_ms: int | None,
        failure_kind: str | None,
        result: AnalysisResult | None,
    ) -> None: ...

    def record_answer(
        self, document_id: str, response: AskResponse, *, question_language: LanguageCode
    ) -> None: ...

    def delete_document(self, document_id: str) -> None: ...

    def purge_expired(self) -> None: ...


class NullRepository:
    """Stores nothing. The default, and the only repository tests use implicitly."""

    enabled = False

    def record_document(self, **_) -> None:
        return None

    def record_analysis(self, **_) -> None:
        return None

    def record_answer(self, *_, **__) -> None:
        return None

    def delete_document(self, document_id: str) -> None:
        return None

    def purge_expired(self) -> None:
        return None


_lock = threading.Lock()
_repository: Repository | None = None


def get_repository() -> Repository:
    """The process-wide repository, built on first use."""
    global _repository
    with _lock:
        if _repository is None:
            _repository = _build()
        return _repository


def set_repository(repository: Repository | None) -> None:
    """Replace the repository (tests), or reset it so the next call rebuilds."""
    global _repository
    with _lock:
        _repository = repository


def _build() -> Repository:
    settings = get_settings()
    if not settings.persistence_configured:
        return NullRepository()
    from app.persistence.supabase import SupabaseRepository

    repository = SupabaseRepository(settings)
    if not repository.enabled:
        # The schema check failed; the repository has already logged why.
        return NullRepository()
    return repository


def persist_document(record) -> None:
    """Record (idempotently) the metadata of an in-memory document. Never raises.

    Takes a `DocumentRecord` and passes on only what the repository may store:
    the filename (which the repository hashes, never stores), the page count
    and the detected language. No page text leaves this function.
    """
    repository = get_repository()
    if not repository.enabled:
        return
    try:
        from app.documents.language import detect_language

        repository.record_document(
            document_id=record.document_id,
            filename=record.filename,
            page_count=record.page_count,
            detected_language=detect_language(page.text for page in record.pages),
        )
    except Exception as exc:
        logger.warning("persistence failed kind=%s", type(exc).__name__)
