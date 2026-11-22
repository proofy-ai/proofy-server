"""T11-a 샘플 사건 대체 결과(계약 4.10·4.11·1.1 `DAILY_LIMIT`).

계약 테스트(README 승인 목록): T11-a-1 AI 실패 대체, T11-a-2 바꾼 샘플은 대체 안 함,
T11-a-3 하루 한도.
"""

import uuid

import fake_claude
import flow

from app.models import AnalysisRun, UsageEvent
from app.services.clock import utc_now

API = flow.API
FALLBACK_STEP = {
    "type": "FALLBACK",
    "title": "미리 만든 결과 사용",
    "summary": "지금은 AI 분석을 쓸 수 없어 샘플용으로 미리 만든 결과를 보여 드립니다.",
}
OWN_NARRATIVE = "모르는 사람이 제 계좌로 10만 원을 보냈고 그 뒤 계좌가 지급정지됐습니다."
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _result(client, case_id, auth):
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _usage(client, run_id) -> UsageEvent:
    with client.app.state.session_factory() as db:
        return db.query(UsageEvent).filter_by(run_id=run_id, kind="ANALYSIS_RUN").one()


# T11-a-1: 샘플 그대로 + AI 실패 → 미리 만든 결과로 SUCCEEDED
def test_t11a1_ai_failure_on_unchanged_sample_uses_precomputed(claude_app, monkeypatch):
    client = claude_app
    fake_claude.install(monkeypatch, [fake_claude.refusal()])
    case_id, auth = flow.sample(client, "GOODS")

    run = flow.run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    assert run["error"] is None
    last = run["steps"][-1]
    assert {k: last[k] for k in FALLBACK_STEP} == FALLBACK_STEP
    # 가짜 분석기의 step(조사 계획 등)은 AI가 한 일처럼 보이지 않게 남기지 않는다
    assert [s for s in run["steps"] if s["title"] == "조사 계획"] == []
    assert [s["type"] for s in run["steps"]].count("FALLBACK") == 1

    result = _result(client, case_id, auth)
    assert result["precomputed"] is True
    assert result["runId"] == run["runId"]
    assert len(result["findings"]) == 3
    assert result["agentReview"]["opinions"]
    assert result["agentReview"]["questions"]
    assert result["draft"] is not None and result["draft"]["sentences"]

    event = _usage(client, run["runId"])
    assert event.precomputed is True
    assert event.ai_called is True
    # AI를 부른 비용은 남는다
    assert event.cost_micro_usd and event.cost_micro_usd > 0


# T11-a-2: 사연을 고친 샘플은 대체하지 않고 실패 그대로
def test_t11a2_changed_sample_fails_without_fallback(claude_app, monkeypatch):
    client = claude_app
    fake_claude.install(monkeypatch, [fake_claude.refusal()])
    case_id, auth = flow.sample(client, "GOODS")

    narrative = "거래처에 가죽 지갑을 납품하고 11월 8일 대금 15만 원을 받았습니다. 고친 사연."
    run = flow.run(client, case_id, auth, {"narrative": narrative})
    assert run["status"] == "FAILED"
    assert run["error"]["code"] == "AGENT_REFUSED"
    assert "FALLBACK" not in [s["type"] for s in run["steps"]]
    assert _usage(client, run["runId"]).precomputed is False
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth)
    assert res.status_code == 404


def _use_up_daily_limit(client) -> None:
    client.app.state.settings.daily_analysis_limit = 1
    with client.app.state.session_factory() as db:
        db.add(
            UsageEvent(
                id=str(uuid.uuid4()),
                kind="ANALYSIS_RUN",
                case_id=str(uuid.uuid4()),
                ai_called=True,
                precomputed=False,
                referral=False,
                created_at=utc_now(),
            )
        )
        db.commit()


def _own_case(client) -> tuple[str, dict[str, str]]:
    body = {
        "noticeReceivedDate": "2026-11-10",
        "publicNoticeDate": None,
        "inflow": {"type": "UNEXPECTED", "amountKrw": 100000, "occurredAt": None},
        "hasPriorFreeze": False,
    }
    res = client.post(f"{API}/cases", json=body)
    assert res.status_code == 201, res.text
    case_id, auth = res.json()["caseId"], {"X-Case-Token": res.json()["caseToken"]}
    res = client.post(
        f"{API}/cases/{case_id}/evidence",
        files={"file": ("record.png", PNG, "image/png")},
        data={"docType": "TRANSACTION_RECORD"},
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return case_id, auth


# T11-a-3: 하루 한도 → 샘플 그대로는 AI 없이 미리 만든 결과, 직접 만든 사건은 429
def test_t11a3_daily_limit(claude_app, monkeypatch):
    client = claude_app
    sdk = fake_claude.install(monkeypatch, [])
    _use_up_daily_limit(client)

    case_id, auth = flow.sample(client, "UNEXPECTED")
    run = flow.run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    assert [s["type"] for s in run["steps"]] == ["FALLBACK"]
    assert sdk.requests == []
    result = _result(client, case_id, auth)
    assert result["precomputed"] is True
    assert len(result["findings"]) == 4
    event = _usage(client, run["runId"])
    assert (event.ai_called, event.precomputed) == (False, True)

    own_id, own_auth = _own_case(client)
    res = flow.start(client, own_id, own_auth, {"narrative": OWN_NARRATIVE})
    assert res.status_code == 429, res.text
    assert res.json()["error"]["code"] == "DAILY_LIMIT"
    with client.app.state.session_factory() as db:
        assert db.query(AnalysisRun).filter_by(case_id=own_id).count() == 0
    assert sdk.requests == []
