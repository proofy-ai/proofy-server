"""사건과 사용자가 말한 입금. 컬럼 정본은 `docs/erd.md` 3.1·3.2."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # caseToken의 SHA-256. 토큰 원문은 저장하지 않는다
    access_token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_scenario: Mapped[str | None] = mapped_column(String(16))
    # 샘플 생성 직후의 input_version. 지금 값과 같으면 "샘플 그대로"(T06·T11)
    sample_input_version: Mapped[int | None] = mapped_column(Integer)
    notice_received_date: Mapped[date] = mapped_column(Date)
    public_notice_date: Mapped[date | None] = mapped_column(Date)
    has_prior_freeze: Mapped[bool | None] = mapped_column(Boolean)
    narrative: Mapped[str | None] = mapped_column(Text)
    input_version: Mapped[int] = mapped_column(Integer, default=1)
    # 시각은 UTC(시간대 정보 없이 저장)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    inflow: Mapped["CaseInflow"] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )


class CaseInflow(Base):
    __tablename__ = "case_inflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), unique=True
    )
    inflow_type: Mapped[str] = mapped_column(String(16))
    # 사용자 **진술** 금액(API 필드는 inflow.amountKrw). 서류에서 뽑은 금액과 섞지 않는다
    reported_amount_krw: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    case: Mapped[Case] = relationship(back_populates="inflow")
