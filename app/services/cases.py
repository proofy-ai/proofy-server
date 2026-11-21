"""사건 만들기·조회·수정·삭제(계약 4.3~4.6). D-day는 응답마다 오늘(한국 날짜)로 다시 계산한다."""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Case, CaseInflow
from app.schemas.case import CaseCreate, CaseOut, CasePatch, InflowIn, InflowOut
from app.services.auth import issue_token
from app.services.clock import utc_now
from app.services.deadline import compute_deadline

CASE_TTL = timedelta(hours=24)
FUTURE_DATE = "미래 날짜는 입력할 수 없습니다."
NOT_NULL = "비울 수 없는 값입니다."


def _check_not_future(fields: dict[str, str], name: str, value: date | None, today: date) -> None:
    if value is not None and value > today:
        fields[name] = FUTURE_DATE


def _raise_if_invalid(fields: dict[str, str]) -> None:
    if fields:
        raise ApiError(400, "VALIDATION_ERROR", "입력값을 확인해 주세요.", {"fields": fields})


def create_case(db: Session, payload: CaseCreate, today: date) -> tuple[Case, str]:
    """사건을 만들고 (사건, 토큰 원문)을 돌려준다."""
    fields: dict[str, str] = {}
    _check_not_future(fields, "noticeReceivedDate", payload.notice_received_date, today)
    _check_not_future(fields, "publicNoticeDate", payload.public_notice_date, today)
    _check_not_future(fields, "inflow.occurredAt", payload.inflow.occurred_at, today)
    _raise_if_invalid(fields)

    token, token_hash = issue_token()
    now = utc_now()
    case = Case(
        id=str(uuid.uuid4()),
        access_token_hash=token_hash,
        status="DRAFT",
        is_sample=False,
        notice_received_date=payload.notice_received_date,
        public_notice_date=payload.public_notice_date,
        has_prior_freeze=payload.has_prior_freeze,
        narrative=None,
        input_version=1,
        created_at=now,
        updated_at=now,
        expires_at=now + CASE_TTL,
    )
    case.inflow = CaseInflow(
        id=str(uuid.uuid4()),
        inflow_type=payload.inflow.type,
        reported_amount_krw=payload.inflow.amount_krw,
        occurred_at=payload.inflow.occurred_at,
        created_at=now,
    )
    db.add(case)
    db.commit()
    return case, token


def update_case(db: Session, case: Case, patch: CasePatch, today: date) -> Case:
    """보낸 필드만 바꾼다. 저장된 값과 실제로 다른 값이 있을 때만 `input_version` +1(계약 4.5)."""
    sent = patch.model_fields_set
    fields: dict[str, str] = {}
    if "notice_received_date" in sent and patch.notice_received_date is None:
        fields["noticeReceivedDate"] = NOT_NULL
    if "inflow" in sent and patch.inflow is None:
        fields["inflow"] = NOT_NULL
    _check_not_future(fields, "noticeReceivedDate", patch.notice_received_date, today)
    _check_not_future(fields, "publicNoticeDate", patch.public_notice_date, today)
    if patch.inflow is not None:
        _check_not_future(fields, "inflow.occurredAt", patch.inflow.occurred_at, today)
    _raise_if_invalid(fields)

    changed = False
    for name in ("notice_received_date", "public_notice_date", "has_prior_freeze", "narrative"):
        if name in sent and getattr(case, name) != getattr(patch, name):
            setattr(case, name, getattr(patch, name))
            changed = True
    if "inflow" in sent and patch.inflow is not None:
        changed = _replace_inflow(case.inflow, patch.inflow) or changed

    if changed:
        case.input_version += 1
        case.updated_at = utc_now()
        db.commit()
    return case


def _replace_inflow(inflow: CaseInflow, new: InflowIn) -> bool:
    """입금 정보를 통째로 바꾼다. UNIQUE(case_id)라 행은 두고 값만 바꾼다."""
    values = {
        "inflow_type": new.type,
        "reported_amount_krw": new.amount_krw,
        "occurred_at": new.occurred_at,
    }
    changed = False
    for name, value in values.items():
        if getattr(inflow, name) != value:
            setattr(inflow, name, value)
            changed = True
    return changed


def delete_case(db: Session, case: Case) -> None:
    """사건과 하위 자료를 지운다.

    증빙 파일·분석 결과는 각 작업(T05·T07~)의 테이블이 CASCADE로 함께 지워진다.
    """
    db.delete(case)
    db.commit()


def to_case_out(case: Case, today: date) -> CaseOut:
    return CaseOut(
        case_id=case.id,
        status=case.status,
        is_sample=case.is_sample,
        sample_scenario=case.sample_scenario,
        notice_received_date=case.notice_received_date,
        public_notice_date=case.public_notice_date,
        inflow=InflowOut(
            type=case.inflow.inflow_type,
            amount_krw=case.inflow.reported_amount_krw,
            occurred_at=case.inflow.occurred_at,
        ),
        has_prior_freeze=case.has_prior_freeze,
        narrative=case.narrative,
        input_version=case.input_version,
        deadline=compute_deadline(case.public_notice_date, today),
        # 증빙(T05)·분석 실행(T07)·결과(T08)가 생기면 조회로 채운다
        evidence_count=0,
        latest_run=None,
        has_result=False,
        created_at=case.created_at,
        expires_at=case.expires_at,
    )
