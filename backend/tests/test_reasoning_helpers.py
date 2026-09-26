"""Shared helper for Phase 23 tests that run the real workflow graph.

Not a test module (no `test_` functions): pytest collects it because of its
name, finds nothing, and moves on.
"""

from __future__ import annotations

from app.agents.graph import build_graph
from app.agents.nodes import build_result
from app.agents.state import AnalysisState
from app.schemas.analysis import AnalysisStage
from tests.test_workflow import FakeProvider, single_page_pdf, store_document

CONTRACT = (
    "SERVICES AGREEMENT\n"
    "2. Termination. Either party may terminate this agreement by providing "
    "30 days' written notice.\n"
    "3. Fees. The Client shall pay GBP 5,000 per month.\n"
)


async def run_analysis(findings, *, language="en", reasoner=None, text=CONTRACT):
    record = store_document(single_page_pdf(text))
    state = await build_graph(FakeProvider(findings=findings), reasoner).ainvoke(
        AnalysisState(
            analysis_id="an_p23",
            document_id=record.document_id,
            stage=AnalysisStage.QUEUED,
            provider_name="fake",
            provider_model="fake-model",
            language=language,
        )
    )
    return state, build_result(state)
