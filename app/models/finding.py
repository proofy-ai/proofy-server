"""주장별 대조 결과와 근거. 컬럼 정본은 `docs/erd.md` 3.6·3.7.

`status`는 자료와의 대조 상태이고 판정이 아니다(CLAUDE.md 원칙 1).
"""

from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ClaimFinding(Base):
    __tablename__ = "claim_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    claim_text: Mapped[str] = mapped_column(Text)
    # MATCH · CONFLICT · STATEMENT_ONLY · UNKNOWN
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    # CONFLICT일 때 {field, statement, found}
    conflict_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class FindingSource(Base):
    __tablename__ = "finding_sources"
    __table_args__ = (
        CheckConstraint(
            "(source_kind = 'EVIDENCE' AND evidence_id IS NOT NULL AND transaction_id IS NULL)"
            " OR (source_kind = 'TRANSACTION' AND transaction_id IS NOT NULL"
            " AND evidence_id IS NULL)"
            " OR (source_kind = 'NARRATIVE' AND evidence_id IS NULL AND transaction_id IS NULL)",
            name="ck_finding_sources_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    finding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("claim_findings.id", ondelete="CASCADE"), index=True
    )
    # 화면 순서
    seq: Mapped[int] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(16))
    # 서류·거래 행을 지우면 그 근거도 지운다(결과는 isStale)
    evidence_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evidence.id", ondelete="CASCADE")
    )
    transaction_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("transactions.id", ondelete="CASCADE")
    )
    page: Mapped[int | None] = mapped_column(Integer)
    region_index: Mapped[int | None] = mapped_column(Integer)
    quoted_text: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean)
