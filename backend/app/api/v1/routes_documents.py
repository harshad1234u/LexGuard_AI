"""Document endpoints.

Implemented so far: upload, extract, manifest, status, delete.

`/extract` exposes Phase 3/4 - page extraction and the coverage verdict - as
their own observable step, so the pipeline stays testable independently of the
model. The same work also runs as nodes inside the `/analyze` workflow
(docs/03_AI_AGENT_SPEC.md sec. 4), which is why skipping this endpoint cannot
skip the coverage gate.

`/analyze` and `/findings` live in `routes_analysis.py`. `/ask` arrives in a
later phase and is deliberately absent rather than stubbed, so the frontend
cannot mistake a placeholder for a working grounded result.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.core.config import get_settings
from app.agents.runner import analysis_runner
from app.core.errors import ConflictError, ErrorCode, PayloadTooLargeError
from app.documents.ingestion import ingest_document
from app.documents.manifest import DocumentManifest
from app.persistence import get_repository
from app.documents.storage import document_store
from app.documents.validation import validate_upload
from app.documents.values import index_values
from app.schemas.documents import (
    DocumentValue,
    StatusResponse,
    UploadResponse,
    ValuesExtraction,
    ValuesResponse,
)
from app.schemas.extraction import ExtractionResponse

router = APIRouter(prefix="/documents", tags=["documents"])

_READ_CHUNK_BYTES = 1 << 20  # 1 MiB


async def _read_bounded(upload: UploadFile, limit: int) -> bytes:
    """Read the upload in chunks, aborting once it exceeds `limit`.

    Reading the whole stream before checking the size would let an oversized
    upload exhaust memory before validation could reject it, so the limit is
    enforced during the read rather than after it.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(
                ErrorCode.FILE_TOO_LARGE,
                f"The file exceeds the {limit / (1024 * 1024):.0f} MB upload limit.",
                details={"limit_bytes": limit},
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    settings = get_settings()
    content = await _read_bounded(file, settings.max_upload_bytes)

    validated = validate_upload(
        filename=file.filename,
        content_type=file.content_type,
        content=content,
    )
    record = document_store.create(validated, content)

    return UploadResponse(
        document_id=record.document_id,
        filename=record.filename,
        page_count=record.page_count,
        size_bytes=record.size_bytes,
        content_type=record.content_type,
        status=record.status,
        source_repaired=record.is_repaired,
    )


@router.post("/{document_id}/extract", response_model=ExtractionResponse)
def extract_document(document_id: str) -> ExtractionResponse:
    """Extract every page and return the manifest plus the coverage verdict.

    Deterministic and entirely local - no model is involved.
    """
    record = document_store.get(document_id)
    manifest, coverage = ingest_document(record)
    return ExtractionResponse(
        document_id=record.document_id,
        status=record.status,
        manifest=manifest,
        coverage=coverage,
    )


@router.get("/{document_id}/manifest", response_model=DocumentManifest)
def document_manifest(document_id: str) -> DocumentManifest:
    """The per-page processing record. 409 until extraction has run."""
    record = document_store.get(document_id)
    if record.manifest is None:
        raise ConflictError(
            ErrorCode.COVERAGE_INCOMPLETE,
            "This document has not been extracted yet.",
            details={"coverage_status": str(record.coverage.status)},
        )
    return record.manifest


@router.get("/{document_id}/values", response_model=ValuesResponse)
def document_values(document_id: str) -> ValuesResponse:
    """Deterministic index of the values the document contains. 409 until coverage is complete.

    No model is involved, so this endpoint works when the provider does not.
    It reports what the document *says*, never what it means: the response
    carries the value, its kind and its page, and no surrounding prose.

    The coverage gate is the same one `/analyze` uses. An index built from a
    partially captured document would silently under-report, and a reader has
    no way to tell an absent value from an unread page.
    """
    record = document_store.get(document_id)
    coverage = record.coverage
    if not coverage.is_complete:
        raise ConflictError(
            ErrorCode.COVERAGE_INCOMPLETE,
            "Values cannot be indexed because document processing is incomplete.",
            details={"coverage_status": str(coverage.status)},
        )

    # Read straight off the manifest the extractor produced, so the counts
    # describe the same pass that produced the values and cannot drift from it.
    manifest = record.manifest
    pages = manifest.pages if manifest is not None else []

    return ValuesResponse(
        document_id=record.document_id,
        coverage_status=coverage.status,
        extraction=ValuesExtraction(
            characters=sum(page.text_length for page in pages),
            pages_with_text=sum(1 for page in pages if page.text_length > 0),
            pages_total=len(pages) or record.page_count,
        ),
        values=[
            DocumentValue(
                kind=item.kind, value=item.value, page=item.page, ambiguous=item.ambiguous
            )
            for item in index_values(record)
        ],
    )


@router.get("/{document_id}/status", response_model=StatusResponse)
def document_status(document_id: str) -> StatusResponse:
    record = document_store.get(document_id)
    coverage = record.coverage
    return StatusResponse(
        document_id=record.document_id,
        status=record.status,
        expected_pages=coverage.expected_pages or record.page_count,
        processed_pages=coverage.processed_pages,
        failed_pages=sorted(coverage.failed_pages),
        unreadable_pages=sorted(coverage.unreadable_pages),
        coverage_status=coverage.status,
        coverage_explanation=coverage.explanation,
        analysis_eligible=coverage.is_complete,
        source_repaired=record.is_repaired,
    )


@router.delete("/{document_id}", status_code=204, response_class=Response)
def delete_document(document_id: str) -> Response:
    """Let a user discard their document immediately rather than waiting for TTL."""
    document_store.get(document_id)  # 404 if unknown
    # The analysis describes a document that will no longer exist.
    analysis_runner.forget_document(document_id)
    document_store.delete(document_id)
    # Delete-on-discard reaches persisted metadata too (a no-op when disabled).
    get_repository().delete_document(document_id)
    return Response(status_code=204)
