import datetime as dt

from fastapi import APIRouter, Request

from app.db import DbSession
from app.schemas.common import CamelModel
from app.services.deadline import today_kst
from app.services.usage import count_ai_runs_on

router = APIRouter()


class DailyUsage(CamelModel):
    date: dt.date
    used: int
    limit: int


class HealthResponse(CamelModel):
    status: str
    agent: str
    demo_mode: bool
    daily_usage: DailyUsage


@router.get("/health", response_model=HealthResponse)
def health(request: Request, db: DbSession) -> HealthResponse:
    """계약 4.1. 시연 전에 분석 모드(`scripted`/`claude`)와 오늘 사용량을 확인하는 용도."""
    settings = request.app.state.settings
    today = today_kst()
    return HealthResponse(
        status="ok",
        agent=settings.agent_llm,
        demo_mode=settings.demo_mode,
        daily_usage=DailyUsage(
            date=today,
            used=count_ai_runs_on(db, today),
            limit=settings.daily_analysis_limit,
        ),
    )
