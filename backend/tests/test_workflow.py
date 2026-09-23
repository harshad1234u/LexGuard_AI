"""Phase 7: the controlled analysis workflow.

Test architecture, deliberately:

    fake model -> REAL workflow -> REAL Phase 5 verifier -> REAL output gate

The verifier is never mocked and never adjusted to make a test pass. A fake
provider supplies the proposals a model might make - including dishonest ones -
and the real machinery decides what survives.

No test here reaches NVIDIA.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents.graph import (
    COVERAGE_GATE,
    DOCUMENT_MAP,
    MODEL,
    NODE_SEQUENCE,
    OUTPUT_GATE,
    build_graph,
)
from app.agents.nodes import build_result
from app.agents.state import AnalysisState
from app.core.config import get_settings
from app.documents.storage import document_store
from app.documents.validation import validate_upload
from app.models.errors import (
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
    ModelUnavailableError,
    make_error,
)
from app.models.provider import ModelProvider, parse_analysis
from app.schemas.analysis import AnalysisStage, ErrorCategory
from app.schemas.findings import ModelAnalysis, VerificationStatus
from tests.conftest import make_pdf, make_pdf_with_image_only_page

PAGE_TEXT = (
    "SERVICES AGREEMENT\n"
    "2. Termination. Either party may terminate this agreement by providing "
    "30 days' written notice.\n"
)

TRUE_FINDING = {
    "type": "termination",
    "claim": "Either party may terminate with 30 days' written notice.",
    "evidence": {"page": 1, "section": "Termination", "quote": "30 days' written notice"},
    "explanation": "Either side can end the agreement with a month's notice.",
    "attention": "review",
}


def finding(**overrides) -> dict:
    merged = {**TRUE_FINDING, **overrides}
    if "evidence" in overrides:
        merged["evidence"] = {**TRUE_FINDING["evidence"], **overrides["evidence"]}
    return merged


class FakeProvider(ModelProvider):
    """A model that says whatever the test tells it to.

    Records every call, so a test can prove the provider was never reached.
    """

    name = "fake"

    def __init__(self, findings: list[dict] | None = None, raises: Exception | None = None,
                 raw: str | None = None, delay: float = 0.0):
        self._findings = findings if findings is not None else [TRUE_FINDING]
        self._raises = raises
        self._raw = raw
        self._delay = delay
        self.calls: list = []

    @property
    def is_configured(self) -> bool:
        return True

    async def analyze_document(self, request):
        self.calls.append(request)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        if self._raw is not None:
            return parse_analysis(self._raw)
        import json

        return ModelAnalysis.model_validate({"findings": self._findings})

    async def answer_question(self, request):  # pragma: no cover - not used in Phase 7
        raise NotImplementedError


def store_document(content: bytes):
    validated = validate_upload(
        filename="contract.pdf", content_type="application/pdf", content=content
    )
    return document_store.create(validated, content)


def single_page_pdf(text: str = PAGE_TEXT) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


async def run_workflow(record, provider: ModelProvider) -> AnalysisState:
    return await build_graph(provider).ainvoke(
        AnalysisState(
            analysis_id="an_test",
            document_id=record.document_id,
            stage=AnalysisStage.QUEUED,
        )
    )


# --- Topology ---------------------------------------------------------------
class TestGraphTopology:
    def test_node_order_matches_the_specified_workflow(self):
        assert NODE_SEQUENCE == [
            "validate",
            "ingest",
            "coverage_gate",
            "document_map",
            "model",
            "verify",
            "output_gate",
        ]

    def test_graph_contains_every_node(self):
        graph = build_graph(FakeProvider())
        nodes = set(graph.get_graph().nodes)
        for name in NODE_SEQUENCE:
            assert name in nodes

    def test_coverage_gate_precedes_the_model_node(self):
        """There must be no edge reaching the model that bypasses the gate."""
        graph = build_graph(FakeProvider())
        edges = [(e.source, e.target) for e in graph.get_graph().edges]

        into_model = [source for source, target in edges if target == MODEL]
        assert into_model == [DOCUMENT_MAP]

        into_map = [source for source, target in edges if target == DOCUMENT_MAP]
        assert into_map == [COVERAGE_GATE]

    def test_graph_imports_no_vendor_class(self):
        """The workflow depends on ModelProvider, not on NemotronProvider."""
        import pathlib

        for name in ["graph.py", "nodes.py", "state.py"]:
            source = (pathlib.Path("app/agents") / name).read_text()
            assert "NemotronProvider" not in source
            assert "ChatNVIDIA" not in source
            assert "nvidia" not in source.lower()


# --- Happy path --------------------------------------------------------------
class TestSuccessfulRun:
    async def test_grounded_finding_reaches_the_output_gate(self):
        record = store_document(single_page_pdf())
        provider = FakeProvider()

        state = await run_workflow(record, provider)

        assert state["stage"] is AnalysisStage.DONE
        assert not state.get("error_category")
        assert state["proposed_count"] == 1
        assert state["displayable_count"] == 1
        assert state["withheld_count"] == 0

        result = build_result(state)
        assert len(result.findings) == 1
        assert result.findings[0].verification_status is VerificationStatus.VERIFIED
        assert result.insufficient_evidence is False

    async def test_result_reports_the_coverage_it_acted_on(self):
        record = store_document(make_pdf(pages=4))
        state = await run_workflow(record, FakeProvider(findings=[]))

        assert state["coverage"].expected_pages == 4
        assert state["coverage"].processed_pages == 4
        assert build_result(state).coverage.status == "complete"

    async def test_every_page_is_supplied_to_the_model(self):
        record = store_document(make_pdf(pages=6))
        provider = FakeProvider(findings=[])

        state = await run_workflow(record, provider)

        assert state["supplied_pages"] == [1, 2, 3, 4, 5, 6]
        payload = provider.calls[0].payload
        assert payload.supplied_page_numbers == [1, 2, 3, 4, 5, 6]
        # Page identity survives into the prompt.
        assert "<<<PAGE 6>>>" in payload.render()

    async def test_no_findings_is_not_insufficient_evidence(self):
        """A document with nothing to report differs from one whose claims failed."""
        record = store_document(make_pdf(pages=2))
        state = await run_workflow(record, FakeProvider(findings=[]))

        result = build_result(state)
        assert result.findings == []
        assert result.insufficient_evidence is False


# --- The gate ------------------------------------------------------------------
class TestCoverageGateBlocksTheModel:
    """The central integrity invariant of this phase."""

    async def test_repaired_pdf_never_reaches_the_provider(self):
        content = make_pdf(pages=6)
        record = store_document(content[: len(content) // 3])
        assert record.is_repaired is True

        provider = FakeProvider()
        state = await run_workflow(record, provider)

        assert provider.calls == [], "the model was called for a repaired document"
        assert state["coverage_complete"] is False
        assert state["error_category"] is ErrorCategory.COVERAGE_ERROR
        assert state["stage"] is AnalysisStage.CHECKING_COVERAGE

    async def test_unreadable_page_never_reaches_the_provider(self):
        record = store_document(make_pdf_with_image_only_page(total=3, image_page=2))

        provider = FakeProvider()
        state = await run_workflow(record, provider)

        assert provider.calls == []
        assert state["error_category"] is ErrorCategory.COVERAGE_ERROR
        assert state["coverage"].unreadable_pages == [2]

    async def test_failed_extraction_never_reaches_the_provider(self):
        record = store_document(make_pdf(pages=3))
        record.source_path.write_bytes(b"corrupted after validation")

        provider = FakeProvider()
        state = await run_workflow(record, provider)

        assert provider.calls == []
        assert state["error_category"] is ErrorCategory.COVERAGE_ERROR

    async def test_blocked_run_never_reports_done(self):
        content = make_pdf(pages=6)
        record = store_document(content[: len(content) // 3])
        state = await run_workflow(record, FakeProvider())
        assert state["stage"] is not AnalysisStage.DONE


# --- Verification is not optional --------------------------------------------------
class TestModelOutputCannotBypassVerification:
    async def test_invalid_page_citation_is_withheld(self):
        record = store_document(single_page_pdf())
        provider = FakeProvider(findings=[finding(evidence={"page": 99})])

        state = await run_workflow(record, provider)
        result = build_result(state)

        assert result.findings == []
        assert result.withheld.rejected == 1
        assert result.insufficient_evidence is True

    async def test_fabricated_quote_is_withheld(self):
        record = store_document(single_page_pdf())
        provider = FakeProvider(
            findings=[finding(evidence={"quote": "arbitration shall be seated in Paris"})]
        )

        result = build_result(await run_workflow(record, provider))
        assert result.findings == []
        assert result.withheld.rejected == 1

    async def test_numeric_mismatch_is_withheld(self):
        """Real quote, claim that misstates it."""
        record = store_document(single_page_pdf())
        provider = FakeProvider(
            findings=[finding(claim="Either party may terminate with 60 days' notice.")]
        )

        result = build_result(await run_workflow(record, provider))
        assert result.findings == []
        assert result.withheld.rejected == 1

    async def test_missing_evidence_is_withheld_as_unverified(self):
        record = store_document(single_page_pdf())
        provider = FakeProvider(
            findings=[{"type": "termination", "claim": "Notice is 30 days.", "evidence": None}]
        )

        result = build_result(await run_workflow(record, provider))
        assert result.findings == []
        assert result.withheld.unverified == 1

    async def test_good_and_bad_findings_are_separated(self):
        record = store_document(single_page_pdf())
        provider = FakeProvider(
            findings=[
                TRUE_FINDING,
                finding(claim="Either party may terminate with 60 days' notice."),
                finding(evidence={"page": 99}),
            ]
        )

        result = build_result(await run_workflow(record, provider))

        assert len(result.findings) == 1
        assert result.findings[0].claim == TRUE_FINDING["claim"]
        assert result.withheld.total == 2
        assert result.insufficient_evidence is False

    async def test_no_withheld_finding_appears_in_the_output(self):
        record = store_document(single_page_pdf())
        provider = FakeProvider(
            findings=[finding(claim="Either party may terminate with 60 days' notice.")]
        )

        result = build_result(await run_workflow(record, provider))
        rendered = result.model_dump_json()

        assert "60 days" not in rendered

    async def test_output_gate_reapplies_the_rule_rather_than_trusting_counts(self):
        """build_result must not rely on a count computed by an earlier node."""
        record = store_document(single_page_pdf())
        state = await run_workflow(record, FakeProvider())

        state["displayable_count"] = 99  # a lie from upstream
        assert len(build_result(state).findings) == 1


# --- Provider failures -----------------------------------------------------------
class TestProviderFailures:
    @pytest.mark.parametrize(
        "error,category",
        [
            (make_error(ModelUnavailableError), ErrorCategory.PROVIDER_UNAVAILABLE),
            (make_error(ModelTimeoutError), ErrorCategory.PROVIDER_TIMEOUT),
            (make_error(ModelRateLimitError), ErrorCategory.PROVIDER_RATE_LIMITED),
            (make_error(ModelResponseError), ErrorCategory.MODEL_OUTPUT_INVALID),
        ],
    )
    async def test_provider_errors_become_terminal_categories(self, error, category):
        record = store_document(single_page_pdf())
        state = await run_workflow(record, FakeProvider(raises=error))

        assert state["error_category"] is category
        assert state["stage"] is AnalysisStage.ANALYZING
        assert state["stage"] is not AnalysisStage.DONE

    async def test_malformed_model_output_is_terminal(self):
        record = store_document(single_page_pdf())
        state = await run_workflow(record, FakeProvider(raw="this is not json at all"))

        assert state["error_category"] is ErrorCategory.MODEL_OUTPUT_INVALID

    async def test_unexpected_provider_exception_is_contained(self):
        record = store_document(single_page_pdf())
        state = await run_workflow(record, FakeProvider(raises=RuntimeError("boom")))

        assert state["error_category"] is ErrorCategory.INTERNAL_ERROR
        assert "boom" not in (state.get("error_message") or "")

    async def test_provider_failure_produces_no_findings(self):
        record = store_document(single_page_pdf())
        state = await run_workflow(record, FakeProvider(raises=make_error(ModelUnavailableError)))
        assert build_result(state).findings == []

    async def test_no_automatic_retry(self):
        record = store_document(single_page_pdf())
        provider = FakeProvider(raises=make_error(ModelRateLimitError))

        await run_workflow(record, provider)
        assert len(provider.calls) == 1


# --- Validation ---------------------------------------------------------------------
class TestValidationNode:
    async def test_missing_document_fails_before_the_provider(self):
        record = store_document(single_page_pdf())
        document_id = record.document_id
        document_store.delete(document_id)

        provider = FakeProvider()
        state = await build_graph(provider).ainvoke(
            AnalysisState(analysis_id="an_x", document_id=document_id,
                          stage=AnalysisStage.QUEUED)
        )

        assert provider.calls == []
        assert state["error_category"] is ErrorCategory.VALIDATION_ERROR


# --- Logging discipline -----------------------------------------------------------------
class TestLogging:
    async def test_logs_carry_metadata_not_document_text(self, caplog):
        secret = "Confidential indemnity provision binding the Supplier"
        record = store_document(single_page_pdf(f"1. Terms. {secret}."))

        with caplog.at_level("DEBUG"):
            await run_workflow(record, FakeProvider(findings=[]))

        assert "indemnity" not in caplog.text.lower()
        assert "nvapi" not in caplog.text
        # Metadata is present.
        assert record.document_id in caplog.text
        assert "coverage_passed" in caplog.text

    async def test_model_claims_and_quotes_are_not_logged(self, caplog):
        record = store_document(single_page_pdf())

        with caplog.at_level("DEBUG"):
            await run_workflow(record, FakeProvider())

        assert "30 days' written notice" not in caplog.text

    async def test_api_keys_are_not_logged(self, caplog, monkeypatch):
        """The configured key must not reach a log on any path."""
        canary = "nvapi-canary-must-never-be-logged-0123456789"
        monkeypatch.setenv("NVIDIA_API_KEY", canary)
        get_settings.cache_clear()
        record = store_document(single_page_pdf())

        with caplog.at_level("DEBUG"):
            await run_workflow(record, FakeProvider())

        assert canary not in caplog.text
        assert "nvapi-" not in caplog.text

    async def test_a_provider_error_echoing_the_key_does_not_log_it(
        self, caplog, monkeypatch
    ):
        """A client library's exception text is outside our control.

        If one echoes the request it was given - key included - the workflow
        must still not put it in a log. Nothing but the category is recorded.
        """
        canary = "nvapi-canary-must-never-be-logged-0123456789"
        monkeypatch.setenv("NVIDIA_API_KEY", canary)
        get_settings.cache_clear()
        record = store_document(single_page_pdf())
        leaky = RuntimeError(f"POST /v1/chat failed with Authorization: Bearer {canary}")

        with caplog.at_level("DEBUG"):
            state = await run_workflow(record, FakeProvider(raises=leaky))

        assert state["error_category"] is ErrorCategory.INTERNAL_ERROR
        assert canary not in caplog.text
        assert canary not in (state.get("error_message") or "")


# --- Verification failure -----------------------------------------------------------------
class TestVerificationFailure:
    """The verifier itself is never mocked to change a verdict.

    What is forced here is a *fault* in the verification node - the one case
    the real verifier cannot be made to produce - to prove the workflow
    contains it rather than continuing to a gate with unchecked findings.
    """

    async def test_verification_error_is_a_terminal_failure(self, monkeypatch):
        record = store_document(single_page_pdf())

        def explode(*_args, **_kwargs):
            raise RuntimeError("verifier exploded")

        monkeypatch.setattr("app.agents.nodes.verify_analysis_claims", explode)
        state = await run_workflow(record, FakeProvider())

        assert state["error_category"] is ErrorCategory.VERIFICATION_ERROR
        assert state["stage"] is not AnalysisStage.DONE
        assert "exploded" not in (state.get("error_message") or "")

    async def test_verification_failure_produces_no_findings(self, monkeypatch):
        record = store_document(single_page_pdf())

        def explode(*_args, **_kwargs):
            raise RuntimeError("verifier exploded")

        monkeypatch.setattr("app.agents.nodes.verify_analysis_claims", explode)
        state = await run_workflow(record, FakeProvider())

        # Nothing was verified, so the gate has nothing it could display.
        assert state.get("verified_findings", []) == []
        assert build_result(state).findings == []
