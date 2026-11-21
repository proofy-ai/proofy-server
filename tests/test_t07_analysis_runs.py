"""T07 분석 실행·진행(계약 4.9·4.10). 테스트 T07-a~f(11/21 승인)."""

import threading
import time

import pytest
from sqlalchemy import select

from app.agent import runner
from app.models import UsageEvent

API = "/api/v1"
STAGE_LABELS = [
    ("EXTRACTING", "글자 읽는 중"),
    ("COMPARING", "거래내역과 대조 중"),
    ("DRAFTING", "초안 작성 중"),
]


def _sample(client, scenario: str = "GOODS") -> tuple[str, dict[str, str]]:
    res = client.post(f"{API}/cases/sample", json={"scenario": scenario})
    assert res.status_code == 201, res.text
    body = res.json()
    return body["caseId"], {"X-Case-Token": body["caseToken"]}


def _start(client, case_id: str, auth: dict[str, str], **body):
    return client.post(f"{API}/cases/{case_id}/analysis-runs", json=body, headers=auth)


def _get_run(client, case_id: str, auth: dict[str, str], run_id: str) -> dict:
    res = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _wait_done(client, case_id: str, auth: dict[str, str], run_id: str, limit: float = 10) -> dict:
    end = time.monotonic() + limit
    while time.monotonic() < end:
        run = _get_run(client, case_id, auth, run_id)
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def _get_case(client, case_id: str, auth: dict[str, str]) -> dict:
    res = client.get(f"{API}/cases/{case_id}", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["case"]


class _WaitingAnalyzer:
    """글자 읽기 단계에서 신호를 기다리는 분석기(실행 중 상태를 만들려고)."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def extract(self, ctx, rec) -> None:
        self.release.wait(5)

    def compare(self, ctx, rec) -> None:
        pass

    def draft(self, ctx, rec) -> None:
        pass


# T07-a: 시작 202 → 폴링 → 완료, 사건 상태·latestRun·hasResult
def test_run_goes_through_stages_to_success(client):
    case_id, auth = _sample(client)
    assert _get_case(client, case_id, auth)["latestRun"] is None

    res = _start(client, case_id, auth)
    assert res.status_code == 202, res.text
    started = res.json()
    assert set(started) == {"runId", "status", "stage"}
    assert started["status"] == "RUNNING"
    assert started["stage"] == "EXTRACTING"

    run = _wait_done(client, case_id, auth, started["runId"])
    assert run["runId"] == started["runId"]
    assert run["status"] == "SUCCEEDED"
    assert run["stage"] == "FINISHED"
    assert [(s["key"], s["label"]) for s in run["stages"]] == STAGE_LABELS
    assert all(s["status"] == "DONE" for s in run["stages"])
    assert run["error"] is None
    assert run["startedAt"].endswith("Z")
    assert run["finishedAt"] is not None

    case = _get_case(client, case_id, auth)
    assert case["status"] == "REVIEW_READY"
    assert case["latestRun"] == {
        "runId": started["runId"],
        "status": "SUCCEEDED",
        "stage": "FINISHED",
    }
    assert case["hasResult"] is True


# T07-b: 사전 조건 422와 details.missing
@pytest.mark.parametrize(
    ("short_narrative", "drop_record", "missing"),
    [
        (True, False, ["NARRATIVE"]),
        (False, True, ["TRANSACTION_RECORD"]),
        (True, True, ["NARRATIVE", "TRANSACTION_RECORD"]),
    ],
)
def test_precondition_422(client, short_narrative, drop_record, missing):
    case_id, auth = _sample(client)
    if short_narrative:
        res = client.patch(f"{API}/cases/{case_id}", json={"narrative": "짧은 사연"}, headers=auth)
        assert res.status_code == 200
    if drop_record:
        items = client.get(f"{API}/cases/{case_id}/evidence", headers=auth).json()["items"]
        for item in items:
            if item["docType"] == "TRANSACTION_RECORD":
                url = f"{API}/cases/{case_id}/evidence/{item['evidenceId']}"
                assert client.delete(url, headers=auth).status_code == 204

    res = _start(client, case_id, auth)
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "ANALYSIS_PRECONDITION"
    assert error["details"]["missing"] == missing
    assert _get_case(client, case_id, auth)["latestRun"] is None


# T07-c: narrative 동봉 — 같으면 inputVersion 그대로, 다르면 저장·+1, 짧으면 저장 뒤 422
def test_narrative_sent_with_start(client):
    case_id, auth = _sample(client)
    original = _get_case(client, case_id, auth)["narrative"]

    res = _start(client, case_id, auth, narrative=original)
    assert res.status_code == 202
    _wait_done(client, case_id, auth, res.json()["runId"])
    assert _get_case(client, case_id, auth)["inputVersion"] == 1

    changed = original + " 영수증도 가지고 있습니다."
    res = _start(client, case_id, auth, narrative=changed)
    assert res.status_code == 202
    _wait_done(client, case_id, auth, res.json()["runId"])
    case = _get_case(client, case_id, auth)
    assert case["narrative"] == changed
    assert case["inputVersion"] == 2

    res = _start(client, case_id, auth, narrative="짧은 사연")
    assert res.status_code == 422
    assert res.json()["error"]["details"]["missing"] == ["NARRATIVE"]
    case = _get_case(client, case_id, auth)
    assert case["narrative"] == "짧은 사연"
    assert case["inputVersion"] == 3


# T07-d: 실행 중 다시 시작 → 409 ANALYSIS_IN_PROGRESS(details.runId)
def test_second_start_while_running_is_409(client, monkeypatch):
    analyzer = _WaitingAnalyzer()
    monkeypatch.setattr(runner, "select_analyzer", lambda agent: analyzer)
    case_id, auth = _sample(client)

    first = _start(client, case_id, auth).json()["runId"]
    try:
        res = _start(client, case_id, auth)
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "ANALYSIS_IN_PROGRESS"
        assert error["details"]["runId"] == first

        run = _get_run(client, case_id, auth, first)
        assert run["status"] == "RUNNING"
        assert [s["status"] for s in run["stages"]] == ["RUNNING", "PENDING", "PENDING"]
        assert _get_case(client, case_id, auth)["status"] == "ANALYZING"
    finally:
        analyzer.release.set()
    assert _wait_done(client, case_id, auth, first)["status"] == "SUCCEEDED"

    # 끝난 뒤에는 다시 시작할 수 있다
    res = _start(client, case_id, auth)
    assert res.status_code == 202
    _wait_done(client, case_id, auth, res.json()["runId"])


# T07-e: 마감 초과 → FAILED, AGENT_TIMEOUT, 사건 ERROR
def test_timeout_fails_run(client, settings, monkeypatch):
    class SlowAnalyzer(_WaitingAnalyzer):
        def extract(self, ctx, rec) -> None:
            self.release.wait(0.6)

    monkeypatch.setattr(runner, "select_analyzer", lambda agent: SlowAnalyzer())
    settings.analysis_timeout_seconds = 0.3
    case_id, auth = _sample(client)

    run_id = _start(client, case_id, auth).json()["runId"]
    run = _wait_done(client, case_id, auth, run_id)
    assert run["status"] == "FAILED"
    assert run["error"]["code"] == "AGENT_TIMEOUT"
    assert run["error"]["message"]
    assert run["finishedAt"] is not None
    assert "FAILED" in [s["status"] for s in run["stages"]]
    assert run["steps"][-1]["type"] == "FAILED"

    case = _get_case(client, case_id, auth)
    assert case["status"] == "ERROR"
    assert case["hasResult"] is False


# T07-f: 다른 사건의 runId는 404, 분석 시작마다 usage_events 1행
def test_other_case_run_404_and_usage_event(client, app):
    case_a, auth_a = _sample(client)
    case_b, auth_b = _sample(client)
    run_id = _start(client, case_a, auth_a).json()["runId"]
    _wait_done(client, case_a, auth_a, run_id)

    res = client.get(f"{API}/cases/{case_b}/analysis-runs/{run_id}", headers=auth_b)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"

    with app.state.session_factory() as db:
        events = db.scalars(select(UsageEvent).where(UsageEvent.kind == "ANALYSIS_RUN")).all()
    assert [(e.case_id, e.run_id) for e in events] == [(case_a, run_id)]
    assert events[0].ai_called is False
    assert events[0].agent == "scripted"


def _join_analysis_threads(limit: float = 5) -> None:
    for thread in threading.enumerate():
        if thread.name.startswith("analysis-"):
            thread.join(limit)
            assert not thread.is_alive()


# 서버 재시작으로 스레드가 사라진 실행: 조회·시작 때 마감이 지났으면 시간 초과로 정리
def test_orphan_run_expires_on_read_and_start(client, app):
    from datetime import timedelta

    from app.models import AnalysisRun

    case_id, auth = _sample(client)
    run_id = _start(client, case_id, auth).json()["runId"]
    _wait_done(client, case_id, auth, run_id)

    # 스레드 없이 RUNNING으로 남은 실행을 만든다(재시작 직전 상태)
    with app.state.session_factory() as db:
        run = db.get(AnalysisRun, run_id)
        run.status, run.stage, run.finished_at = "RUNNING", "COMPARING", None
        run.started_at = run.started_at - timedelta(seconds=200)
        db.commit()

    # 마감이 지난 고아 실행이 있어도 새 분석은 409가 아니라 시작된다
    res = _start(client, case_id, auth)
    assert res.status_code == 202, res.text
    new_run = res.json()["runId"]
    assert new_run != run_id
    old = _get_run(client, case_id, auth, run_id)
    assert old["status"] == "FAILED"
    assert old["error"]["code"] == "AGENT_TIMEOUT"
    assert [s["status"] for s in old["stages"]] == ["DONE", "FAILED", "PENDING"]
    assert _wait_done(client, case_id, auth, new_run)["status"] == "SUCCEEDED"


# 실행 중 사건 삭제: 스레드가 예외 없이 멈추고 실행·사용량 기록 처리가 맞다
def test_delete_case_while_running(client, app, monkeypatch, caplog):
    import logging

    from app.models import AnalysisRun

    caplog.set_level(logging.INFO, logger="proofy.analysis")

    analyzer = _WaitingAnalyzer()
    monkeypatch.setattr(runner, "select_analyzer", lambda agent: analyzer)
    case_id, auth = _sample(client)
    run_id = _start(client, case_id, auth).json()["runId"]

    assert client.delete(f"{API}/cases/{case_id}", headers=auth).status_code == 204
    analyzer.release.set()
    _join_analysis_threads()

    assert not [r for r in caplog.records if r.levelname in ("ERROR", "CRITICAL")]
    assert any("멈춤" in r.getMessage() for r in caplog.records)
    with app.state.session_factory() as db:
        assert db.get(AnalysisRun, run_id) is None
        # 사용량 기록은 사건과 따로 남는다(ERD 3.10)
        events = db.scalars(select(UsageEvent).where(UsageEvent.run_id == run_id)).all()
        assert len(events) == 1
