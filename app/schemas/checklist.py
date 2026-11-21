"""유형별 서류 목록(계약 4.2)과 사건 체크리스트(계약 4.8)."""

from typing import Literal

from pydantic import StrictBool

from app.schemas.common import CamelModel, DocType, InflowType

ChecklistCategory = Literal[
    "OFFICIAL_REQUIRED", "TYPE_GUIDE", "ANALYSIS_INPUT", "OPTIONAL", "AI_RECOMMENDED"
]
ChecklistStatus = Literal["SATISFIED", "MISSING", "NOT_COLLECTED", "GUIDE_ONLY"]


class SourceRef(CamelModel):
    label: str
    url: str


class RequirementItem(CamelModel):
    code: str
    label: str
    category: ChecklistCategory
    accepted_doc_types: list[DocType]
    uploadable: bool
    required_for_analysis: bool
    note: str | None
    source_ref: SourceRef | None


class RequirementsResponse(CamelModel):
    inflow_type: InflowType
    items: list[RequirementItem]


class ChecklistItem(CamelModel):
    item_id: str
    # AI 권장 항목은 null
    code: str | None
    label: str
    category: ChecklistCategory
    status: ChecklistStatus
    accepted_doc_types: list[DocType]
    required_for_analysis: bool
    # 이 항목을 충족한 증빙 ID
    satisfied_by: list[str]
    checked: bool
    note: str | None
    source_ref: SourceRef | None


class ChecklistResponse(CamelModel):
    items: list[ChecklistItem]
    missing_count: int


class ChecklistPatch(CamelModel):
    checked: StrictBool


class ChecklistItemEnvelope(CamelModel):
    item: ChecklistItem
