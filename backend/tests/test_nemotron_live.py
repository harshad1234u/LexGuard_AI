"""The one live Nemotron call in this project.

Deselected by default (`addopts = -m "not live"`); run deliberately with:

    pytest -m live

It exists to prove the seam works end to end - authentication, model identifier,
structured output, and the handoff into the Phase 5 verifier - not to measure
the model. There is no benchmark here and no retry: a failed call is diagnosed
from its error class, not by calling again (docs/06_EVALUATION_PLAN.md).

The document below is three sentences written for this test. No real or private
legal document is ever sent from the test suite.
"""

from __future__ import annotations

import time

import pytest

from app.core.config import get_settings
from app.models.payload import DocumentPage, DocumentPayload
from app.models.provider import AnalysisRequest
from app.schemas.findings import ModelAnalysis, VerificationStatus
from app.verification.grounding import verify_finding

pytestmark = pytest.mark.live

#: A tiny, non-sensitive test document with one unambiguous numeric fact.
TEST_PAGE_TEXT = (
    "SERVICES AGREEMENT\n\n"
    "1. Term. This agreement begins on 1 January 2027.\n\n"
    "2. Termination. Either party may terminate this agreement by providing "
    "30 days' written notice.\n"
)


class LiveDocument:
    """The same source the model saw, for the verifier to check against."""

    page_count = 1

    def page_text(self, page_number: int) -> str | None:
        return TEST_PAGE_TEXT if page_number == 1 else None


@pytest.fixture(scope="module")
def live_payload() -> DocumentPayload:
    return DocumentPayload(
        document_id="doc_live_test",
        total_pages=1,
        pages=[DocumentPage(page_number=1, text=TEST_PAGE_TEXT)],
    )


async def test_live_nemotron_round_trip(live_payload, capsys):
    """One request: auth, model, structured output, then the real verifier."""
    get_settings.cache_clear()
    settings = get_settings()

    if not settings.model_configured:
        pytest.skip("NVIDIA_API_KEY is not configured")

    # Imported here so collecting this module never constructs a client.
    from app.models.nemotron import NemotronProvider

    provider = NemotronProvider()

    # Capacity on the hosted endpoint is not what this test is about. Phase 14
    # saw `503 ResourceExhausted: Worker local total request limit reached`
    # several times in a row, and a test that reports NVIDIA being busy as a
    # failure of this repository teaches people to ignore it. An auth failure,
    # a wrong model identifier or a malformed response still fails.
    from tests.test_nemotron_live_phase14 import call_or_skip

    started = time.perf_counter()
    analysis = await call_or_skip(
        provider.analyze_document(AnalysisRequest(payload=live_payload))
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    # 1-4. Reachable, authenticated, and the reply fits the schema.
    assert isinstance(analysis, ModelAnalysis)
    assert analysis.findings, "the model returned no findings for a document with clear clauses"

    # 5. Evidence fields are populated.
    grounded = [f for f in analysis.findings if f.evidence is not None]
    assert grounded, "no finding carried evidence"
    assert all(f.evidence.page >= 1 for f in grounded)
    assert all(f.evidence.quote.strip() for f in grounded)

    # 6. The proposal goes through the unmodified Phase 5 verifier.
    document = LiveDocument()
    results = [(f, verify_finding(f, document)) for f in analysis.findings]
    statuses = [r.status for _, r in results]

    with capsys.disabled():
        print(f"\n  model      : {settings.nemotron_model}")
        print(f"  latency_ms : {latency_ms}")
        print(f"  findings   : {len(analysis.findings)}")
        print(f"  statuses   : {[str(s) for s in statuses]}")
        for finding, result in results:
            print(
                f"    - {finding.type:<20} page={finding.evidence.page if finding.evidence else '-'} "
                f"status={result.status} reasons={[str(x) for x in result.reasons]}"
            )

    # At least one finding must survive verification against the real text.
    # This is the claim the phase is making: Nemotron -> structured finding ->
    # existing verifier -> verified.
    assert VerificationStatus.VERIFIED in statuses, (
        "no finding verified against the source document; "
        f"statuses were {[str(s) for s in statuses]}"
    )
