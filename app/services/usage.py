"""사용량 집계(`docs/erd.md` 3.10). 기록은 사건과 따로 있어 사건을 지워도 줄지 않는다.

`GET /health`의 `dailyUsage` 표시와 분석 시작 때 하루 한도 검사(429 `DAILY_LIMIT`, T11-a)에 쓴다.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import UsageEvent

KST_OFFSET = timedelta(hours=9)


def kst_day_start_utc(day: date) -> datetime:
    """한국 날짜 0시를 DB에 저장하는 UTC 시각(시간대 없이)으로."""
    return datetime.combine(day, time()) - KST_OFFSET


def count_ai_runs_on(db: Session, day: date) -> int:
    """그 한국 날짜에 외부 AI를 부른 분석 수. 하루 한도는 `ai_called = true`만 센다."""
    start = kst_day_start_utc(day)
    return (
        db.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.kind == "ANALYSIS_RUN",
                UsageEvent.ai_called.is_(True),
                UsageEvent.created_at >= start,
                UsageEvent.created_at < start + timedelta(days=1),
            )
        )
        or 0
    )
