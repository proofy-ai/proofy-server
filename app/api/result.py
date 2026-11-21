"""분석 결과 API(계약 4.11). 업무 로직은 `app/services/results.py`에 있다."""

from fastapi import APIRouter

from app.db import DbSession
from app.schemas.result import ResultResponse
from app.services import results as results_service
from app.services.auth import AuthorizedCase
from app.services.deadline import today_kst

router = APIRouter(tags=["result"])


@router.get("/cases/{case_id}/result", response_model=ResultResponse)
def get_result(case: AuthorizedCase, db: DbSession) -> ResultResponse:
    return results_service.get_result(db, case, today_kst())
