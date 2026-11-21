"""증빙 올리기·목록·지우기(계약 4.7). 파일 원본은 DB `evidence_files`에 둔다(ERD v1.1 3.3.1)."""

import hashlib
import ntpath
import posixpath
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Case, Evidence, EvidenceFile
from app.schemas.evidence import EvidenceOut

MAX_FILES_PER_CASE = 8
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_NAME_LENGTH = 255

# 파일 앞부분(매직 바이트) → 형식. 이름·브라우저가 보낸 Content-Type은 믿지 않는다
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)


def detect_mime(data: bytes) -> str | None:
    for signature, mime in _SIGNATURES:
        if data.startswith(signature):
            return mime
    return None


def _clean_name(filename: str | None) -> str:
    # 브라우저에 따라 경로가 붙어 올 수 있어 파일 이름만 남긴다
    name = posixpath.basename(ntpath.basename(filename or "")).strip()
    return (name or "upload")[:MAX_NAME_LENGTH]


_last_created_at = datetime.min
_created_at_lock = threading.Lock()


def _now() -> datetime:
    """올린 순서를 지키는 시각(마이크로초까지 저장, 응답은 초 단위).

    Windows 시계는 해상도가 거칠어 연달아 부르면 같은 값이 나올 수 있다. 같거나 이전 값이면
    1마이크로초씩 밀어 항상 커지게 한다(서버 프로세스 하나 기준).
    """
    global _last_created_at
    with _created_at_lock:
        now = datetime.now(UTC).replace(tzinfo=None)
        if now <= _last_created_at:
            now = _last_created_at + timedelta(microseconds=1)
        _last_created_at = now
        return now


def count_evidence(db: Session, case_id: str) -> int:
    return db.scalar(select(func.count()).where(Evidence.case_id == case_id)) or 0


def list_evidence(db: Session, case_id: str) -> list[Evidence]:
    return list(
        db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case_id)
            .order_by(Evidence.created_at, Evidence.id)
        )
    )


def stage_evidence(
    db: Session,
    case_id: str,
    doc_type: str,
    original_name: str,
    mime: str,
    data: bytes,
    *,
    is_sample: bool = False,
) -> Evidence:
    """증빙 행과 파일 원본을 세션에 넣는다(커밋은 부르는 쪽이 한다). 검사는 부르는 쪽 책임."""
    evidence = Evidence(
        id=str(uuid.uuid4()),
        case_id=case_id,
        doc_type=doc_type,
        original_name=original_name,
        mime_type=mime,
        size_bytes=len(data),
        content_sha256=hashlib.sha256(data).hexdigest(),
        is_sample=is_sample,
        extract_status="UPLOADED",
        created_at=_now(),
    )
    db.add(evidence)
    db.add(EvidenceFile(evidence_id=evidence.id, content=data))
    return evidence


def add_evidence(
    db: Session, case: Case, doc_type: str, filename: str | None, stream: BinaryIO
) -> Evidence:
    """검사 순서: 개수(409) → 크기(413) → 형식(415). 실패하면 아무것도 바꾸지 않는다."""
    if count_evidence(db, case.id) >= MAX_FILES_PER_CASE:
        raise ApiError(
            409,
            "EVIDENCE_LIMIT",
            f"서류는 사건당 {MAX_FILES_PER_CASE}개까지 올릴 수 있어요.",
            {"limit": MAX_FILES_PER_CASE},
        )
    data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            "파일은 10MB 이하만 올릴 수 있어요.",
            {"maxBytes": MAX_FILE_BYTES},
        )
    mime = detect_mime(data)
    if mime is None:
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "JPG·PNG·PDF 파일만 올릴 수 있어요.")

    evidence = stage_evidence(db, case.id, doc_type, _clean_name(filename), mime, data)
    _bump_input_version(case)
    db.commit()
    return evidence


def delete_evidence(db: Session, case: Case, evidence_id: str) -> None:
    evidence = db.get(Evidence, evidence_id)
    if evidence is None or evidence.case_id != case.id:
        raise ApiError(404, "NOT_FOUND", "서류를 찾을 수 없습니다.")
    # evidence_files는 ON DELETE CASCADE로 함께 지워진다
    db.delete(evidence)
    _bump_input_version(case)
    db.commit()


def _bump_input_version(case: Case) -> None:
    # 증빙 추가·삭제는 분석 입력이 바뀐 것(계약 4.7, ERD 4절)
    case.input_version += 1
    case.updated_at = _now().replace(microsecond=0)


def to_evidence_out(evidence: Evidence) -> EvidenceOut:
    return EvidenceOut(
        evidence_id=evidence.id,
        doc_type=evidence.doc_type,
        original_name=evidence.original_name,
        mime_type=evidence.mime_type,
        size_bytes=evidence.size_bytes,
        extract_status=evidence.extract_status,
        low_confidence_regions=evidence.low_confidence_regions,
        is_sample=evidence.is_sample,
        created_at=evidence.created_at,
    )
