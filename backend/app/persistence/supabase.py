"""Supabase (PostgREST) repository - metadata and released content only.

Backend-only: authenticates with the service-role key, which never leaves the
server. Talks to PostgREST with `httpx` (already a dependency) rather than the
supabase-py client, so no new dependency is needed for four tables.

Three rules:

* **Refuse unknown schemas.** On construction it calls the
  `lexguard_schema_version()` RPC the migration creates. Anything but the
  expected answer disables the repository, so a project without the migration
  - and therefore without its RLS - is never written to.
* **Never block, never fail a request.** Writes are handed to a two-thread
  pool and return immediately; each has a 5-second timeout; every failure is
  logged by type only (a response body could echo what was sent).
* **Gated input only.** The write methods take `AnalysisResult` and
  `AskResponse` - what the output gate already released - and copy named
  fields out of them. Question text, answer text, withheld items, reasoning
  note text and the raw filename have no path into a request body here.
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.analysis import AnalysisResult
from app.schemas.findings import LanguageCode, VerificationStatus
from app.schemas.qa import AskResponse

logger = get_logger(__name__)

#: Must match `lexguard_schema_version()` in the migration.
SCHEMA_VERSION = "1"
TIMEOUT_SECONDS = 5.0


def filename_digest(filename: str, salt: str | None) -> str:
    """Salted SHA-256 of a filename. The filename itself is never stored."""
    return hashlib.sha256(f"{salt or ''}\x00{filename}".encode("utf-8")).hexdigest()


def file_extension(filename: str) -> str:
    extension = os.path.splitext(filename)[1].lower().lstrip(".")
    return extension[:10] or "none"


class SupabaseRepository:
    """Writes metadata to Supabase through PostgREST."""

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._client = httpx.Client(
            base_url=f"{settings.supabase_url.rstrip('/')}/rest/v1",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="persist")
        self.enabled = self._schema_ok()

    # --- Schema gate ---------------------------------------------------------
    def _schema_ok(self) -> bool:
        try:
            response = self._client.post("/rpc/lexguard_schema_version", json={})
            if response.status_code == 200 and response.json() == SCHEMA_VERSION:
                logger.info("persistence enabled backend=supabase schema=%s", SCHEMA_VERSION)
                return True
            logger.warning(
                "persistence_disabled reason=schema_missing http_status=%d", response.status_code
            )
        except Exception as exc:
            logger.warning("persistence_disabled reason=unreachable kind=%s", type(exc).__name__)
        return False

    # --- Transport -------------------------------------------------------------
    def _send(self, operation: str, method: str, path: str, **kwargs) -> None:
        """One request, run synchronously (called from the pool)."""
        try:
            response = self._client.request(method, path, **kwargs)
            if response.status_code >= 300:
                logger.warning(
                    "persistence write failed operation=%s http_status=%d",
                    operation,
                    response.status_code,
                )
        except Exception as exc:
            logger.warning(
                "persistence write failed operation=%s kind=%s", operation, type(exc).__name__
            )

    def _submit(self, *calls: tuple) -> None:
        """Run calls in order, off the event loop. Never raises."""
        if not self.enabled:
            return

        def run():
            for call in calls:
                self._send(*call[:3], **(call[3] if len(call) > 3 else {}))

        try:
            self._pool.submit(run)
        except Exception as exc:  # pool shut down
            logger.warning("persistence write skipped kind=%s", type(exc).__name__)

    # --- Writes --------------------------------------------------------------------
    def document_row(
        self, *, document_id: str, filename: str, page_count: int, detected_language: str
    ) -> dict:
        expires = datetime.now(timezone.utc) + timedelta(
            days=self._settings.supabase_retention_days
        )
        return {
            "id": document_id,
            "filename_sha256": filename_digest(filename, self._settings.persistence_hash_salt),
            "file_extension": file_extension(filename),
            "page_count": page_count,
            "detected_language": detected_language,
            "expires_at": expires.isoformat(),
        }

    def record_document(
        self, *, document_id: str, filename: str, page_count: int, detected_language: str
    ) -> None:
        row = self.document_row(
            document_id=document_id,
            filename=filename,
            page_count=page_count,
            detected_language=detected_language,
        )
        # `ignore-duplicates`: the first record wins, so repeated calls cannot
        # extend a document's retention.
        self._submit(
            (
                "record_document",
                "POST",
                "/documents",
                {
                    "json": row,
                    "headers": {"Prefer": "resolution=ignore-duplicates,return=minimal"},
                },
            )
        )

    @staticmethod
    def analysis_rows(
        *,
        document_id: str,
        analysis_id: str,
        status: str,
        duration_ms: int | None,
        failure_kind: str | None,
        result: AnalysisResult | None,
    ) -> tuple[dict, list[dict]]:
        """The job row and the released-finding rows. Pure; tested directly."""
        provenance = result.provenance if result is not None else None
        reasoning = result.reasoning if result is not None else None
        job = {
            "id": analysis_id,
            "document_id": document_id,
            "status": "completed" if status == "completed" else "failed",
            "provider": provenance.provider if provenance else None,
            "model": provenance.model if provenance else None,
            "reasoning_provider": provenance.reasoning_provider if provenance else None,
            "reasoning_model": provenance.reasoning_model if provenance else None,
            "verification_policy_version": (
                provenance.verification_policy_version if provenance else None
            ),
            "language": str(result.language) if result is not None else None,
            "failure_kind": failure_kind,
            "duration_ms": duration_ms,
            "proposed_count": result.proposed_count if result is not None else 0,
            "released_count": len(result.findings) if result is not None else 0,
            "withheld_count": result.withheld.total if result is not None else 0,
            "reasoning_status": str(reasoning.status) if reasoning else None,
            "notes_released_count": len(reasoning.notes) if reasoning else 0,
            "notes_withheld_count": reasoning.withheld_count if reasoning else 0,
        }
        findings = [
            {
                "analysis_job_id": analysis_id,
                "finding_id": finding.id,
                "type": finding.type,
                "claim": finding.claim,
                "quote": finding.evidence.quote,
                "page_number": finding.evidence.page,
                "section_reference": finding.evidence.section,
                "verification_status": str(finding.verification_status),
                "explanation_verified": finding.explanation_verified,
            }
            for finding in (result.findings if result is not None else [])
            # Belt and braces: the gate only releases VERIFIED, and the table
            # has a CHECK constraint saying the same.
            if finding.verification_status is VerificationStatus.VERIFIED
        ]
        return job, findings

    def record_analysis(self, **kwargs) -> None:
        job, findings = self.analysis_rows(**kwargs)
        calls: list[tuple] = [
            ("record_analysis", "POST", "/analysis_jobs",
             {"json": job, "headers": {"Prefer": "resolution=merge-duplicates,return=minimal"}}),
        ]
        if findings:
            calls.append(
                ("record_findings", "POST", "/released_findings",
                 {"json": findings,
                  "headers": {"Prefer": "resolution=ignore-duplicates,return=minimal"}})
            )
        self._submit(*calls)

    @staticmethod
    def answer_row(
        document_id: str, response: AskResponse, *, question_language: LanguageCode
    ) -> dict:
        """Metadata only. No question, no answer, no quote. Pure; tested directly."""
        provenance = response.provenance
        return {
            "document_id": document_id,
            "provider": provenance.provider if provenance else None,
            "model": provenance.model if provenance else None,
            "verification_policy_version": (
                provenance.verification_policy_version if provenance else None
            ),
            "answer_status": str(response.status),
            "question_language": str(question_language),
            "evidence_count": len(response.evidence),
            "claims_checked": response.claims_checked,
            "claims_withheld": response.claims_withheld,
            "translation_released": response.answer_translation is not None,
        }

    def record_answer(
        self, document_id: str, response: AskResponse, *, question_language: LanguageCode
    ) -> None:
        row = self.answer_row(document_id, response, question_language=question_language)
        self._submit(
            ("record_answer", "POST", "/qa_events",
             {"json": row, "headers": {"Prefer": "return=minimal"}})
        )

    # --- Deletion and retention ------------------------------------------------------
    def delete_document(self, document_id: str) -> None:
        """Delete one document; the foreign keys cascade to everything linked."""
        self._submit(
            ("delete_document", "DELETE", "/documents", {"params": {"id": f"eq.{document_id}"}})
        )

    def purge_expired(self) -> None:
        """Delete documents past `expires_at` - and only those - with their rows."""
        now = datetime.now(timezone.utc).isoformat()
        self._submit(
            ("purge_expired", "DELETE", "/documents", {"params": {"expires_at": f"lt.{now}"}})
        )

    def close(self) -> None:
        self._pool.shutdown(wait=True)
        self._client.close()


__all__ = ["SupabaseRepository", "file_extension", "filename_digest"]
