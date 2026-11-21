"""분석 실행 조회 도우미. 사건 응답(`latestRun`·`hasResult`)과 분석 서비스가 함께 쓴다."""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import AnalysisRun


def latest_run(db: Session, case_id: str) -> AnalysisRun | None:
    return db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.case_id == case_id)
        .order_by(AnalysisRun.version.desc())
        .limit(1)
    ).first()


def latest_succeeded_run(db: Session, case_id: str) -> AnalysisRun | None:
    """결과·거래·AI 권장 항목은 가장 최근 성공 실행 것만 쓴다(계약 4.11)."""
    return db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.case_id == case_id, AnalysisRun.status == "SUCCEEDED")
        .order_by(AnalysisRun.version.desc())
        .limit(1)
    ).first()


def has_result(db: Session, case_id: str) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(AnalysisRun.case_id == case_id, AnalysisRun.status == "SUCCEEDED")
            )
        )
    )
