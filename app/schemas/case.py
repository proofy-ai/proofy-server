"""사건 API 요청·응답(계약 4.3~4.5)."""

from datetime import date
from typing import Literal

from pydantic import Field, StrictBool, StrictInt

from app.schemas.common import CamelModel, UtcDatetime
from app.schemas.deadline import Deadline

InflowType = Literal["SALARY", "GOODS", "UNEXPECTED", "OTHER"]
SampleScenario = Literal["GOODS", "UNEXPECTED", "SALARY"]
CaseStatus = Literal["DRAFT", "ANALYZING", "REVIEW_READY", "ERROR"]

MAX_AMOUNT_KRW = 10_000_000_000
MAX_NARRATIVE = 2000


class InflowIn(CamelModel):
    type: InflowType
    # 금액은 원 단위 정수만(문자열·소수 금지, 계약 1절)
    amount_krw: StrictInt = Field(ge=1, le=MAX_AMOUNT_KRW)
    occurred_at: date | None = None


class CaseCreate(CamelModel):
    notice_received_date: date
    public_notice_date: date | None = None
    inflow: InflowIn
    # 키는 필수, 값은 null 허용(모름)
    has_prior_freeze: StrictBool | None


class CasePatch(CamelModel):
    """보낸 필드만 바꾼다. 보냈는지는 `model_fields_set`으로 구분한다."""

    notice_received_date: date | None = None
    public_notice_date: date | None = None
    inflow: InflowIn | None = None
    has_prior_freeze: StrictBool | None = None
    narrative: str | None = Field(default=None, max_length=MAX_NARRATIVE)


class InflowOut(CamelModel):
    type: InflowType
    amount_krw: int
    occurred_at: date | None


class LatestRun(CamelModel):
    run_id: str
    status: str
    stage: str


class CaseOut(CamelModel):
    case_id: str
    status: CaseStatus
    is_sample: bool
    sample_scenario: SampleScenario | None
    notice_received_date: date
    public_notice_date: date | None
    inflow: InflowOut
    has_prior_freeze: bool | None
    narrative: str | None
    input_version: int
    deadline: Deadline
    evidence_count: int
    latest_run: LatestRun | None
    has_result: bool
    created_at: UtcDatetime
    expires_at: UtcDatetime


class CaseEnvelope(CamelModel):
    case: CaseOut


class CaseCreated(CamelModel):
    case_id: str
    # 생성 응답에서 한 번만 준다(계약 4.3)
    case_token: str
    case: CaseOut
