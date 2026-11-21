"""증빙 API 응답(계약 4.7)."""

from typing import Literal

from app.schemas.common import CamelModel, DocType, UtcDatetime

ExtractStatus = Literal["UPLOADED", "PROCESSING", "READY", "FAILED"]
EvidenceMime = Literal["image/jpeg", "image/png", "application/pdf"]


class EvidenceOut(CamelModel):
    evidence_id: str
    doc_type: DocType
    original_name: str
    mime_type: EvidenceMime
    size_bytes: int
    extract_status: ExtractStatus
    low_confidence_regions: int | None
    is_sample: bool
    created_at: UtcDatetime


class EvidenceEnvelope(CamelModel):
    evidence: EvidenceOut


class EvidenceList(CamelModel):
    items: list[EvidenceOut]
