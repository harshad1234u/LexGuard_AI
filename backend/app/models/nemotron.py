"""Nemotron, via the hosted NVIDIA Build / NIM API.

This is the only module in the application that knows NVIDIA exists. It runs
against the hosted endpoint - the model is never downloaded or served locally
(docs/09_DECISIONS.md).

The API key is read from settings, which read it from the environment. It is
never logged, never returned, and is stripped from any upstream error text
before that text goes anywhere.
"""

from __future__ import annotations

import asyncio
import time
import warnings

from app.core.config import get_settings
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
    make_error,
    redact,
)
from app.models.payload import DocumentPayload
from app.models.prompts import (
    SYSTEM_PROMPT,
    build_analysis_prompt,
    build_question_prompt,
)
from app.models.provider import (
    AnalysisRequest,
    ModelProvider,
    QuestionRequest,
    parse_analysis,
    parse_answer,
)
from app.models.reasoning import (
    REASONING_SYSTEM_PROMPT,
    ModelReasoning,
    ReasoningProvider,
    ReasoningRequest,
    build_reasoning_prompt,
    parse_reasoning,
)
from app.models.transport import (
    ProviderDiagnosis,
    diagnose_message,
    log_call,
    status_from_message,
)
from app.schemas.findings import ModelAnalysis, ModelAnswer

logger = get_logger(__name__)


class NemotronProvider(ModelProvider, ReasoningProvider):
    """Calls Nemotron through LangChain's NVIDIA integration."""

    name = "nemotron"

    def __init__(self, **overrides):
        self._settings = get_settings()
        self._overrides = overrides
        self._client = None  # built lazily; construction requires a key

    # --- Configuration ---------------------------------------------------
    @property
    def is_configured(self) -> bool:
        return bool(self._settings.nvidia_api_key)

    @property
    def model_id(self) -> str:
        return self._settings.nemotron_model

    def _build_client(self):
        """Construct the chat client, or raise if we cannot."""
        if not self.is_configured:
            raise make_error(ModelNotConfiguredError)

        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        settings = self._settings
        parameters = {
            "model": settings.nemotron_model,
            "api_key": settings.nvidia_api_key,
            "base_url": settings.nvidia_base_url,
            "temperature": settings.model_temperature,
            "top_p": settings.model_top_p,
            "max_tokens": settings.model_max_output_tokens,
            **self._overrides,
        }

        with warnings.catch_warnings():
            # The installed integration ships a static model table that predates
            # Nemotron 3 and warns that it cannot classify the model. The
            # identifier is confirmed present in the live catalogue, so the
            # warning is noise rather than a signal.
            warnings.filterwarnings("ignore", message=".*type is unknown.*")
            return ChatNVIDIA(**parameters)

    @property
    def client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def _resolve_client(self):
        """The client, built off the event loop on first use.

        The worker thread only returns the client; it is stored here, in the
        coroutine, after the await. A build that outlives the deadline is
        therefore abandoned with nothing to publish: its result is dropped and
        the next request builds afresh.
        """
        if self._client is None:
            self._client = await asyncio.to_thread(self._build_client)
        return self._client

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

    async def reason_about_findings(self, request: ReasoningRequest) -> ModelReasoning:
        """Phase 23 reasoning notes over released findings. Proposals only."""
        raw = await self._invoke(
            build_reasoning_prompt(request),
            operation="reason",
            payload=None,
            system_prompt=REASONING_SYSTEM_PROMPT,
            timeout=self._settings.reasoning_timeout_seconds,
        )
        return parse_reasoning(raw)

    # --- Transport --------------------------------------------------------
    async def _invoke(
        self,
        user_prompt: str,
        *,
        operation: str,
        payload: DocumentPayload | None,
        system_prompt: str = SYSTEM_PROMPT,
        timeout: int | None = None,
    ) -> str:
        """One request, with a timeout and no automatic retry.

        Retries are deliberately absent. A failed analysis is cheap to ask for
        again explicitly; a silent retry loop burns a metered API and can turn
        one rate-limit into several (docs/03_AI_AGENT_SPEC.md sec. 8).
        """
        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]

        # Checked before the try block: a configuration failure is ours, not
        # the network's, and must not be reclassified as "temporarily
        # unavailable" by the handler below.
        if not self.is_configured:
            raise make_error(ModelNotConfiguredError)

        started = time.perf_counter()
        built = self._client is not None
        try:
            # One deadline covers building the client and calling it. Building
            # is not free: the integration lists the hosted models over a
            # blocking HTTP request with no socket timeout, and run on the
            # event loop that request froze the whole server - both timeouts
            # included - for as long as the upstream held it (Phase 22).
            async with asyncio.timeout(timeout or self._settings.model_timeout_seconds):
                client = await self._resolve_client()
                built = True
                response = await client.ainvoke(messages)
        except TimeoutError as exc:
            # Which half of the shared deadline ran out: a client that was never
            # built is the Phase 22 failure, and is worth telling apart.
            reason = "timeout" if built else "construction_timeout"
            self._log(operation, payload, started, "timeout", reason=reason)
            raise make_error(ModelTimeoutError, detail=reason) from exc
        except ModelError:
            # Already one of ours, already safe. Do not re-wrap.
            raise
        except Exception as exc:
            found = self._diagnose(exc)
            # `reason` and `http_status` are what make a failure diagnosable
            # afterwards; the error class alone does not identify the cause.
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

    def _classify(self, exc: Exception) -> type:
        """Map an upstream failure onto an application error class."""
        return self._diagnose(exc).error

    def _diagnose(self, exc: Exception) -> ProviderDiagnosis:
        """Classify an upstream failure and record *why* it was classified so.

        Matches on the redacted message so a key embedded in an error string
        cannot influence - or survive - classification.

        The `reason` exists because the error class alone is not a diagnosis.
        Six distinct upstream conditions collapse into `ModelUnavailableError`,
        and a log that records only the class cannot tell a capacity limit from
        a DNS failure from an exception this code has never seen. That
        distinction is exactly what was missing when a live 503 had to be
        investigated after the fact, so it is recorded here - as a fixed
        vocabulary, never as the upstream message, which can echo the document.
        """
        message = redact(str(exc), self._settings.nvidia_api_key).lower()
        status = getattr(getattr(exc, "response", None), "status_code", None)
        # The NVIDIA integration raises a bare Exception with the error body
        # interpolated into the message and no `.response` attached, so the
        # status is recovered from the text inside `diagnose_message`.
        return diagnose_message(message, status)

    def _log(
        self, operation: str, payload: DocumentPayload | None, started: float, outcome: str, **extra
    ):
        """Metadata only. No prompt, no document text, no key, no response body."""
        log_call(__name__, self.name, operation, payload, started, outcome, **extra)


#: Kept importable from here for existing callers.
_status_from_message = status_from_message
__all__ = ["NemotronProvider", "ProviderDiagnosis"]


def _response_text(response) -> str:
    """Extract text from a LangChain message, whatever shape its content takes."""
    content = getattr(response, "content", response)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        # Multimodal responses arrive as a list of parts.
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        ]
        return "".join(parts)

    raise make_error(ModelResponseError, detail="unreadable_content")
