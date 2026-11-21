"""소명서 초안. 컬럼 정본은 `docs/erd.md` 3.9.

사건당 현재본 1행. 분석이 성공하면 그 실행의 초안으로 바꾸고(`version`은 이어서 +1),
`PUT`으로 저장할 때마다 `version` +1.
`unconfirmedCount`·`fullText`는 저장하지 않고 읽을 때 계산한다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), unique=True
    )
    based_on_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    # [{sentenceId, section, text, origin, findingIds, needsCheck, needsCheckReason,
    #   confirmed, edited}]
    sentences_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    # 사용자가 PUT으로 마지막에 저장한 시각. 값이 있으면 다시 분석할 때 DRAFT_HAS_EDITS
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)
