"""거래내역서에서 뽑은 거래 행. 컬럼 정본은 `docs/erd.md` 3.4.

재분석하면 새 실행이 새로 뽑는다. 조회는 가장 최근 성공 실행 것만 쓴다.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount_krw > 0", name="ck_transactions_amount_positive"),
        CheckConstraint("direction IN ('IN', 'OUT')", name="ck_transactions_direction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    # 서류를 지우면 그 서류에서 뽑은 행도 지운다(결과는 isStale)
    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence.id", ondelete="CASCADE")
    )
    analysis_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    # STATEMENT(거래내역서)
    source: Mapped[str] = mapped_column(String(16))
    region_index: Mapped[int] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(3))
    amount_krw: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[date] = mapped_column(Date)
    counterparty_masked: Mapped[str | None] = mapped_column(String(100))
    # 원문 행. 서버 안에서만 쓴다
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
