"""Phase 23: the Gemini provider, against a stub SDK client.

No test here reaches Google. The stub stands in for `genai.Client`, and the
errors are the SDK's own exception classes, so classification is tested
against what the SDK actually raises.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import time

import httpx
import pytest
from google.genai import errors as genai_errors

from app.core.config import get_settings
from app.models.errors import (
    ModelAuthError,
    ModelNotFoundError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from app.models.gemini import GeminiProvider
from app.models.payload import DocumentPage, DocumentPayload
from app.models.prompts import build_analysis_prompt, build_question_prompt
from app.models.provider import AnalysisRequest, QuestionRequest
from app.models.transport import ProviderFailureKind, failure_kind
from tests.test_workflow import TRUE_FINDING

KEY = "AIza-canary-gemini-phase23-do-not-leak"


@pytest.fixture(autouse=True)
def gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setenv("MODEL_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def payload() -> DocumentPayload:
    return DocumentPayload(
        document_id="doc_gemini",
        total_pages=1,
        pages=[DocumentPage(page_number=1, text="Either party may terminate on 30 days' written notice.")],
    )


class _Response:
    def __init__(self, text):
        self._text = text

    @property
    def text(self):
        if isinstance(self._text, Exception):
            raise self._text
        return self._text


class StubClient:
    """Mimics `client.aio.models.generate_content`. Records every call."""

    def __init__(self, reply=None, raises=None, delay=0.0):
        self.reply, self.raises, self.delay = reply, raises, delay
        self.calls = []
        outer = self

        class _Models:
            async def generate_content(self, *, model, contents, config):
                outer.calls.append({"model": model, "contents": contents, "config": config})
                if outer.delay:
                    await asyncio.sleep(outer.delay)
                if outer.raises is not None:
                    raise outer.raises
                return _Response(outer.reply)

        class _Aio:
            models = _Models()

        self.aio = _Aio()


def provider_with(monkeypatch, client) -> GeminiProvider:
    monkeypatch.setattr(GeminiProvider, "_build_client", lambda self: client)
    return GeminiProvider()


class TestParsing:
    async def test_a_valid_reply_becomes_a_proposal(self, monkeypatch, payload):
        client = StubClient(reply=json.dumps({"findings": [TRUE_FINDING]}))
        result = await provider_with(monkeypatch, client).analyze_document(
            AnalysisRequest(payload=payload)
        )
        assert len(result.findings) == 1
        assert client.calls[0]["model"] == "gemini-test-model"
        assert client.calls[0]["config"].response_mime_type == "application/json"

    async def test_a_fenced_reply_is_accepted(self, monkeypatch, payload):
        raw = "```json\n" + json.dumps({"findings": [TRUE_FINDING]}) + "\n```"
        result = await provider_with(monkeypatch, StubClient(reply=raw)).analyze_document(
            AnalysisRequest(payload=payload)
        )
        assert len(result.findings) == 1

    @pytest.mark.parametrize(
        "reply,kind",
        [
            ("this is not json", ProviderFailureKind.INVALID_RESPONSE),
            ("", ProviderFailureKind.INVALID_RESPONSE),
            (None, ProviderFailureKind.INVALID_RESPONSE),
            (ValueError("blocked candidate"), ProviderFailureKind.INVALID_RESPONSE),
            (json.dumps({"findings": [{**TRUE_FINDING, "attention": "catastrophic"}]}),
             ProviderFailureKind.SCHEMA_INVALID),
            (json.dumps({"findings": [{**TRUE_FINDING, "kind": "certainty"}]}),
             ProviderFailureKind.SCHEMA_INVALID),
            (json.dumps({"findings": [{**TRUE_FINDING, "explanation_translation": "x" * 5000}]}),
             ProviderFailureKind.SCHEMA_INVALID),
        ],
    )
    async def test_unusable_replies_are_errors_not_partial_results(
        self, monkeypatch, payload, reply, kind
    ):
        with pytest.raises(ModelResponseError) as caught:
            await provider_with(monkeypatch, StubClient(reply=reply)).analyze_document(
                AnalysisRequest(payload=payload)
            )
        assert failure_kind(caught.value) is kind

    async def test_answers_parse_through_the_same_schema(self, monkeypatch, payload):
        answer = {"answer": "Thirty days.", "evidence": [], "not_found": False}
        result = await provider_with(
            monkeypatch, StubClient(reply=json.dumps(answer))
        ).answer_question(QuestionRequest(payload=payload, question="Notice?"))
        assert result.answer == "Thirty days."


def api_error(code: int, status: str, message: str):
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, {"error": {"code": code, "status": status, "message": message}})


class TestFailureClassification:
    @pytest.mark.parametrize(
        "raised,error,kind",
        [
            (api_error(401, "UNAUTHENTICATED", "API key not valid"), ModelAuthError,
             ProviderFailureKind.AUTH),
            (api_error(403, "PERMISSION_DENIED", "denied"), ModelAuthError,
             ProviderFailureKind.AUTH),
            (api_error(404, "NOT_FOUND", "models/x is not found"), ModelNotFoundError,
             ProviderFailureKind.CONFIGURATION),
            (api_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded"), ModelRateLimitError,
             ProviderFailureKind.RATE_LIMIT),
            (api_error(503, "UNAVAILABLE", "The model is overloaded"), ModelUnavailableError,
             ProviderFailureKind.CAPACITY),
            (api_error(500, "INTERNAL", "internal"), ModelUnavailableError,
             ProviderFailureKind.CAPACITY),
            (httpx.ConnectError("connection refused"), ModelUnavailableError,
             ProviderFailureKind.NETWORK),
            (httpx.ReadTimeout("read timed out"), ModelTimeoutError,
             ProviderFailureKind.TIMEOUT),
            (RuntimeError("something new"), ModelUnavailableError,
             ProviderFailureKind.UNKNOWN),
        ],
    )
    async def test_each_upstream_failure_maps_to_one_kind(
        self, monkeypatch, payload, raised, error, kind
    ):
        with pytest.raises(error) as caught:
            await provider_with(monkeypatch, StubClient(raises=raised)).analyze_document(
                AnalysisRequest(payload=payload)
            )
        assert failure_kind(caught.value) is kind

    async def test_a_key_in_an_upstream_error_is_redacted_everywhere(
        self, monkeypatch, payload, caplog
    ):
        leaky = api_error(400, "INVALID_ARGUMENT", f"bad request for key={KEY}")
        with caplog.at_level(logging.INFO):
            with pytest.raises(Exception) as caught:
                await provider_with(monkeypatch, StubClient(raises=leaky)).analyze_document(
                    AnalysisRequest(payload=payload)
                )
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert KEY not in text
        assert KEY not in str(caught.value.to_payload())

    async def test_logs_carry_no_prompt_and_no_document_text(self, monkeypatch, payload, caplog):
        client = StubClient(reply=json.dumps({"findings": []}))
        with caplog.at_level(logging.DEBUG):
            await provider_with(monkeypatch, client).analyze_document(
                AnalysisRequest(payload=payload)
            )
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "written notice" not in text
        assert "outcome=ok" in text and "provider=gemini" in text

    async def test_there_is_exactly_one_attempt(self, monkeypatch, payload):
        client = StubClient(raises=api_error(503, "UNAVAILABLE", "overloaded"))
        with pytest.raises(ModelUnavailableError):
            await provider_with(monkeypatch, client).analyze_document(
                AnalysisRequest(payload=payload)
            )
        assert len(client.calls) == 1


class TestDeadlines:
    async def test_a_hanging_call_times_out_with_a_responsive_loop(self, monkeypatch, payload):
        client = StubClient(reply="{}", delay=30)
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        began = time.perf_counter()
        with pytest.raises(ModelTimeoutError) as caught:
            await provider_with(monkeypatch, client).analyze_document(
                AnalysisRequest(payload=payload)
            )
        beat.cancel()
        assert time.perf_counter() - began < 3
        assert ticks >= 10, "the event loop stalled during the call"
        assert failure_kind(caught.value) is ProviderFailureKind.TIMEOUT

    async def test_a_hanging_construction_is_a_construction_timeout_off_the_loop(
        self, monkeypatch, payload
    ):
        gate = threading.Event()

        def stuck_build(self):
            gate.wait(10)
            return StubClient(reply="{}")

        monkeypatch.setattr(GeminiProvider, "_build_client", stuck_build)
        provider = GeminiProvider()
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        with pytest.raises(ModelTimeoutError) as caught:
            await provider.analyze_document(AnalysisRequest(payload=payload))
        beat.cancel()
        gate.set()
        assert ticks >= 10
        assert failure_kind(caught.value) is ProviderFailureKind.CONSTRUCTION_TIMEOUT
        assert provider._client is None, "an abandoned build must publish nothing"

    def test_constructing_the_real_sdk_client_makes_no_network_call(self, monkeypatch):
        def refuse(*_, **__):
            raise AssertionError("network used during client construction")

        monkeypatch.setattr(socket, "create_connection", refuse)
        monkeypatch.setattr(socket.socket, "connect", refuse)
        client = GeminiProvider()._build_client()
        assert client is not None


class TestPrompts:
    def test_english_prompts_are_unchanged_by_phase_23(self, payload):
        assert build_analysis_prompt(payload) == build_analysis_prompt(payload, "en")
        assert "Tamil" not in build_analysis_prompt(payload)
        assert "translation" not in build_question_prompt(payload, "Q?")

    def test_a_tamil_request_asks_for_a_translation_only(self, payload):
        prompt = build_analysis_prompt(payload, "ta")
        assert "explanation_translation" in prompt and "Tamil" in prompt
        # The untrusted-content fence is intact and still last.
        assert prompt.index("explanation_translation") < prompt.index("BEGIN UNTRUSTED")
        question = build_question_prompt(payload, "When?", "ta")
        assert "answer_translation" in question
        assert question.rstrip().endswith("When?")

    async def test_the_requested_language_reaches_the_prompt(self, monkeypatch, payload):
        client = StubClient(reply=json.dumps({"findings": []}))
        await provider_with(monkeypatch, client).analyze_document(
            AnalysisRequest(payload=payload, language="ta")
        )
        assert "Tamil" in client.calls[0]["contents"]


# --- Invariant 1: no Gemini output reaches a response unverified -------------------

ADVERSARIAL = [
    # Fabricated quote.
    {"id": "a1", "type": "liability", "claim": "The Supplier's liability is unlimited.",
     "evidence": {"page": 1, "quote": "liability is unlimited"}},
    # Polarity flip over a real quote.
    {"id": "a2", "type": "termination", "claim": "Neither party may terminate this agreement.",
     "evidence": {"page": 1, "quote": "Either party may terminate this agreement"}},
    # Wrong figure over a real quote.
    {"id": "a3", "type": "termination", "claim": "Either party may terminate with 45 days' written notice.",
     "evidence": {"page": 1, "quote": "30 days' written notice"}},
    # Role reversal over a real quote.
    {"id": "a4", "type": "payment", "claim": "The Supplier shall pay GBP 5,000 per month.",
     "evidence": {"page": 1, "quote": "The Client shall pay GBP 5,000 per month"}},
    # Invented page.
    {"id": "a5", "type": "termination", "claim": "Either party may terminate with 30 days' written notice.",
     "evidence": {"page": 7, "quote": "30 days' written notice"}},
]
TRUE_ONE = {"id": "ok", "type": "payment", "claim": "The Client shall pay GBP 5,000 per month.",
            "evidence": {"page": 1, "quote": "The Client shall pay GBP 5,000 per month"}}


class TestNoGeminiOutputBypassesVerification:
    async def test_adversarial_gemini_findings_are_all_withheld(self, monkeypatch):
        from app.agents.graph import build_graph
        from app.agents.nodes import build_result
        from app.agents.state import AnalysisState
        from app.schemas.analysis import AnalysisStage
        from tests.test_reasoning_helpers import CONTRACT
        from tests.test_workflow import single_page_pdf, store_document

        client = StubClient(reply=json.dumps({"findings": ADVERSARIAL + [TRUE_ONE]}))
        provider = provider_with(monkeypatch, client)
        record = store_document(single_page_pdf(CONTRACT))
        state = await build_graph(provider).ainvoke(
            AnalysisState(analysis_id="an_g", document_id=record.document_id,
                          stage=AnalysisStage.QUEUED, provider_name="gemini",
                          provider_model="gemini-test-model")
        )
        result = build_result(state)

        assert [f.id for f in result.findings] == ["ok"]
        assert result.withheld.total == len(ADVERSARIAL)
        dumped = result.model_dump_json()
        for item in ADVERSARIAL:
            assert item["claim"] not in dumped
        assert result.provenance.provider == "gemini"
        assert result.provenance.model == "gemini-test-model"

    def test_gemini_qa_with_fabricated_evidence_returns_the_not_found_text(
        self, client, monkeypatch
    ):
        from app.schemas.qa import NOT_FOUND_ANSWER
        from tests.conftest import upload
        from tests.test_api_qa import contract_pdf

        answer = {"answer": "The Supplier's liability is unlimited.",
                  "evidence": [{"page": 1, "quote": "liability is unlimited"}],
                  "not_found": False}
        stub = StubClient(reply=json.dumps(answer))
        monkeypatch.setattr(GeminiProvider, "_build_client", lambda self: stub)
        monkeypatch.setattr("app.api.v1.routes_qa._provider_factory", GeminiProvider)

        document_id = upload(client, contract_pdf()).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")
        response = client.post(f"/api/v1/documents/{document_id}/ask",
                               json={"question": "What is the liability cap?"})
        body = response.json()
        assert body["status"] == "not_found"
        assert body["answer"] == NOT_FOUND_ANSWER
        assert "unlimited" not in response.text
        assert body["provenance"]["provider"] == "gemini"
