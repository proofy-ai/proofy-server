"""사용량 로그. 컬럼 정본은 `docs/erd.md` 3.10.

사건과 FK로 묶지 않는다(사건을 지워도 한도·비용 기록이 남는다). 개인정보를 두지 않는다.
T07은 `ANALYSIS_RUN` 행만 쓰고, 한도 계산·`CASE_CREATE`·IP 해시는 T11에서 한다.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # CASE_CREATE · ANALYSIS_RUN
    kind: Mapped[str] = mapped_column(String(16))
    # FK 아님. 사건이 지워져도 값만 남는다
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36))
    # HMAC-SHA256(IP_HASH_SECRET, IP). T11에서 채운다
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # 외부 AI를 불렀나. 하루 한도는 이 값이 true인 행만 센다(T11)
    ai_called: Mapped[bool] = mapped_column(Boolean, default=False)
    precomputed: Mapped[bool] = mapped_column(Boolean, default=False)
    referral: Mapped[bool] = mapped_column(Boolean, default=False)
    agent: Mapped[str | None] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_micro_usd: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
