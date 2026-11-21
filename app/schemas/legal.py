"""법령 안내(계약 4.2.1)."""

from datetime import date
from typing import Literal

from app.schemas.checklist import SourceRef
from app.schemas.common import CamelModel, InflowType

LegalGuideStage = Literal["SITUATION", "SUBMIT"]


class LegalGuideItem(CamelModel):
    code: str
    stage: LegalGuideStage
    title: str
    plain: str
    quote: str
    # 이 유형에서 "보통" 쓰는 이의제기 사유. 판정 값이 아니다(원칙 1)
    common_for_type: bool
    source_ref: SourceRef
    effective_date: date


class LegalGuidesResponse(CamelModel):
    inflow_type: InflowType
    disclaimer: str
    items: list[LegalGuideItem]
