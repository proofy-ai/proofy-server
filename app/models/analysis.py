"""분석 실행. 컬럼 정본은 `docs/erd.md` 3.5.

T08~T16이 쓰는 컬럼(`precomputed`, `referral_json`, `masked_narrative`, `model` 등)도
여기서 미리 만든다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (UniqueConstraint("case_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    # 사건별 분석 횟수(1부터)
    version: Mapped[int] = mapped_column(Integer)
    # 시작할 때의 cases.input_version. 다르면 결과 isStale(T08)
    based_on_input_version: Mapped[int] = mapped_column(Integer)
    # RUNNING · SUCCEEDED · FAILED
    status: Mapped[str] = mapped_column(String(16))
    # EXTRACTING · COMPARING · DRAFTING · FINISHED
    stage: Mapped[str] = mapped_column(String(16))
    # 4번 화면 steps. 단계마다 새 리스트로 바꿔 저장한다(JSON 변경 감지)
    steps_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(String(200))
    precomputed: Mapped[bool] = mapped_column(Boolean, default=False)
    referral_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    masked_narrative: Mapped[str | None] = mapped_column(Text)
    agent: Mapped[str] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
