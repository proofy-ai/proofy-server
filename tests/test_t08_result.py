"""T08 가짜 분석기 + 결과 API(계약 4.8·4.11). 계약 테스트 8·9, T08-a~d(11/21 승인)."""

import time

from app.agent import runner
from app.agent.output import RecommendedDoc
from app.agent.scripted import ScriptedAnalyzer

API = "/api/v1"
RESULT_KEYS = {
    "runId",
    "basedOnInputVersion",
    "isStale",
    "generatedAt",
    "precomputed",
    "referral",
    # 계약 v0.8 AI 의견·질문(T24)
    "agentReview",
    "aiNotice",
    "deadline",
    "findings",
    "checklist",
    "draft",
    "unreadEvidence",
    "summary",
}


def _sample(client, scenario: str = "GOODS") -> tuple[str, dict[str, str]]:
    res = client.post(f"{API}/cases/sample", json={"scenario": scenario})
    assert res.status_code == 201, res.text
    body = res.json()
    return body["caseId"], {"X-Case-Token": body["caseToken"]}


def _analyze(client, case_id: str, auth: dict[str, str]) -> dict:
    res = client.post(f"{API}/cases/{case_id}/analysis-runs", json={}, headers=auth)
    assert res.status_code == 202, res.text
    run_id = res.json()["runId"]
    end = time.monotonic() + 60
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            assert run["status"] == "SUCCEEDED", run
            return run
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def _result(client, case_id: str, auth: dict[str, str]) -> dict:
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _evidence_ids(client, case_id: str, auth: dict[str, str]) -> set[str]:
    res = client.get(f"{API}/cases/{case_id}/evidence", headers=auth)
    assert res.status_code == 200, res.text
    return {e["evidenceId"] for e in res.json()["items"]}


def _ai_items(result_or_checklist: dict) -> list[dict]:
    checklist = result_or_checklist.get("checklist", result_or_checklist)
    return [i for i in checklist["items"] if i["category"] == "AI_RECOMMENDED"]


# 8: 결과 응답 모양 핵심(GOODS)
def test_goods_result_shape(client):
    case_id, auth = _sample(client, "GOODS")
    run = _analyze(client, case_id, auth)
    result = _result(client, case_id, auth)

    assert set(result) == RESULT_KEYS
    assert result["runId"] == run["runId"]
    assert result["isStale"] is False
    assert result["precomputed"] is False
    assert result["referral"] is None
    # 초안 내용은 T09 테스트가 본다
    assert result["draft"] is not None
    assert result["aiNotice"]

    findings = result["findings"]
    assert [f["status"] for f in findings] == ["MATCH", "CONFLICT", "STATEMENT_ONLY"]
    for f in findings:
        assert set(f) == {"findingId", "claim", "status", "note", "conflict", "sources"}
        assert isinstance(f["note"], str) and f["note"]
    conflict = findings[1]["conflict"]
    assert conflict == {"field": "AMOUNT", "statement": "150,000원", "found": "120,000원"}

    sources = [s for f in findings for s in f["sources"]]
    by_kind = {s["kind"]: s for s in sources}
    assert set(by_kind) == {"NARRATIVE", "EVIDENCE", "TRANSACTION"}
    assert set(by_kind["NARRATIVE"]) == {"kind", "quote", "verified"}
    assert set(by_kind["EVIDENCE"]) == {
        "kind",
        "evidenceId",
        "docType",
        "originalName",
        "page",
        "regionIndex",
        "quote",
        "verified",
    }
    assert set(by_kind["TRANSACTION"]) == {
        "kind",
        "transactionId",
        "evidenceId",
        "occurredAt",
        "direction",
        "amountKrw",
        "counterparty",
        "verified",
    }
    tx = by_kind["TRANSACTION"]
    assert (tx["occurredAt"], tx["direction"], tx["amountKrw"]) == ("2026-11-08", "IN", 150000)
    assert all(s["verified"] is True for s in sources)

    counts = result["summary"]["findingCounts"]
    assert counts == {"MATCH": 1, "CONFLICT": 1, "STATEMENT_ONLY": 1, "UNKNOWN": 0}
    assert result["summary"]["missingDocuments"] == result["checklist"]["missingCount"]

    ai = _ai_items(result)
    assert len(ai) == 1
    assert ai[0]["acceptedDocTypes"] == ["SHIPPING"]
    assert ai[0]["code"] is None
    assert ai[0]["status"] == "MISSING"


# 9: 사건 간 근거 교차 차단
def test_sources_stay_in_own_case(client):
    cases = [_sample(client, "GOODS") for _ in range(2)]
    for case_id, auth in cases:
        _analyze(client, case_id, auth)

    tx_ids_by_case = []
    for case_id, auth in cases:
        own_evidence = _evidence_ids(client, case_id, auth)
        sources = [s for f in _result(client, case_id, auth)["findings"] for s in f["sources"]]
        ev_refs = {s["evidenceId"] for s in sources if "evidenceId" in s}
        assert ev_refs and ev_refs <= own_evidence
        tx_ids_by_case.append({s["transactionId"] for s in sources if s["kind"] == "TRANSACTION"})
    assert all(tx_ids_by_case)
    assert not (tx_ids_by_case[0] & tx_ids_by_case[1])


# T08-a: 분석 전 결과 조회 404
def test_result_before_analysis_is_404(client):
    case_id, auth = _sample(client)
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


# T08-b: 두 번 분석 → 두 번째 실행 것만
def test_second_run_replaces_result(client):
    case_id, auth = _sample(client)
    _analyze(client, case_id, auth)
    first = _result(client, case_id, auth)
    second_run = _analyze(client, case_id, auth)
    second = _result(client, case_id, auth)

    assert second["runId"] == second_run["runId"] != first["runId"]
    assert len(second["findings"]) == 3
    assert not {f["findingId"] for f in first["findings"]} & {
        f["findingId"] for f in second["findings"]
    }
    assert len(_ai_items(second)) == 1
    checklist = client.get(f"{API}/cases/{case_id}/checklist", headers=auth).json()
    assert len(_ai_items(checklist)) == 1
    assert _ai_items(checklist)[0]["itemId"] == _ai_items(second)[0]["itemId"]


# T08-c: 분석 뒤 사연 수정 → isStale, 다시 분석하면 고친 인용은 verified false
def test_edit_after_analysis_is_stale_and_unverified(client):
    case_id, auth = _sample(client)
    _analyze(client, case_id, auth)
    narrative = (
        "온라인 쇼핑몰을 운영합니다. 거래처에 지갑을 납품하고 대금을 계좌로 받았습니다. "
        "물건은 다음 날 택배로 보냈습니다."
    )
    res = client.patch(f"{API}/cases/{case_id}", json={"narrative": narrative}, headers=auth)
    assert res.status_code == 200, res.text
    assert _result(client, case_id, auth)["isStale"] is True

    _analyze(client, case_id, auth)
    result = _result(client, case_id, auth)
    assert result["isStale"] is False
    quotes = {
        s["quote"]: s["verified"]
        for f in result["findings"]
        for s in f["sources"]
        if s["kind"] == "NARRATIVE"
    }
    assert quotes["11월 8일 대금을 계좌로 받았습니다"] is False
    assert quotes["물건은 다음 날 택배로 보냈습니다"] is True


# T08-d: UNEXPECTED → DATE 충돌 1, MATCH 2, STATEMENT_ONLY 1
def test_unexpected_result(client):
    case_id, auth = _sample(client, "UNEXPECTED")
    _analyze(client, case_id, auth)
    result = _result(client, case_id, auth)

    counts = result["summary"]["findingCounts"]
    assert counts == {"MATCH": 2, "CONFLICT": 1, "STATEMENT_ONLY": 1, "UNKNOWN": 0}
    conflicts = [f["conflict"] for f in result["findings"] if f["status"] == "CONFLICT"]
    assert conflicts == [{"field": "DATE", "statement": "11월 11일", "found": "11월 12일"}]
    assert _ai_items(result) == []


# 그 밖의 확인(계약 테스트 아님)


def test_steps_have_tool_call_reasons(client):
    case_id, auth = _sample(client)
    run = _analyze(client, case_id, auth)
    types = [s["type"] for s in run["steps"]]
    assert types.count("OCR") == 3
    assert "CONFLICT" in types
    # 조사 계획(T24)도 TOOL_CALL이라 거래내역 조회 줄을 제목으로 찾는다
    tool = next(s for s in run["steps"] if s["title"] == "거래내역 조회")
    assert tool["summary"] == "사연의 11월 8일 대금 입금을 확인하려고 11/1~11/10 입금을 조회 → 2건"
    assert all(isinstance(s["summary"], str) and s["summary"] for s in run["steps"])


def test_ai_item_not_satisfied_by_fixed_doc_type(client, monkeypatch):
    """고정 항목이 받는 docType(CHAT)으로는 AI 권장 항목이 충족되지 않는다(계약 v0.6.5)."""

    class WithChatRecommendation(ScriptedAnalyzer):
        def compare(self, ctx, rec, out) -> None:
            super().compare(ctx, rec, out)
            out.recommended += [
                RecommendedDoc(f"권장 {i}", "설명입니다.", ("CHAT",)) for i in range(4)
            ]

    monkeypatch.setattr(runner, "select_analyzer", lambda agent: WithChatRecommendation())
    case_id, auth = _sample(client, "UNEXPECTED")  # 협박 문자(CHAT)가 올라 있음
    _analyze(client, case_id, auth)
    ai = _ai_items(_result(client, case_id, auth))
    assert len(ai) == 3  # 최대 3개
    assert all(i["status"] == "MISSING" and i["satisfiedBy"] == [] for i in ai)

    res = client.patch(
        f"{API}/cases/{case_id}/checklist/{ai[0]['itemId']}", json={"checked": True}, headers=auth
    )
    assert res.status_code == 200, res.text
    assert res.json()["item"]["checked"] is True


def test_ai_item_satisfied_by_own_doc_type(client):
    case_id, auth = _sample(client, "GOODS")
    _analyze(client, case_id, auth)
    res = client.post(
        f"{API}/cases/{case_id}/evidence",
        headers=auth,
        data={"docType": "SHIPPING"},
        files={"file": ("ship.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
    )
    assert res.status_code == 201, res.text
    ai = _ai_items(_result(client, case_id, auth))
    assert ai[0]["status"] == "SATISFIED"
    assert ai[0]["satisfiedBy"] == [res.json()["evidence"]["evidenceId"]]
