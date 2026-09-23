"""Analysis endpoints.

Analysis is asynchronous because a real model call takes tens of seconds and a
whole document takes longer. `POST /analyze` starts the workflow and returns
202 with an id; the client polls `GET /analysis/{id}/status`.

Nothing here decides anything about grounding. The route starts a job and
reports what the workflow concluded; the coverage gate, the verifier and the
output gate live in the graph, where they cannot be routed around.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.agents.runner import AnalysisJob, analysis_runner
from app.documents.overview import build_overview
from app.documents.storage import document_store
from app.schemas.analysis import (
    AnalysisStatus,
    AnalysisStatusResponse,
    AnalyzeResponse,
    FindingsResponse,
)

documents_router = APIRouter(prefix="/documents", tags=["analysis"])
analysis_router = APIRouter(prefix="/analysis", tags=["analysis"])


def _status_payload(job: AnalysisJob) -> AnalysisStatusResponse:
    """Safe metadata only - no prompts, no raw model output, no provider detail."""
    return AnalysisStatusResponse(
        analysis_id=job.analysis_id,
        document_id=job.document_id,
        status=job.status,
        stage=job.stage,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_ms=job.duration_ms,
        coverage=job.coverage,
        proposed_count=job.proposed_count,
        verified_count=job.verified_count,
        withheld_count=job.withheld_count,
        error_category=job.error_category,
        error_message=job.error_message,
    )


@documents_router.post("/{document_id}/analyze", response_model=AnalyzeResponse)
async def start_analysis(document_id: str, response: Response) -> AnalyzeResponse:
    """Start an analysis, or hand back the one already under way.

    202 while work is outstanding, 200 when an existing completed analysis is
    returned - so a client can tell "started" from "already done" without
    parsing the body.
    """
    document_store.get(document_id)  # 404 if unknown or expired

    job, reused = analysis_runner.submit(document_id)

    response.status_code = 200 if job.status is AnalysisStatus.COMPLETED else 202
    return AnalyzeResponse(
        analysis_id=job.analysis_id,
        document_id=job.document_id,
        status=job.status,
        stage=job.stage,
        created_at=job.created_at,
        reused=reused,
    )


@analysis_router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse)
def analysis_status(analysis_id: str) -> AnalysisStatusResponse:
    return _status_payload(analysis_runner.get(analysis_id))


@documents_router.get("/{document_id}/findings", response_model=FindingsResponse)
def document_findings(document_id: str) -> FindingsResponse:
    """The gated result. 409 until an analysis has completed.

    `result.findings` contains only findings that passed the output gate.
    Everything the model proposed that did not survive verification appears as
    counts in `result.withheld`, never as content.

    `overview` groups those same findings by topic. It is built here, from the
    gated result, rather than in the workflow - the release decision is already
    made by the time this runs, and a projection taken after the gate cannot
    route around it. It adds no field a client could not derive itself from
    `result.findings`.
    """
    document_store.get(document_id)
    job = analysis_runner.latest_completed(document_id)

    return FindingsResponse(
        document_id=document_id,
        analysis_id=job.analysis_id,
        status=job.status,
        result=job.result,
        overview=build_overview(job.result),
    )
