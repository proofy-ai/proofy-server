from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def _utc_iso(value: datetime) -> str:
    # DB에는 시간대 없이 UTC로 저장한다. 시간대가 붙어 오면 UTC로 바꾼다
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


# 계약 1절 시각 형식: ISO 8601 UTC, 초 단위 `"2026-11-21T06:30:00Z"`
UtcDatetime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str)]

InflowType = Literal["SALARY", "GOODS", "UNEXPECTED", "OTHER"]

# 계약 2절 `DocType`. 신분증 값은 없다(신분증은 받지 않는다)
DocType = Literal[
    "NOTICE",
    "TRANSACTION_RECORD",
    "INSURANCE_ELIGIBILITY",
    "EMPLOYMENT_CERT",
    "PAYSLIP",
    "BUSINESS_REG",
    "CHAT",
    "CONTRACT",
    "TAX_INVOICE",
    "TRANSACTION_STATEMENT",
    "SHIPPING",
    "OTHER",
]


class CamelModel(BaseModel):
    """요청·응답 기본 모델. 파이썬에서는 snake_case, JSON에서는 camelCase(계약 1절)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
