"""T11-b 시간당 한도(계약 1.1 `RATE_LIMITED`, 4.3·4.3.1·4.10)와 24시간 자동 삭제(계약 2절 ④).

계약 테스트(README 승인 목록): T11-b-1 사건 생성 한도, T11-b-2 분석 한도, T11-b-3 자동 삭제.
"""

from collections.abc import Iterator
from datetime import timedelta

import flow
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import AnalysisRun, Case, Evidence, UsageEvent
from app.services.cleanup import purge_expired
from app.services.clock import utc_now

API = flow.API
NEW_CASE = {
    "noticeReceivedDate": "2026-11-15",
    "inflow": {"type": "GOODS", "amountKrw": 150_000},
    "hasPriorFreeze": None,
}


@pytest.fixture
def limited(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm="scripted",
        scripted_stage_delay_seconds=0,
        rate_limit_cases_per_ip_hour=2,
        rate_limit_runs_per_case_hour=1,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


def _count(client, model, *where) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model).where(*where))


def _assert_rate_limited(res) -> None:
    assert res.status_code == 429, res.text
    assert res.json()["error"]["code"] == "RATE_LIMITED"


# T11-b-1: 같은 IP에서 사건 생성 한도(일반·샘플 함께 셈)
def test_t11b1_case_create_limit_per_ip(limited):
    assert limited.post(f"{API}/cases", json=NEW_CASE).status_code == 201
    assert limited.post(f"{API}/cases/sample", json={"scenario": "GOODS"}).status_code == 201

    _assert_rate_limited(limited.post(f"{API}/cases", json=NEW_CASE))
    _assert_rate_limited(limited.post(f"{API}/cases/sample", json={"scenario": "UNEXPECTED"}))
    assert _count(limited, Case) == 2
    # IP 원문은 저장하지 않는다
    with limited.app.state.session_factory() as db:
        hashes = {e.ip_hash for e in db.scalars(select(UsageEvent))}
    assert len(hashes) == 1 and "testclient" not in hashes and len(hashes.pop()) == 64


# T11-b-2: 사건당 분석 한도. 다른 사건은 분석할 수 있다
def test_t11b2_run_limit_per_case(limited):
    case_id, auth = flow.sample(limited)
    assert flow.run(limited, case_id, auth)["status"] == "SUCCEEDED"

    _assert_rate_limited(flow.start(limited, case_id, auth))
    assert _count(limited, AnalysisRun, AnalysisRun.case_id == case_id) == 1

    other_id, other_auth = flow.sample(limited)
    assert flow.run(limited, other_id, other_auth)["status"] == "SUCCEEDED"


# T11-b-3: 만료 사건과 하위 자료는 DB에서 지우고, 사용량 기록은 남기되 IP 해시는 비운다
def test_t11b3_purge_expired_cases(client):
    old_id, old_auth = flow.sample(client)
    assert flow.run(client, old_id, old_auth)["status"] == "SUCCEEDED"
    kept_id, kept_auth = flow.sample(client)

    later = utc_now() + timedelta(hours=25)
    with client.app.state.session_factory() as db:
        db.get(Case, kept_id).expires_at = later + timedelta(hours=1)
        db.commit()
    events = _count(client, UsageEvent)
    assert _count(client, UsageEvent, UsageEvent.ip_hash.is_not(None)) > 0

    with client.app.state.session_factory() as db:
        assert purge_expired(db, later)[0] == 1

    assert _count(client, Case, Case.id == old_id) == 0
    assert _count(client, Evidence, Evidence.case_id == old_id) == 0
    assert _count(client, AnalysisRun, AnalysisRun.case_id == old_id) == 0
    assert _count(client, Case, Case.id == kept_id) == 1
    assert _count(client, Evidence, Evidence.case_id == kept_id) > 0
    assert _count(client, UsageEvent) == events
    assert _count(client, UsageEvent, UsageEvent.ip_hash.is_not(None)) == 0
    # 남은 사건은 그대로 조회된다
    assert client.get(f"{API}/cases/{kept_id}", headers=kept_auth).status_code == 200
