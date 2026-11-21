"""사건 없이 부르는 안내 API(계약 4.2, 4.2.1). 인증 없음."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.checklist import RequirementsResponse
from app.schemas.common import InflowType
from app.schemas.legal import LegalGuidesResponse
from app.services.legal import DISCLAIMER, legal_guides_for
from app.services.requirements import requirements_for

router = APIRouter(tags=["meta"])


@router.get("/meta/requirements", response_model=RequirementsResponse)
def get_requirements(
    inflow_type: Annotated[InflowType, Query(alias="inflowType")],
) -> RequirementsResponse:
    return RequirementsResponse(
        inflow_type=inflow_type,
        items=[r.to_schema() for r in requirements_for(inflow_type)],
    )


@router.get("/legal-guides", response_model=LegalGuidesResponse)
def get_legal_guides(
    inflow_type: Annotated[InflowType, Query(alias="inflowType")],
) -> LegalGuidesResponse:
    return LegalGuidesResponse(
        inflow_type=inflow_type,
        disclaimer=DISCLAIMER,
        items=[g.to_schema(inflow_type) for g in legal_guides_for(inflow_type)],
    )
