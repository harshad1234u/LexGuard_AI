"""Gemini, via the official `google-genai` SDK (Gemini Developer API).

The only module in the application that knows Google exists. Like the
Nemotron module, it produces PROPOSALS: the reply is parsed by the same strict
schema and every finding still goes to the application's verifier and output
gate. A successful Gemini call means only that Gemini answered.

What was checked about the SDK before writing this (google-genai 2.25.0):

* Constructing `genai.Client(api_key=...)` makes no network request. It is
  still built through `asyncio.to_thread` under the call's deadline, the
  Phase 22 pattern, so a future SDK that starts doing I/O at construction
  cannot freeze the event loop.
* Retries are a single attempt unless `retry_options` says otherwise. It is
  pinned to one attempt anyway: retries are an explicit product decision here
  (docs/03_AI_AGENT_SPEC.md sec. 8), not an SDK default.
* JSON output is requested with `response_mime_type`. The schema is enforced
  by the application (`parse_analysis`), not delegated to the provider: a
  provider-side schema would be a second definition that could drift.

The key is read from settings, never logged, and redacted from any upstream
error text before that text is classified.
"""

from __future__ import annotations

import asyncio
import time

from app.core.config import get_settings
from app.models.errors import (
    ModelError,
    ModelNotConfiguredError,
    ModelResponseError,
    ModelTimeoutError,
    make_error,
    redact,
)
from app.models.payload import DocumentPayload
from app.models.prompts import SYSTEM_PROMPT, build_analysis_prompt, build_question_prompt
from app.models.provider import (
    AnalysisRequest,
    ModelProvider,
    QuestionRequest,
    parse_analysis,
    parse_answer,
)
from app.models.transport import ProviderDiagnosis, diagnose_message, log_call
from app.schemas.findings import ModelAnalysis, ModelAnswer


class GeminiProvider(ModelProvider):
    """Document understanding and Q&A through the Gemini API."""

    name = "gemini"

    def __init__(self, **overrides):
        self._settings = get_settings()
        self._overrides = overrides
        self._client = None  # built lazily, off the event loop

    # --- Configuration ---------------------------------------------------
    @property
    def is_configured(self) -> bool:
        return bool(self._settings.gemini_api_key) and bool(self._settings.gemini_model)

    @property
    def model_id(self) -> str:
        return self._settings.gemini_model or ""

    def _build_client(self):
        """Construct the SDK client, or raise if we cannot."""
        if not self.is_configured:
            raise make_error(ModelNotConfiguredError)

        from google import genai
        from google.genai import types

        settings = self._settings
        return genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                # Milliseconds. A socket-level bound under the asyncio deadline,
                # so an abandoned request does not hold a connection forever.
                timeout=settings.model_timeout_seconds * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    async def _resolve_client(self):
        """The client, built off the event loop on first use.

        As in `NemotronProvider`: the worker thread only returns the client and
        it is stored here, after the await, so a build that outlives the
        deadline publishes nothing.
        """
        if self._client is None:
            self._client = await asyncio.to_thread(self._build_client)
        return self._client

    def _config(self):
        from google.genai import types

        settings = self._settings
        parameters = {
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "temperature": settings.model_temperature,
            "top_p": settings.model_top_p,
            "max_output_tokens": settings.model_max_output_tokens,
            **self._overrides,
        }
        return types.GenerateContentConfig(**parameters)

    # --- Requests ---------------------------------------------------------
    async def analyze_document(self, request: AnalysisRequest) -> ModelAnalysis:
        raw = await self._invoke(
            build_analysis_prompt(request.payload, language=request.language),
            operation="analyze",
            payload=request.payload,
        )
        return parse_analysis(raw)

    async def answer_question(self, request: QuestionRequest) -> ModelAnswer:
        raw = await self._invoke(
            build_question_prompt(request.payload, request.question, language=request.language),
            operation="ask",
            payload=request.payload,
        )
        return parse_answer(raw)

    # --- Transport --------------------------------------------------------
    async def _invoke(self, user_prompt: str, *, operation: str, payload: DocumentPayload) -> str:
        """One request, one deadline, no retry."""
        if not self.is_configured:
            raise make_error(ModelNotConfiguredError)

        started = time.perf_counter()
        built = self._client is not None
        try:
            async with asyncio.timeout(self._settings.model_timeout_seconds):
                client = await self._resolve_client()
                built = True
                response = await client.aio.models.generate_content(
                    model=self.model_id,
                    contents=user_prompt,
                    config=self._config(),
                )
        except TimeoutError as exc:
            reason = "timeout" if built else "construction_timeout"
            self._log(operation, payload, started, "timeout", reason=reason)
            raise make_error(ModelTimeoutError, detail=reason) from exc
        except ModelError:
            raise
        except Exception as exc:
            found = self._diagnose(exc)
            self._log(
                operation,
                payload,
                started,
                str(found.error.__name__),
                reason=found.reason,
                http_status=found.status if found.status is not None else "none",
                upstream=type(exc).__name__,
            )
            raise make_error(found.error, detail=found.reason) from exc

        text = _response_text(response)
        self._log(operation, payload, started, "ok", chars=len(text))
        return text

    def _diagnose(self, exc: Exception) -> ProviderDiagnosis:
        """Classify an upstream failure on its redacted text.

        `google.genai.errors.APIError` carries the HTTP code as `.code` and the
        canonical status (e.g. RESOURCE_EXHAUSTED) as `.status`. Transport
        failures arrive as httpx exceptions, whose class name ("ConnectError",
        "ReadTimeout") is part of the classified text.
        """
        code = getattr(exc, "code", None)
        status = code if isinstance(code, int) else None
        text = " ".join(
            str(part)
            for part in (type(exc).__name__, getattr(exc, "status", "") or "", str(exc))
            if part
        )
        message = redact(text, self._settings.gemini_api_key).lower()
        return diagnose_message(message, status)

    def _log(self, operation: str, payload: DocumentPayload, started: float, outcome: str, **extra):
        log_call(__name__, self.name, operation, payload, started, outcome, **extra)


def _response_text(response) -> str:
    """The reply's text, or a response error if there is none.

    `response.text` is None when generation was blocked or produced no text
    part; that is an unusable reply, not an empty analysis.
    """
    try:
        text = getattr(response, "text", None)
    except Exception as exc:  # the SDK raises on some blocked candidates
        raise make_error(ModelResponseError, detail="unreadable_content") from exc
    if not isinstance(text, str) or not text.strip():
        raise make_error(ModelResponseError, detail="empty_response")
    return text
