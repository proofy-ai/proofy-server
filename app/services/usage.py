"""사용량 집계와 한도(`docs/erd.md` 3.10, T11). 기록은 사건과 따로 있어 사건을 지워도 줄지 않는다.

- 하루 한도(429 `DAILY_LIMIT`, T11-a): 외부 AI를 부른 분석만, 한국 날짜 기준
- 시간당 한도(429 `RATE_LIMITED`, T11-b): 같은 IP의 사건 생성, 사건당 분석. 최근 1시간
- IP는 원문을 두지 않고 `HMAC-SHA256(IP_HASH_SECRET, IP)`만 둔다. 24시간 뒤 정리가 비운다
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import UsageEvent

KST_OFFSET = timedelta(hours=9)
RATE_WINDOW = timedelta(hours=1)
# IP_HASH_SECRET이 없을 때 쓰는 값. 프로세스마다 새로 만든다
_FALLBACK_KEY = secrets.token_bytes(32)


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


def hash_ip(secret: str | None, ip: str | None) -> str | None:
    if not ip:
        return None
    key = secret.encode() if secret else _FALLBACK_KEY
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def _count_since(db: Session, since: datetime, *conditions) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(UsageEvent.created_at > since, *conditions)
        )
        or 0
    )


def check_case_create_limit(
    db: Session, ip_hash: str | None, limit: int | None, now: datetime
) -> None:
    """같은 IP에서 최근 1시간 사건 생성이 한도 이상이면 429(계약 4.3·4.3.1, 샘플도 함께 센다)."""
    if ip_hash is None or limit is None:
        return
    made = _count_since(
        db, now - RATE_WINDOW, UsageEvent.kind == "CASE_CREATE", UsageEvent.ip_hash == ip_hash
    )
    if made >= limit:
        raise ApiError(
            429,
            "RATE_LIMITED",
            f"한 시간에 사건을 {limit}개까지 만들 수 있어요. 잠시 뒤 다시 시도해 주세요.",
        )


def record_case_create(db: Session, case_id: str, ip_hash: str | None, now: datetime) -> None:
    """사건 생성 기록(커밋은 부르는 쪽이 한다)."""
    db.add(
        UsageEvent(
            id=str(uuid.uuid4()),
            kind="CASE_CREATE",
            case_id=case_id,
            ip_hash=ip_hash,
            ai_called=False,
            precomputed=False,
            referral=False,
            created_at=now,
        )
    )


def check_run_limit(db: Session, case_id: str, limit: int, now: datetime) -> None:
    """이 사건의 최근 1시간 분석이 한도 이상이면 429(계약 4.10). 가짜·대체 결과 실행도 센다."""
    runs = _count_since(
        db, now - RATE_WINDOW, UsageEvent.kind == "ANALYSIS_RUN", UsageEvent.case_id == case_id
    )
    if runs >= limit:
        raise ApiError(
            429,
            "RATE_LIMITED",
            f"한 사건은 한 시간에 {limit}번까지 분석할 수 있어요. 잠시 뒤 다시 시도해 주세요.",
        )
