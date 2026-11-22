"""T16 대조 에이전트. 실제 Claude는 부르지 않고 가짜 SDK(`fake_claude`)로 도구 루프를 돌린다.

계약 테스트(README 승인 목록): T16-a 판정 필드 부재, T16-b 사건 간 근거 교차 차단.
"""

import time

import fake_claude
import flow
import pytest

from app.agent.compare import MAX_TOOL_CALLS, OUTPUT_SCHEMA, TOOLS
from app.agent.extract import Extraction
from app.agent.llm import ClaudeClient, Deadline, Usage, cost_micro_usd, user_text
from app.agent.masking import mask_text, seal_payload
from app.agent.verify import check_output
from app.config import Settings
from app.main import create_app
from app.models import UsageEvent

API = "/api/v1"
MISSING = "proofy-no-such-tesseract"

TX_QUERY = {
    "reason": "사연의 11월 8일 대금 입금을 확인하려고",
    "from": "2026-11-01",
    "to": "2026-11-10",
    "direction": "IN",
    "counterparty": None,
    "minAmount": None,
    "maxAmount": None,
}


def _source(kind, quote=None, evidence_id=None, region=None, tx=None):
    return {
        "kind": kind,
        "quote": quote,
        "evidenceId": evidence_id,
        "regionIndex": region,
        "transactionId": tx,
    }


def _finding(claim, status, sources, conflict=None):
    return {
        "claim": claim,
        "status": status,
        "note": "",
        "conflict": conflict,
        "sources": sources,
    }


@pytest.fixture
def claude_app(tmp_path):
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm="claude",
        scripted_stage_delay_seconds=0,
        tesseract_cmd=MISSING,
        pdftoppm_cmd=MISSING,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


def _sample(client, scenario="GOODS"):
    body = client.post(f"{API}/cases/sample", json={"scenario": scenario}).json()
    return body["caseId"], {"X-Case-Token": body["caseToken"]}


def _run(client, case_id, auth):
    res = client.post(f"{API}/cases/{case_id}/analysis-runs", json={}, headers=auth)
    assert res.status_code == 202, res.text
    run_id = res.json()["runId"]
    end = time.monotonic() + 20
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def _walk_keys(schema, found):
    if isinstance(schema, dict):
        for key, value in schema.get("properties", {}).items():
            found.add(key)
            _walk_keys(value, found)
        for value in schema.values():
            if isinstance(value, dict | list):
                _walk_keys(value, found)
    elif isinstance(schema, list):
        for value in schema:
            _walk_keys(value, found)
    return found


# T16-a 판정 필드 부재: AI 출력 형식에는 정해 둔 칸만 있다(해제 가능성·수용 여부 등 없음)
def test_t16a_output_schema_has_no_judgement_fields():
    keys = _walk_keys(OUTPUT_SCHEMA, set())
    assert keys == {
        "findings",
        "claim",
        "status",
        "note",
        "conflict",
        "field",
        "statement",
        "found",
        "sources",
        "kind",
        "quote",
        "evidenceId",
        "regionIndex",
        "transactionId",
        "recommendedDocs",
        "label",
        "reason",
        "acceptedDocTypes",
        # T24: 계획 항목 번호, 조건부 의견·질문(근거 번호·법령 근거)
        "planItem",
        "opinions",
        "questions",
        "text",
        "why",
        "findingIndexes",
        "lawRefs",
        "ref",
        # T10: 상담 권유(판정 칸 아님: 상담이 먼저 필요해 보이는지와 원문 인용)
        "consult",
        "recommend",
        "quotes",
    }
    status = OUTPUT_SCHEMA["properties"]["findings"]["items"]["properties"]["status"]
    assert set(status["enum"]) == {"MATCH", "CONFLICT", "STATEMENT_ONLY", "UNKNOWN"}


# T16-b 사건 간 근거 교차 차단: 조회하지 않은 거래·다른 사건 서류는 근거에서 빠지고,
# 자료 근거가 하나도 남지 않은 MATCH는 UNKNOWN이 된다
def test_t16b_unseen_or_foreign_sources_are_dropped(claude_app, monkeypatch):
    client = claude_app
    other_case, other_auth = _sample(client, "UNEXPECTED")
    other_evidence = client.get(f"{API}/cases/{other_case}/evidence", headers=other_auth).json()
    foreign_id = other_evidence["items"][0]["evidenceId"]

    case_id, auth = _sample(client)
    answer = {
        "findings": [
            # 도구가 돌려준 t2 → 남는다
            _finding("11월 8일 15만 원을 받았습니다", "MATCH", [_source("TRANSACTION", tx="t2")]),
            # 조회하지 않은 거래(t3은 출금이라 입금 조회에 없음), 다른 사건 서류 → 빠지고 UNKNOWN
            _finding(
                "11월 10일 4만5천 원을 썼습니다",
                "MATCH",
                [
                    _source("TRANSACTION", tx="t3"),
                    _source("EVIDENCE", quote="협박", evidence_id=foreign_id, region=0),
                ],
            ),
        ],
        "recommendedDocs": [],
    }
    fake_claude.install(
        monkeypatch,
        [
            fake_claude.tool_use(("u1", "get_transactions", TX_QUERY)),
            fake_claude.text(answer),
        ],
    )
    run = _run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED", run
    verify = [s for s in run["steps"] if s["type"] == "VERIFY"]
    assert verify and "확인되지 않는 근거" in verify[0]["summary"]

    result = client.get(f"{API}/cases/{case_id}/result", headers=auth).json()
    first, second = result["findings"]
    assert first["status"] == "MATCH"
    assert [(s["kind"], s["amountKrw"]) for s in first["sources"]] == [("TRANSACTION", 150_000)]
    assert second["status"] == "UNKNOWN"
    assert second["sources"] == []


def test_tool_reason_becomes_tool_call_step_and_usage_is_saved(claude_app, monkeypatch):
    client = claude_app
    case_id, auth = _sample(client)
    answer = {
        "findings": [],
        "recommendedDocs": [
            {
                "label": "택배 발송 기록",
                "reason": "발송을 보여 줄 자료입니다.",
                "acceptedDocTypes": ["SHIPPING"],
            }
        ],
    }
    sdk = fake_claude.install(
        monkeypatch,
        [fake_claude.tool_use(("u1", "get_transactions", TX_QUERY)), fake_claude.text(answer)],
    )
    run = _run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    calls = [s for s in run["steps"] if s["type"] == "TOOL_CALL"]
    assert calls[0]["summary"] == "사연의 11월 8일 대금 입금을 확인하려고 → 2건"
    assert any(s["type"] == "DRAFT" for s in run["steps"])

    # 요청 설정(agent-design 5절): effort low, 자동 캐시, 서버측 fallback, thinking 없음
    request = sdk.requests[0]
    assert request["output_config"]["effort"] == "low"
    assert request["cache_control"] == {"type": "ephemeral"}
    assert request["fallbacks"] == "default"
    assert "thinking" not in request

    checklist = client.get(f"{API}/cases/{case_id}/checklist", headers=auth).json()
    ai = [i for i in checklist["items"] if i["category"] == "AI_RECOMMENDED"]
    assert [i["label"] for i in ai] == ["택배 발송 기록"]

    with client.app.state.session_factory() as db:
        event = db.query(UsageEvent).filter_by(run_id=run["runId"]).one()
        assert event.model == "claude-opus-5-5"
        # 대조 2회 + 초안 1회(T17), 가짜 응답은 회당 입력 1000·출력 100
        assert event.input_tokens == 3000 and event.output_tokens == 300
        assert event.cost_micro_usd == cost_micro_usd(Usage(3000, 300), "claude-opus-5-5")
        assert event.model == "claude-opus-5-5"


def test_tool_calls_over_limit_get_error(claude_app, monkeypatch):
    client = claude_app
    case_id, auth = _sample(client)
    calls = [(f"u{i}", "get_transactions", TX_QUERY) for i in range(MAX_TOOL_CALLS + 1)]
    sdk = fake_claude.install(monkeypatch, [fake_claude.tool_use(*calls)])
    run = _run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    results = sdk.requests[1]["messages"][-1]["content"]
    assert [r.get("is_error", False) for r in results] == [False] * MAX_TOOL_CALLS + [True]
    assert len([s for s in run["steps"] if s["type"] == "TOOL_CALL"]) == MAX_TOOL_CALLS


def test_refusal_fails_run_and_still_records_cost(claude_app, monkeypatch):
    client = claude_app
    case_id, auth = _sample(client)
    fake_claude.install(monkeypatch, [fake_claude.refusal()])
    # 샘플 그대로면 미리 만든 결과로 끝나므로(T11) 사연을 고친 사건으로 실패를 본다
    narrative = "거래처에 가죽 지갑을 납품하고 11월 8일 대금 15만 원을 받았습니다. 고친 사연입니다."
    run = flow.run(client, case_id, auth, {"narrative": narrative})
    assert run["status"] == "FAILED"
    assert run["error"]["code"] == "AGENT_REFUSED"
    with client.app.state.session_factory() as db:
        event = db.query(UsageEvent).filter_by(run_id=run["runId"]).one()
        assert event.cost_micro_usd and event.cost_micro_usd > 0


def test_llm_accepts_only_masked_text():
    with pytest.raises(TypeError):
        user_text("김민수 010-1234-5678")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        seal_payload({"narrative": "가리지 않은 사연"})
    sealed = seal_payload({"narrative": mask_text("김민수 씨", {"김민수"}), "evidenceId": "e1"})
    assert "김*수" in sealed and "김민수" not in sealed
    assert user_text(sealed)["text"] == sealed


def test_check_output_fills_page_from_region_and_clips():
    ex = Extraction(
        status="READY",
        regions=[
            {"index": 4, "page": 2, "text": "3개 12만원", "maskedText": mask_text("3개 12만원")}
        ],
    )
    raw = {
        "findings": [
            _finding(
                "가" * 500,
                "CONFLICT",
                [_source("EVIDENCE", quote="3개 12만원", evidence_id="e1", region=4)],
                conflict={"field": "AMOUNT", "statement": "150,000원", "found": "120,000원"},
            ),
            _finding("어긋남 내용이 없는 항목", "CONFLICT", [], conflict=None),
        ],
        "recommendedDocs": [],
    }
    checked = check_output(raw, {"e1": ex}, set(), ["SHIPPING"])
    first, second = checked.findings
    assert len(first.claim) == 200
    assert first.sources[0].page == 2 and first.sources[0].region_index == 4
    assert first.conflict is not None and first.conflict.found == "120,000원"
    assert second.status == "UNKNOWN" and second.conflict is None


def test_cost_uses_answering_model_price():
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    assert cost_micro_usd(usage, "claude-opus-5-5") == 4_000_000
    # 모르는 모델(서버측 fallback 등)은 비싼 단가로 센다
    assert cost_micro_usd(usage, "claude-unknown") == 10_000_000


def test_client_without_key_fails_clearly():
    from app.agent.steps import AgentError

    with pytest.raises(AgentError):
        ClaudeClient(None, "claude-opus-5-5", "low", Deadline(time.monotonic() + 10))


def test_tools_require_reason():
    # 조사 계획(T24)은 조회가 아니라 이유 대신 계획 항목을 받는다
    for tool in (t for t in TOOLS if t["name"] != "make_plan"):
        assert "reason" in tool["input_schema"]["required"]
        assert tool["strict"] is True
