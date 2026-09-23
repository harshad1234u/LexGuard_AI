"""Running analyses in the background.

A deliberately small execution abstraction: `AnalysisRunner` owns the job
records and the decision to start work; how the work actually runs sits behind
`_spawn`. Today that is an asyncio task in this process, which is the right
size for an MVP with ephemeral documents and no database. Replacing it with a
real queue means reimplementing `_spawn` and the job store - the API, the
graph and the gates do not change.

The model call takes tens of seconds, so no HTTP request waits for it. A client
starts an analysis, gets an id, and polls.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.agents.graph import build_graph
from app.agents.nodes import build_result
from app.agents.state import AnalysisState
from app.core.config import get_settings
from app.core.errors import ConflictError, ErrorCode, NotFoundError
from app.core.logging import get_logger
from app.models import get_model_provider
from app.models.provider import ModelProvider
from app.schemas.analysis import (
    AnalysisResult,
    AnalysisStage,
    AnalysisStatus,
    CoverageSummary,
    ErrorCategory,
    TERMINAL_STATUSES,
)

logger = get_logger(__name__)

#: The workflow's stages in order, one per graph node. Used only to report the
#: stage a run is entering; the graph's own edges decide what actually runs.
STAGE_SEQUENCE: tuple[AnalysisStage, ...] = (
    AnalysisStage.QUEUED,
    AnalysisStage.VALIDATING,
    AnalysisStage.INGESTING,
    AnalysisStage.CHECKING_COVERAGE,
    AnalysisStage.BUILDING_DOCUMENT_MAP,
    AnalysisStage.ANALYZING,
    AnalysisStage.VERIFYING,
    AnalysisStage.GATING_OUTPUT,
)

#: Which stage follows which. `gating_output` has no successor here: the run's
#: final stage is published by `_finish`, together with its status, so the two
#: can never disagree while a client is polling.
NEXT_STAGE: dict[AnalysisStage, AnalysisStage] = dict(
    zip(STAGE_SEQUENCE, STAGE_SEQUENCE[1:])
)


class AnalysisJob(BaseModel):
    """One analysis, from request to terminal state."""

    analysis_id: str
    document_id: str
    status: AnalysisStatus = AnalysisStatus.QUEUED
    stage: AnalysisStage = AnalysisStage.QUEUED
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    coverage: CoverageSummary | None = None
    proposed_count: int | None = None
    verified_count: int | None = None
    withheld_count: int | None = None
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    result: AnalysisResult | None = Field(
        default=None,
        description="Set only once the output gate has run.",
    )

    @property
    def is_active(self) -> bool:
        return self.status not in TERMINAL_STATUSES


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRunner:
    """Starts analyses and tracks their jobs.

    In-process and thread-safe. Jobs live as long as the process, like the
    documents they describe.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJob] = {}
        self._by_document: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()

    # --- Lookup ---------------------------------------------------------
    def get(self, analysis_id: str) -> AnalysisJob:
        with self._lock:
            job = self._jobs.get(analysis_id)
        if job is None:
            raise NotFoundError(
                ErrorCode.DOCUMENT_NOT_FOUND,
                "That analysis is not available. It may have expired.",
            )
        return job

    def for_document(self, document_id: str) -> AnalysisJob | None:
        with self._lock:
            analysis_id = self._by_document.get(document_id)
            return self._jobs.get(analysis_id) if analysis_id else None

    def latest_completed(self, document_id: str) -> AnalysisJob:
        job = self.for_document(document_id)
        if job is None:
            raise NotFoundError(
                ErrorCode.DOCUMENT_NOT_FOUND,
                "No analysis has been run for this document yet.",
            )
        if job.status is not AnalysisStatus.COMPLETED:
            raise ConflictError(
                ErrorCode.COVERAGE_INCOMPLETE,
                "The analysis for this document has not completed.",
                details={"analysis_id": job.analysis_id, "status": str(job.status)},
            )
        return job

    # --- Submission -------------------------------------------------------
    def submit(
        self,
        document_id: str,
        *,
        provider: ModelProvider | None = None,
    ) -> tuple[AnalysisJob, bool]:
        """Start an analysis, or return the existing one.

        Returns `(job, reused)`. The idempotency rule, which exists so a
        double-clicked button cannot buy two 37-second inferences:

        * queued or running -> return it untouched, reused=True
        * completed         -> return it, reused=True (re-running costs a call
                               and cannot produce a better-grounded answer from
                               the same document)
        * failed            -> start a new one, reused=False (a failure is
                               retryable, but only because the user asked again)

        The check and the claim happen under one lock, so two requests racing
        for the same document cannot both conclude that nothing is running.
        Coordination extends no further than this process - see the limits
        documented in the README.
        """
        job = AnalysisJob(
            analysis_id=f"an_{secrets.token_hex(10)}",
            document_id=document_id,
            created_at=_now(),
        )

        with self._lock:
            active_id = self._by_document.get(document_id)
            existing = self._jobs.get(active_id) if active_id else None
            if existing is not None and existing.status is not AnalysisStatus.FAILED:
                claimed = None
            else:
                self._jobs[job.analysis_id] = job
                self._by_document[document_id] = job.analysis_id
                claimed = job

        if claimed is None:
            logger.info(
                "analysis reused analysis_id=%s document_id=%s status=%s",
                existing.analysis_id,
                document_id,
                existing.status,
            )
            return existing, True

        logger.info(
            "analysis queued analysis_id=%s document_id=%s", job.analysis_id, document_id
        )
        self._spawn(job, provider or get_model_provider())
        return job, False

    # --- Execution ---------------------------------------------------------
    def _spawn(self, job: AnalysisJob, provider: ModelProvider) -> None:
        """Begin the work. The seam a real job queue would replace."""
        task = asyncio.create_task(self._run(job, provider))
        with self._lock:
            self._tasks[job.analysis_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job.analysis_id, None))

    async def _run(self, job: AnalysisJob, provider: ModelProvider) -> None:
        settings = get_settings()
        job.status = AnalysisStatus.RUNNING
        job.started_at = _now()
        started = time.perf_counter()

        try:
            final = await asyncio.wait_for(
                self._execute(job, provider),
                timeout=settings.analysis_timeout_seconds,
            )
        except TimeoutError:
            # A whole-workflow budget, separate from the provider's own
            # timeout. Terminal, and never retried automatically.
            self._finish_failed(
                job,
                started,
                ErrorCategory.ANALYSIS_TIMEOUT,
                "The analysis took too long and was stopped. Please try again.",
            )
            return
        except asyncio.CancelledError:
            self._finish_failed(
                job, started, ErrorCategory.INTERNAL_ERROR, "The analysis was cancelled."
            )
            raise
        except Exception as exc:
            # The type only, and no traceback: an exception's own message can
            # echo whatever it was handed, which at this point is document
            # text or a model's proposal about it.
            logger.error("analysis crashed analysis_id=%s type=%s",
                         job.analysis_id, type(exc).__name__)
            self._finish_failed(
                job, started, ErrorCategory.INTERNAL_ERROR,
                "The analysis could not be completed.",
            )
            return

        self._finish(job, started, final)

    async def _execute(self, job: AnalysisJob, provider: ModelProvider) -> AnalysisState:
        """Run the graph, publishing progress as it goes.

        Streamed rather than invoked so a polling client sees real progress
        instead of a spinner that says "queued" for a minute.

        The graph emits state *after* each node returns, so reporting the stage
        it carries would leave a client reading "building_document_map" for the
        whole model call - the one stage worth naming accurately, since it is
        the one that takes 37 seconds. What is published instead is the stage
        the workflow is entering, which the emission after the previous node
        determines: the sequence is fixed and the mapping is 1:1 with the nodes.

        This is reporting only. Nothing routes on `job.stage`, and a run that
        ended - failed or gated - advances no further.
        """
        state: AnalysisState = {}
        stream = build_graph(provider).astream(
            AnalysisState(
                analysis_id=job.analysis_id,
                document_id=job.document_id,
                stage=AnalysisStage.QUEUED,
            ),
            stream_mode="values",
        )

        async for state in stream:
            if state.get("error_category"):
                continue
            entering = NEXT_STAGE.get(state.get("stage"))
            if entering is not None:
                job.stage = entering

        return state

    def _finish(self, job: AnalysisJob, started: float, state: AnalysisState) -> None:
        """Record the outcome.

        COMPLETED is set only when the run reached the output gate. A workflow
        that stopped earlier is a failure, whatever the reason - there is no
        path that reports success for a partially-executed analysis.
        """
        job.duration_ms = int((time.perf_counter() - started) * 1000)
        job.completed_at = _now()
        job.coverage = state.get("coverage")
        job.stage = state.get("stage", AnalysisStage.QUEUED)

        if state.get("error_category"):
            job.status = AnalysisStatus.FAILED
            job.error_category = state["error_category"]
            job.error_message = state.get("error_message")
        elif job.stage is not AnalysisStage.DONE:
            # Defensive: a run that ended without failing and without gating.
            job.status = AnalysisStatus.FAILED
            job.error_category = ErrorCategory.INTERNAL_ERROR
            job.error_message = "The analysis did not complete."
        else:
            job.status = AnalysisStatus.COMPLETED
            job.result = build_result(state)
            job.proposed_count = job.result.proposed_count
            job.verified_count = len(job.result.findings)
            job.withheld_count = job.result.withheld.total

        logger.info(
            "analysis finished analysis_id=%s document_id=%s status=%s stage=%s "
            "category=%s duration_ms=%d",
            job.analysis_id,
            job.document_id,
            job.status,
            job.stage,
            job.error_category,
            job.duration_ms,
        )

    def _finish_failed(
        self,
        job: AnalysisJob,
        started: float,
        category: ErrorCategory,
        message: str,
    ) -> None:
        job.status = AnalysisStatus.FAILED
        job.error_category = category
        job.error_message = message
        job.duration_ms = int((time.perf_counter() - started) * 1000)
        job.completed_at = _now()
        logger.info(
            "analysis finished analysis_id=%s document_id=%s status=failed category=%s "
            "duration_ms=%d",
            job.analysis_id,
            job.document_id,
            category,
            job.duration_ms,
        )

    # --- Lifecycle ----------------------------------------------------------
    def forget_document(self, document_id: str) -> None:
        """Drop an analysis when its document is discarded."""
        with self._lock:
            analysis_id = self._by_document.pop(document_id, None)
            if analysis_id:
                self._jobs.pop(analysis_id, None)
                task = self._tasks.pop(analysis_id, None)
        if analysis_id and task and not task.done():
            task.cancel()

    def clear(self) -> None:
        """Cancel everything in flight and forget it. Shutdown and tests."""
        with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
            self._jobs.clear()
            self._by_document.clear()
        for task in tasks:
            if not task.done():
                task.cancel()


analysis_runner = AnalysisRunner()
