"""사건 API(계약 4.3~4.6). 업무 로직은 `app/services/cases.py`에 있다."""

from fastapi import APIRouter, Response

from app.db import DbSession
from app.schemas.case import CaseCreate, CaseCreated, CaseEnvelope, CasePatch
from app.services import cases as case_service
from app.services.auth import AuthorizedCase
from app.services.deadline import today_kst

router = APIRouter(tags=["cases"])


@router.post("/cases", status_code=201, response_model=CaseCreated)
def create_case(payload: CaseCreate, db: DbSession) -> CaseCreated:
    today = today_kst()
    case, token = case_service.create_case(db, payload, today)
    return CaseCreated(
        case_id=case.id, case_token=token, case=case_service.to_case_out(case, today)
    )


@router.get("/cases/{case_id}", response_model=CaseEnvelope)
def get_case(case: AuthorizedCase) -> CaseEnvelope:
    return CaseEnvelope(case=case_service.to_case_out(case, today_kst()))


@router.patch("/cases/{case_id}", response_model=CaseEnvelope)
def patch_case(patch: CasePatch, case: AuthorizedCase, db: DbSession) -> CaseEnvelope:
    today = today_kst()
    case = case_service.update_case(db, case, patch, today)
    return CaseEnvelope(case=case_service.to_case_out(case, today))


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case: AuthorizedCase, db: DbSession) -> Response:
    case_service.delete_case(db, case)
    return Response(status_code=204)
