"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.agents.runner import analysis_runner
from app.documents.storage import document_store
from app.persistence import get_repository, set_repository

#: How often persisted metadata past its retention is purged.
PURGE_INTERVAL_SECONDS = 3600

logger = get_logger(__name__)

DISCLAIMER = (
    "This application provides legal information and document-understanding "
    "assistance only. It does not create an attorney-client relationship, does "
    "not replace professional legal advice, and does not guarantee legal "
    "correctness or outcomes."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.workspace_path.mkdir(parents=True, exist_ok=True)

    # Provider roles: names and booleans only, never a key.
    readiness = settings.provider_readiness()
    keys = {"gemini": "GEMINI_API_KEY", "nemotron": "NVIDIA_API_KEY"}
    for role, provider in (
        ("analysis", settings.analysis_provider),
        ("qa", settings.qa_provider),
    ):
        if not readiness[role]:
            logger.warning(
                "%s is not set; the %s role (%s) will be unavailable.",
                keys[provider], role, provider,
            )
    logger.info(
        "provider roles analysis=%s qa=%s reasoning=%s reasoning_effective=%s",
        settings.analysis_provider,
        settings.qa_provider,
        settings.reasoning_provider,
        settings.reasoning_effective,
    )
    if settings.reasoning_effective and not readiness["reasoning"]:
        logger.warning(
            "NVIDIA_API_KEY is not set; reasoning notes will report 'unavailable'."
        )

    # The repository's schema check is a network call: made off the loop.
    repository = await asyncio.to_thread(get_repository)
    purger = None
    if repository.enabled:
        repository.purge_expired()
        purger = asyncio.create_task(_purge_periodically())

    yield
    if purger is not None:
        purger.cancel()
    close = getattr(repository, "close", None)
    if close is not None:
        await asyncio.to_thread(close)
    set_repository(None)
    # Ephemeral by design: nothing uploaded survives the process.
    analysis_runner.clear()
    document_store.clear()


async def _purge_periodically() -> None:
    while True:
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)
        get_repository().purge_expired()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PromptWars Legal AI",
        description=DISCLAIMER,
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def limit_json_body(request: Request, call_next):
        """Reject an oversized JSON body before it is parsed.

        Field-level limits (a 2000-character question) only apply once the body
        has been decoded, so without this a multi-megabyte document could be
        pasted into a JSON field and parsed in full before being rejected.
        Checking the declared length costs nothing and refuses it first.

        Multipart uploads are untouched: they stream through their own bounded
        reader, which enforces the much larger upload limit chunk by chunk.

        Limitation: a chunked request declares no length, so it is parsed as
        before. FastAPI's JSON decoding bounds that in practice, and closing it
        properly belongs to the reverse proxy in front of the app.
        """
        if "application/json" in request.headers.get("content-type", ""):
            declared = request.headers.get("content-length")
            try:
                length = int(declared) if declared is not None else 0
            except ValueError:
                length = 0
            if length > settings.max_json_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": str(ErrorCode.FILE_TOO_LARGE),
                            "message": "The request is too large.",
                            "details": {"limit_bytes": settings.max_json_body_bytes},
                        }
                    },
                )
        return await call_next(request)

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "The request did not match the expected format.",
                    "details": {"fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()]},
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log the type only; an exception message can echo document content,
        # and `logger.exception` would render that message with the traceback.
        logger.error("unhandled error type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": str(ErrorCode.INTERNAL_ERROR),
                    "message": "An unexpected error occurred while processing the request.",
                    "details": {},
                }
            },
        )

    app.include_router(api_router)
    return app


app = create_app()
