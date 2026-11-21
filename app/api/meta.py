"""사건 없이 부르는 안내 API(계약 4.2). 인증 없음."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.checklist import RequirementsResponse
from app.schemas.common import InflowType
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
