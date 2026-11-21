"""올린 서류와 파일 내용. 컬럼 정본은 `docs/erd.md` 3.3·3.3.1."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(32))
    original_name: Mapped[str] = mapped_column(String(255))
    # 파일 내용으로 판별한 형식
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    extract_status: Mapped[str] = mapped_column(String(16), default="UPLOADED")
    # 아래 글자 추출 칼럼은 T13·T14에서 채운다
    extract_method: Mapped[str | None] = mapped_column(String(16))
    # 서버 안에서만 쓰고 외부 AI에 보내지 않는다
    extracted_text: Mapped[str | None] = mapped_column(Text)
    # AI에는 이것만 보낸다
    masked_text: Mapped[str | None] = mapped_column(Text)
    regions_json: Mapped[list[dict] | None] = mapped_column(JSON)
    low_confidence_regions: Mapped[int | None] = mapped_column(Integer)
    extract_error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime)


class EvidenceFile(Base):
    """파일 원본. 호스팅 디스크가 재배포 때 지워져도 남게 DB에 둔다(ERD v1.1)."""

    __tablename__ = "evidence_files"

    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary)
