"""이슈 #40 FE 대조 반영(계약 v0.6.4): 기한 설명 문장, `/health`의 `dailyUsage`."""

import time
import uuid
from datetime import datetime, timedelta

from app.models import UsageEvent
from app.services.deadline import today_kst
from app.services.usage import kst_day_start_utc

CASE_BODY = {
    "noticeReceivedDate": "2026-11-10",
    "publicNoticeDate": None,
    "inflow": {"type": "GOODS", "amountKrw": 150000, "occurredAt": None},
    "hasPriorFreeze": False,
}


# 공고일을 모르면 basis는 null이 아니라 문장(계약 4.4)
def test_unknown_notice_basis_is_sentence(client):
    res = client.post("/api/v1/cases", json=CASE_BODY)
    assert res.status_code == 201, res.text
    deadline = res.json()["case"]["deadline"]
    assert deadline["state"] == "UNKNOWN_NOTICE_DATE"
    assert deadline["label"] == "공고일 확인 필요"
    assert deadline["basis"] == "공고일을 몰라 기한을 계산하지 못했습니다."


def _event(created_at: datetime, *, ai_called: bool, kind: str = "ANALYSIS_RUN") -> UsageEvent:
    return UsageEvent(
        id=str(uuid.uuid4()),
        kind=kind,
        case_id=str(uuid.uuid4()),
        ai_called=ai_called,
        precomputed=False,
        referral=False,
        created_at=created_at,
    )


# dailyUsage: 오늘(한국 날짜) 외부 AI를 부른 분석만 센다
def test_daily_usage_counts_ai_runs_today(client, app, settings):
    settings.daily_analysis_limit = 42
    today_start = kst_day_start_utc(today_kst())
    with app.state.session_factory() as db:
        db.add_all(
            [
                _event(today_start, ai_called=True),  # 오늘 0시 정각: 셈
                _event(today_start + timedelta(hours=1), ai_called=True),  # 셈
                _event(today_start + timedelta(hours=2), ai_called=False),  # AI 안 부름
                _event(today_start - timedelta(seconds=1), ai_called=True),  # 어제
                _event(today_start, ai_called=True, kind="CASE_CREATE"),  # 분석 아님
            ]
        )
        db.commit()

    body = client.get("/api/v1/health").json()
    assert body["dailyUsage"] == {"date": today_kst().isoformat(), "used": 2, "limit": 42}


# 가짜 분석은 외부 AI를 부르지 않아 used가 늘지 않는다
def test_scripted_run_does_not_count(client):
    body = client.post("/api/v1/cases/sample", json={"scenario": "GOODS"}).json()
    base = f"/api/v1/cases/{body['caseId']}/analysis-runs"
    auth = {"X-Case-Token": body["caseToken"]}
    res = client.post(base, json={}, headers=auth)
    assert res.status_code == 202
    run_url = f"{base}/{res.json()['runId']}"
    end = time.monotonic() + 10
    while client.get(run_url, headers=auth).json()["status"] == "RUNNING":
        assert time.monotonic() < end
        time.sleep(0.02)
    assert client.get("/api/v1/health").json()["dailyUsage"]["used"] == 0
