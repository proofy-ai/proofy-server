"""AI 조건부 의견과 질문(계약 v0.8 4.11 `agentReview`). 컬럼 정본은 `docs/erd.md` 3.11·3.12.

의견은 문장으로만 저장하고 초안과 섞지 않는다. 해제·수용 가능성 같은 칸은 없다(CLAUDE.md 원칙 1).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AnalysisOpinion(Base):
    __tablename__ = "analysis_opinions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # 같은 실행의 claim_findings.id
    finding_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    # [{ref, source, label, quote, verified}]
    law_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    needs_check: Mapped[bool] = mapped_column(Boolean, default=False)
    # 서버 안에서만 쓰는 사유: LAW_QUOTE_NOT_FOUND · JUDGMENT_EXPRESSION · NUMBER_MISMATCH
    check_reason: Mapped[str | None] = mapped_column(String(32))


class AnalysisQuestion(Base):
    __tablename__ = "analysis_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text)
    finding_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    law_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # 사용자 답(원문, T25). AI에는 가린 뒤에만 보낸다
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
