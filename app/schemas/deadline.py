from datetime import date
from typing import Literal

from app.schemas.common import CamelModel

DeadlineState = Literal["UNKNOWN_NOTICE_DATE", "OK", "URGENT", "EXPIRED"]


class Deadline(CamelModel):
    """이의제기 기한(계약 4.4 `deadline`, 계산 규칙은 5절). FE는 표시만 한다."""

    state: DeadlineState
    deadline_date: date | None
    days_left: int | None
    label: str
    basis: str | None
    notice: str
