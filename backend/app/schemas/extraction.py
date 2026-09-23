"""Schemas for the extraction step.

Kept separate from `app.schemas.documents` because it composes the manifest and
the coverage report, both of which import `CoverageStatus` from there.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.documents.manifest import DocumentManifest
from app.schemas.documents import DocumentStatus
from app.verification.coverage import CoverageReport


class ExtractionResponse(BaseModel):
    """Response for POST /api/v1/documents/{document_id}/extract.

    Carries the application's own record of what was read, so a client never has
    to take completeness on trust.
    """

    document_id: str
    status: DocumentStatus
    manifest: DocumentManifest
    coverage: CoverageReport
