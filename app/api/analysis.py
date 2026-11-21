"""분석 실행 API(계약 4.9·4.10). 업무 로직은 `app/services/analysis.py`에 있다."""

from fastapi import APIRouter, Request

from app.db import DbSession
from app.schemas.analysis import AnalysisRunOut, AnalysisStart, AnalysisStarted
from app.services import analysis as analysis_service
from app.services.auth import AuthorizedCase
from app.services.deadline import today_kst

router = APIRouter(tags=["analysis"])


@router.post("/cases/{case_id}/analysis-runs", status_code=202, response_model=AnalysisStarted)
def start_analysis(
    case: AuthorizedCase,
    db: DbSession,
    request: Request,
    payload: AnalysisStart | None = None,
) -> AnalysisStarted:
    state = request.app.state
    run = analysis_service.start_analysis(
        db, case, payload or AnalysisStart(), state.settings, state.session_factory, today_kst()
    )
    return AnalysisStarted(run_id=run.id, status=run.status, stage=run.stage)


@router.get("/cases/{case_id}/analysis-runs/{run_id}", response_model=AnalysisRunOut)
def get_analysis_run(
    run_id: str, case: AuthorizedCase, db: DbSession, request: Request
) -> AnalysisRunOut:
    timeout = request.app.state.settings.analysis_timeout_seconds
    run = analysis_service.get_run(db, case, run_id, timeout)
    return analysis_service.to_run_out(run)
