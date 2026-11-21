"""사건별 체크리스트 행. 컬럼 정본은 `docs/erd.md` 3.8.

상수 항목(`code` 있음)은 체크 표시 보관용이고 문구는 코드 상수(`app/services/requirements.py`)에서
읽는다. AI 권장 항목(`code` 없음, T08)만 문구를 저장한다.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ChecklistItemRow(Base):
    __tablename__ = "checklist_items"
    __table_args__ = (UniqueConstraint("case_id", "code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    # analysis_runs 테이블이 생기는 T07에서 FK를 건다
    analysis_run_id: Mapped[str | None] = mapped_column(String(36))
    code: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    accepted_doc_types_json: Mapped[list[str] | None] = mapped_column(JSON)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)
