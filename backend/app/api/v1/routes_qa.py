"""Document-grounded question answering.

    question -> coverage gate -> model -> Phase 5 verifier -> Q&A gate -> answer

The same shape as the analysis workflow and for the same reasons: the model is
asked only after the application knows the document was fully read, and what it
says is checked before any of it reaches a reader.

Synchronous, unlike `/analyze`. A question produces one short answer and a
person is waiting for it, so a job id and a polling loop would be worse for the
user and no safer. The cost is that the request holds a connection for the
duration; `qa_timeout_seconds` bounds that well below the analysis provider
timeout, and the limits are written up in docs/07_API_SPEC.md.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.logging import get_logger
from app.documents.ingestion import ingest_document
from app.documents.storage import DocumentRecord, document_store
from app.models import get_model_provider
from app.models.errors import (
    ModelError,
    ModelTimeoutError,
    ModelUnavailableError,
    as_question_error,
    make_error,
)
from app.models.payload import build_payload
from app.models.provider import ModelProvider, QuestionRequest
from app.schemas.qa import AskRequest, AskResponse
from app.verification.coverage import require_complete_coverage
from app.verification.qa import gate_answer, verify_answer

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["qa"])

#: Swapped in tests. Production always resolves the configured provider.
_provider_factory = get_model_provider


def _ensure_answerable(record: DocumentRecord) -> None:
    """Refuse to ask the model about a document we have not fully read.

    Delegates to the Phase 4 controller, so Q&A is gated by exactly the rule
    that gates analysis - `incomplete`, `failed`, `blocked_repaired` and
    unreadable pages are all refused by the same code, and the refusal is the
    same structured 409 a client already handles.

    Extraction runs on demand for a document that has not had it, so a client
    cannot reach the model by skipping `/extract`; it reaches the gate instead.
    """
    if record.manifest is None:
        try:
            ingest_document(record)
        except Exception as exc:
            logger.warning(
                "qa ingest failed document_id=%s type=%s",
                record.document_id,
                type(exc).__name__,
            )
            # Surfaced through the coverage gate below, which will refuse a
            # document with no usable manifest anyway.

    require_complete_coverage(record.coverage)


@router.post("/{document_id}/ask", response_model=AskResponse)
async def ask_document(document_id: str, request: AskRequest) -> AskResponse:
    """Answer a question from one uploaded document.

    404 if the document is unknown or expired, 409 if it is not eligible for a
    complete-document answer, 422 if the question is missing or malformed, and
    502/503/504 if the provider fails - all in the project's standard error
    envelope.
    """
    record = document_store.get(document_id)  # 404 if unknown or expired
    _ensure_answerable(record)

    question = request.question.strip()
    provider: ModelProvider = _provider_factory()
    settings = get_settings()

    # Only this document's pages are ever built into the payload, so the model
    # cannot be shown - and evidence cannot be matched against - another upload.
    payload = build_payload(record)

    logger.info(
        "qa asked document_id=%s pages=%d question_chars=%d",
        document_id,
        len(payload.pages),
        len(question),
    )

    try:
        answer = await asyncio.wait_for(
            provider.answer_question(QuestionRequest(payload=payload, question=question)),
            timeout=settings.qa_timeout_seconds,
        )
    # Every failure below leaves through `as_question_error`, which swaps the
    # analysis wording the provider raised for wording about this question.
    # The class, the code, the status and the `reason` detail are untouched -
    # only the sentence changes, because the sentence is the only part that
    # told the user their analysis had failed when it had not (Phase 19).
    except TimeoutError as exc:
        logger.info("qa timeout document_id=%s", document_id)
        raise as_question_error(
            make_error(ModelTimeoutError, detail="qa_timeout")
        ) from exc
    except ModelError as exc:
        # Already safe and already classified correctly; re-worded, not re-graded.
        raise as_question_error(exc) from exc
    except Exception as exc:
        # Type name only: an exception's message can echo document content.
        logger.error(
            "qa failed document_id=%s type=%s", document_id, type(exc).__name__
        )
        raise as_question_error(
            make_error(ModelUnavailableError, detail=type(exc).__name__)
        ) from exc

    # The model proposed; the application decides.
    verified = verify_answer(answer, record)
    return gate_answer(
        document_id=document_id,
        question=question,
        answer=answer,
        verified=verified,
        document=record,
    )
