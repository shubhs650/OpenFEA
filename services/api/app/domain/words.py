"""Additive immutable Word artifacts tied to the original report's exact model/PDF."""

from datetime import datetime
from uuid import UUID

from app.domain.base import StrictModel
from app.domain.models import Hash


class WordRequest(StrictModel):
    pass


class WordExport(StrictModel):
    id: UUID
    report_id: UUID
    job_id: UUID
    project_id: UUID
    created_at: datetime
    model_sha256: Hash
    pdf_sha256: Hash
    docx_sha256: Hash
    generator: dict[str, str]
    renderer: dict[str, str]
