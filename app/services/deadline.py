"""이의제기 기한(D-day) 계산. 계약 5절. 날짜·기한은 코드가 만든다(CLAUDE.md 원칙 2)."""

import calendar
from datetime import date, datetime, timedelta, timezone

from app.schemas.deadline import Deadline, DeadlineState

# 한국은 서머타임이 없어 UTC+9 고정으로 충분하다
KST = timezone(timedelta(hours=9))

URGENT_DAYS = 7
NOTICE = "정확한 기한은 계좌가 있는 은행에 꼭 확인하세요."


def today_kst() -> date:
    return datetime.now(KST).date()


def last_day_of_period(public_notice_date: date) -> date:
    """공고일 기준 2개월 기간의 마지막 날.

    초일 불산입(민법 제157조): 시작일 S = 공고일 + 1일.
    S의 2개월 뒤 같은 날짜가 있으면 그 전날, 그 달에 같은 날짜가 없으면 그 달 말일(민법 제160조).
    공휴일 순연(제161조)은 하지 않는다(계약 5절 4번).
    """
    start = public_notice_date + timedelta(days=1)
    month_index = start.month - 1 + 2
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_dom = calendar.monthrange(year, month)[1]
    if start.day <= last_dom:
        return date(year, month, start.day) - timedelta(days=1)
    return date(year, month, last_dom)


def _label(days_left: int) -> str:
    if days_left > 0:
        return f"D-{days_left}"
    if days_left == 0:
        return "D-DAY"
    return "기한 지남"


def _state(days_left: int) -> DeadlineState:
    if days_left > URGENT_DAYS:
        return "OK"
    if days_left >= 0:
        return "URGENT"
    return "EXPIRED"


def compute_deadline(public_notice_date: date | None, today: date) -> Deadline:
    if public_notice_date is None:
        return Deadline(
            state="UNKNOWN_NOTICE_DATE",
            deadline_date=None,
            days_left=None,
            label="공고일 확인 필요",
            basis=None,
            notice=NOTICE,
        )

    deadline_date = last_day_of_period(public_notice_date)
    days_left = (deadline_date - today).days
    return Deadline(
        state=_state(days_left),
        deadline_date=deadline_date,
        days_left=days_left,
        label=_label(days_left),
        basis=f"공고일({public_notice_date.isoformat()}) 기준 2개월, 참고 계산",
        notice=NOTICE,
    )
