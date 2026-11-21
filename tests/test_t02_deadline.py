"""T02 계약 테스트 1·2·3 (docs/tasks/README.md 계약 테스트 목록, 11/21 승인)."""

from datetime import date

import pytest

from app.services.deadline import compute_deadline

TODAY = date(2026, 11, 21)


# 계약 테스트 1
def test_unknown_notice_date():
    d = compute_deadline(None, TODAY)
    assert d.state == "UNKNOWN_NOTICE_DATE"
    assert d.deadline_date is None
    assert d.days_left is None
    assert d.basis == "공고일을 몰라 기한을 계산하지 못했습니다."
    assert d.label == "공고일 확인 필요"
    assert "은행" in d.notice


# 계약 테스트 2
@pytest.mark.parametrize(
    ("notice_date", "expected_last_day"),
    [
        (date(2026, 11, 17), date(2027, 1, 17)),
        (date(2026, 11, 30), date(2027, 1, 31)),
        (date(2026, 12, 30), date(2027, 2, 28)),  # 평년: 2월 31일 없음 → 말일
        (date(2027, 12, 29), date(2028, 2, 29)),  # 윤년: 2월 30일 없음 → 말일
        (date(2027, 12, 30), date(2028, 2, 29)),  # 윤년: 2월 31일 없음 → 말일
    ],
)
def test_last_day(notice_date, expected_last_day):
    d = compute_deadline(notice_date, date(2026, 1, 1))
    assert d.deadline_date == expected_last_day


# 계약 테스트 3
@pytest.mark.parametrize(
    ("today", "days_left", "label", "state"),
    [
        (date(2027, 1, 9), 8, "D-8", "OK"),
        (date(2027, 1, 10), 7, "D-7", "URGENT"),
        (date(2027, 1, 17), 0, "D-DAY", "URGENT"),
        (date(2027, 1, 18), -1, "기한 지남", "EXPIRED"),
    ],
)
def test_boundaries(today, days_left, label, state):
    d = compute_deadline(date(2026, 11, 17), today)
    assert (d.days_left, d.label, d.state) == (days_left, label, state)


def test_json_shape():
    body = compute_deadline(date(2026, 11, 17), TODAY).model_dump(mode="json", by_alias=True)
    assert set(body) == {"state", "deadlineDate", "daysLeft", "label", "basis", "notice"}
    assert body["deadlineDate"] == "2027-01-17"
    assert body["daysLeft"] == 57
    assert body["label"] == "D-57"
    assert body["basis"] == "공고일(2026-11-17) 기준 2개월, 참고 계산"
