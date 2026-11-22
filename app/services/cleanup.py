"""24시간 자동 삭제(계약 2절 ④, ERD 3.10, T11-b).

만료 사건은 조회 때 이미 404다(`services/auth.py`). 여기서는 DB에서 실제로 지운다.
서버가 켜질 때 한 번, 그 뒤 `CLEANUP_INTERVAL_SECONDS`마다 서버 안 스레드로 돈다.
"""

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import Case, UsageEvent
from app.services.clock import utc_now

logger = logging.getLogger(__name__)

IP_HASH_TTL = timedelta(hours=24)


def purge_expired(db: Session, now: datetime) -> tuple[int, int]:
    """만료 사건을 지우고(하위 자료는 CASCADE) 24시간 지난 IP 해시를 비운다. (지운 사건, 비운 해시)

    사용량 기록 행은 남긴다(한도·비용 집계, 사건과 FK 없음).
    """
    expired = db.scalars(select(Case).where(Case.expires_at <= now)).all()
    for case in expired:
        db.delete(case)
    cleared = db.execute(
        update(UsageEvent)
        .where(UsageEvent.ip_hash.is_not(None), UsageEvent.created_at <= now - IP_HASH_TTL)
        .values(ip_hash=None)
    ).rowcount
    db.commit()
    return len(expired), cleared or 0


def run_once(session_factory: sessionmaker[Session]) -> None:
    try:
        with session_factory() as db:
            cases, hashes = purge_expired(db, utc_now())
        if cases or hashes:
            logger.info("자동 삭제: 만료 사건 %d개, IP 해시 %d개 비움", cases, hashes)
    except Exception:  # 정리가 실패해도 서버는 계속 돈다. 다음 주기에 다시 한다
        logger.exception("자동 삭제 실패")


class Cleaner:
    """주기 정리 스레드. `stop()`으로 끝낸다."""

    def __init__(self, session_factory: sessionmaker[Session], interval_seconds: float) -> None:
        self._session_factory = session_factory
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        run_once(self._session_factory)
        if self._interval <= 0:
            return
        self._thread = threading.Thread(target=self._loop, name="proofy-cleanup", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            run_once(self._session_factory)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
