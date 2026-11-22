"""사건 만들기·조회·수정·삭제(계약 4.3~4.6). D-day는 응답마다 오늘(한국 날짜)로 다시 계산한다."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.models import Case, CaseInflow
from app.schemas.case import CaseCreate, CaseOut, CasePatch, InflowIn, InflowOut, LatestRun
from app.services.auth import issue_token
from app.services.clock import utc_now
from app.services.deadline import compute_deadline
from app.services.evidence import count_evidence
from app.services.runs import has_result, latest_run
from app.services.usage import check_case_create_limit, hash_ip, record_case_create

CASE_TTL = timedelta(hours=24)
FUTURE_DATE = "미래 날짜는 입력할 수 없습니다."
NOT_NULL = "비울 수 없는 값입니다."


@dataclass(frozen=True)
class Creator:
    """사건을 만드는 요청(T11-b 시간당 한도). IP는 해시로만 갖는다."""

    ip_hash: str | None
    hourly_limit: int


def creator_for(settings: Settings, ip: str | None) -> Creator:
    return Creator(hash_ip(settings.ip_hash_secret, ip), settings.rate_limit_cases_per_ip_hour)


def _check_not_future(fields: dict[str, str], name: str, value: date | None, today: date) -> None:
    if value is not None and value > today:
        fields[name] = FUTURE_DATE


def _raise_if_invalid(fields: dict[str, str]) -> None:
    if fields:
        raise ApiError(400, "VALIDATION_ERROR", "입력값을 확인해 주세요.", {"fields": fields})


def create_case(
    db: Session, payload: CaseCreate, today: date, creator: Creator | None = None
) -> tuple[Case, str]:
    """사건을 만들고 (사건, 토큰 원문)을 돌려준다."""
    fields: dict[str, str] = {}
    _check_not_future(fields, "noticeReceivedDate", payload.notice_received_date, today)
    _check_not_future(fields, "publicNoticeDate", payload.public_notice_date, today)
    _check_not_future(fields, "inflow.occurredAt", payload.inflow.occurred_at, today)
    _raise_if_invalid(fields)

    case, token = stage_case(db, payload, creator=creator)
    db.commit()
    return case, token


def stage_case(
    db: Session,
    payload: CaseCreate,
    narrative: str | None = None,
    creator: Creator | None = None,
) -> tuple[Case, str]:
    """사건과 입금 정보를 세션에 넣는다(커밋은 부르는 쪽이 한다). 날짜 검사는 부르는 쪽 책임.

    `creator`가 있으면 같은 IP의 시간당 한도를 검사하고 생성 기록을 남긴다(T11-b).
    """
    now = utc_now()
    if creator is not None:
        check_case_create_limit(db, creator.ip_hash, creator.hourly_limit, now)
    token, token_hash = issue_token()
    case = Case(
        id=str(uuid.uuid4()),
        access_token_hash=token_hash,
        status="DRAFT",
        is_sample=False,
        notice_received_date=payload.notice_received_date,
        public_notice_date=payload.public_notice_date,
        has_prior_freeze=payload.has_prior_freeze,
        narrative=narrative,
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
    if creator is not None:
        record_case_create(db, case.id, creator.ip_hash, now)
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


def to_case_out(db: Session, case: Case, today: date) -> CaseOut:
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
        evidence_count=count_evidence(db, case.id),
        latest_run=_latest_run_out(db, case.id),
        has_result=has_result(db, case.id),
        created_at=case.created_at,
        expires_at=case.expires_at,
    )


def _latest_run_out(db: Session, case_id: str) -> LatestRun | None:
    run = latest_run(db, case_id)
    if run is None:
        return None
    return LatestRun(run_id=run.id, status=run.status, stage=run.stage)
