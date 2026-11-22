"""T24 AI 의견·질문(`agentReview`)과 조사 계획.

계약 테스트(README 승인 목록): T24-a 응답 모양. T24-b·c는 실제 분석(가짜 SDK) 부분에서.
"""

import json

import fake_claude
import flow
import pytest

from app.agent.compare import MAX_TOOL_CALLS

API = flow.API


def _result(client, scenario):
    case_id, auth = flow.sample(client, scenario)
    run = flow.run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth)
    assert res.status_code == 200
    return run, res.json()


@pytest.mark.parametrize(
    ("scenario", "label"),
    [("GOODS", "법 제7조 제1항 제2호"), ("UNEXPECTED", "법 제7조 제1항 제3호")],
)
def test_t24a_agent_review_shape(client, scenario, label):
    """T24-a: notice, 의견(근거 조항 칩), 질문(why), answered, findingIds는 같은 결과의 항목 ID."""
    _, body = _result(client, scenario)
    review = body["agentReview"]
    assert set(review) == {"notice", "opinions", "questions", "answered"}
    assert "변호사가 아니며" in review["notice"]
    assert review["answered"] == []

    finding_ids = {f["findingId"] for f in body["findings"]}
    (opinion,) = review["opinions"]
    assert set(opinion) == {"opinionId", "text", "findingIds", "lawRefs", "needsCheck"}
    assert opinion["needsCheck"] is False
    assert opinion["findingIds"] and set(opinion["findingIds"]) <= finding_ids
    (ref,) = opinion["lawRefs"]
    assert set(ref) == {"source", "label", "quote", "verified"}
    assert (ref["source"], ref["label"], ref["verified"]) == ("LAW", label, True)

    assert len(review["questions"]) == 2
    for q in review["questions"]:
        assert set(q) == {"questionId", "text", "why", "findingIds", "lawRefs"}
        assert q["text"] and q["why"]
        assert set(q["findingIds"]) <= finding_ids
    # 의견은 초안에 들어가지 않는다(초안은 본인 사실 진술)
    assert opinion["text"] not in body["draft"]["fullText"]


def test_scripted_run_shows_plan_law_and_plan_check(client):
    run, _ = _result(client, "GOODS")
    titles = [s["title"] for s in run["steps"]]
    assert titles[titles.index("조사 계획")] == "조사 계획"
    plan = next(s for s in run["steps"] if s["title"] == "조사 계획")
    assert plan["type"] == "TOOL_CALL"
    assert plan["summary"].startswith("확인할 것 3가지: 11/8 입금(거래내역)")
    # 계획이 조회보다 먼저
    assert titles.index("조사 계획") < titles.index("거래내역 조회") < titles.index("법령 조회")
    check = next(s for s in run["steps"] if s["title"] == "계획 점검")
    assert check["type"] == "VERIFY"


def test_agent_review_is_null_without_opinions_or_questions(client):
    """T24 결정 1: 의견·질문·답한 기록이 모두 없으면 null(급여·기타 가짜 분석)."""
    body = client.post(
        f"{API}/cases",
        json={
            "noticeReceivedDate": "2026-11-15",
            "inflow": {"type": "SALARY", "amountKrw": 2_000_000},
            "hasPriorFreeze": None,
        },
    ).json()
    case_id, auth = body["caseId"], {"X-Case-Token": body["caseToken"]}
    client.post(
        f"{API}/cases/{case_id}/evidence",
        files={"file": ("tx.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"docType": "TRANSACTION_RECORD"},
        headers=auth,
    )
    run = flow.run(
        client, case_id, auth, {"narrative": "회사에서 11월 급여 200만 원을 받았습니다."}
    )
    assert run["status"] == "SUCCEEDED"
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth).json()
    assert res["agentReview"] is None


# ---- 실제 분석(가짜 SDK): 조사 계획, 의견 검증(T24-b), 의견 고쳐 쓰기(T24-c) ----

TX_QUERY = {
    "reason": "사연의 11월 8일 대금 입금을 확인하려고",
    "from": "2026-11-01",
    "to": "2026-11-10",
    "direction": "IN",
    "counterparty": None,
    "minAmount": None,
    "maxAmount": None,
}
PLAN = {
    "items": [
        {"claim": "11/8 입금", "check": "거래내역 입금 행", "sources": ["TRANSACTIONS"]},
        {"claim": "법령 근거", "check": "이의제기 사유 조항", "sources": ["LAW"]},
    ],
    "revision": None,
}
LAW_QUOTE = "재화 또는 용역의 공급에 대한 대가로 받았거나"
READ_LAW = {"reason": "물품 대금이 사유가 되는지 확인하려고", "ref": "LAW:7"}
DRAFT = {
    "sentences": [
        {
            "section": "DEPOSIT_REASON",
            "text": "본인은 11월 8일 대금을 받았습니다.",
            "findingIndexes": [0],
        }
    ]
}


def _finding_answer(opinions, questions=(), plan_item=0):
    return {
        "findings": [
            {
                "claim": "11월 8일 대금 15만 원을 받았습니다",
                "status": "MATCH",
                "note": "거래내역서의 입금 행과 같습니다.",
                "conflict": None,
                "sources": [
                    {
                        "kind": "TRANSACTION",
                        "quote": None,
                        "evidenceId": None,
                        "regionIndex": None,
                        "transactionId": "t2",
                    }
                ],
                "planItem": plan_item,
            }
        ],
        "recommendedDocs": [],
        "opinions": list(opinions),
        "questions": list(questions),
    }


def _opinion(text, refs, indexes=(0,)):
    return {
        "text": text,
        "findingIndexes": list(indexes),
        "lawRefs": [{"ref": r, "quote": q} for r, q in refs],
    }


def _claude_run(client, monkeypatch, answer, *after):
    sdk = fake_claude.install(
        monkeypatch,
        [
            fake_claude.tool_use(
                ("p1", "make_plan", PLAN),
                ("u1", "get_transactions", TX_QUERY),
                ("u2", "get_law_article", READ_LAW),
            ),
            fake_claude.text(answer),
            fake_claude.text(DRAFT),
            *[fake_claude.text(r) for r in after],
        ],
    )
    case_id, auth = flow.sample(client)
    run = flow.run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED", run
    result = client.get(f"{API}/cases/{case_id}/result", headers=auth).json()
    return run, result, sdk


def test_make_plan_step_and_plan_check(claude_app, monkeypatch):
    run, _, _ = _claude_run(claude_app, monkeypatch, _finding_answer([]))
    plan = next(s for s in run["steps"] if s["title"] == "조사 계획")
    assert plan["type"] == "TOOL_CALL"
    assert plan["summary"] == "확인할 것 2가지: 11/8 입금(거래내역) · 법령 근거(법령)"
    check = next(s for s in run["steps"] if s["title"] == "계획 점검")
    assert check["type"] == "VERIFY"
    assert check["summary"] == "계획한 확인 2개 중 1개를 마쳤습니다. 확인 못 한 것: '법령 근거'"


def test_plan_check_counts_verified_law_citation(claude_app, monkeypatch):
    """#73: 법령만 보는 계획 항목은 확인된 법령 인용이 의견에 있으면 마친 것으로 센다."""
    opinion = _opinion("물품 대금으로 설명할 수 있어 보입니다.", [("LAW:7", LAW_QUOTE)])
    run, _, _ = _claude_run(claude_app, monkeypatch, _finding_answer([opinion]))
    check = next(s for s in run["steps"] if s["title"] == "계획 점검")
    assert check["summary"] == "계획한 확인 2개를 모두 마쳤습니다."


def test_plan_check_ignores_unverified_law_citation(claude_app, monkeypatch):
    """#73: 원문에 없는 인용은 법령 확인으로 세지 않는다."""
    opinion = _opinion("물품 대금으로 설명할 수 있어 보입니다.", [("LAW:7", "원문에 없는 문장")])
    run, _, _ = _claude_run(claude_app, monkeypatch, _finding_answer([opinion]))
    check = next(s for s in run["steps"] if s["title"] == "계획 점검")
    assert check["summary"] == "계획한 확인 2개 중 1개를 마쳤습니다. 확인 못 한 것: '법령 근거'"


def test_make_plan_not_counted_and_limited(claude_app, monkeypatch):
    calls = [("p1", "make_plan", PLAN), ("p2", "make_plan", PLAN), ("p3", "make_plan", PLAN)]
    calls += [(f"u{i}", "get_transactions", TX_QUERY) for i in range(MAX_TOOL_CALLS)]
    sdk = fake_claude.install(monkeypatch, [fake_claude.tool_use(*calls)])
    case_id, auth = flow.sample(claude_app)
    run = flow.run(claude_app, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    results = sdk.requests[1]["messages"][-1]["content"]
    # 계획은 2번까지, 조회 한도에는 세지 않는다
    errors = [r.get("is_error", False) for r in results]
    assert errors == [False, False, True] + [False] * MAX_TOOL_CALLS
    titles = [s["title"] for s in run["steps"]]
    assert titles.count("조사 계획") == 1 and titles.count("조사 계획 수정") == 1


def test_t24b_opinion_law_refs_are_checked(claude_app, monkeypatch):
    """T24-b: 조회하지 않은 조항·원문에 없는 인용은 verified false·needsCheck(지우지 않음)."""
    answer = _finding_answer(
        [
            _opinion(
                "말씀하신 내용과 거래내역을 기준으로 보면, 15만 원은 물건값으로 받은 돈이라고 "
                "설명할 수 있는 사정으로 보여요.",
                [("LAW:7", LAW_QUOTE)],
                indexes=(0, 5),
            ),
            # 이번 실행에서 읽지 않은 조항(법 제8조)
            _opinion(
                "말씀하신 내용을 기준으로 보면 이의제기로 지급정지 종료를 요청할 수 있는 "
                "사정으로 보여요.",
                [("LAW:8", "이의제기가 있는 경우")],
            ),
            # 읽은 조항이지만 원문에 없는 인용
            _opinion(
                "말씀하신 내용을 기준으로 보면 정당한 대가로 설명할 수 있는 사정으로 보여요.",
                [("LAW:7", "정당한 대가를 받은 계좌는 지급정지를 하지 아니한다")],
            ),
        ],
        questions=[
            {
                "text": "물건을 보낸 기록이 있나요?",
                "why": "발송을 보여 줄 자료가 없어요.",
                "findingIndexes": [0, 9],
                "lawRefs": [],
            }
        ],
    )
    _, result, _ = _claude_run(claude_app, monkeypatch, answer)
    finding_id = result["findings"][0]["findingId"]
    good, unread, wrong = result["agentReview"]["opinions"]

    assert good["needsCheck"] is False
    assert good["findingIds"] == [finding_id]  # 없는 번호 5는 빠짐
    assert good["lawRefs"] == [
        {"source": "LAW", "label": "법 제7조 제1항 제2호", "quote": LAW_QUOTE, "verified": True}
    ]
    assert unread["needsCheck"] is True
    assert unread["lawRefs"][0]["verified"] is False
    assert unread["lawRefs"][0]["label"] == "법 제8조"
    assert wrong["needsCheck"] is True
    assert wrong["lawRefs"][0]["verified"] is False

    (question,) = result["agentReview"]["questions"]
    assert question["findingIds"] == [finding_id]


REWRITE_OK = (
    "말씀하신 내용과 거래내역을 기준으로 보면 물건값으로 받은 돈이라고 "
    "설명할 수 있는 사정으로 보여요."
)


@pytest.mark.parametrize(
    ("rewritten", "keeps_original"),
    [(REWRITE_OK, False), ("그래도 해제될 가능성이 높아요.", True)],
)
def test_t24c_opinion_rewrite_once(claude_app, monkeypatch, rewritten, keeps_original):
    """T24-c: 결과 예측 의견은 1회 고쳐 쓰기. 통과하면 고친 글, 또 걸리면 원래 글 + needsCheck."""
    original = "말씀하신 내용과 거래내역을 기준으로 보면 해제될 가능성이 높아요."
    answer = _finding_answer([_opinion(original, [("LAW:7", LAW_QUOTE)])])
    run, result, sdk = _claude_run(
        claude_app,
        monkeypatch,
        answer,
        {"sentences": [], "opinions": [{"index": 0, "text": rewritten}]},
    )
    (opinion,) = result["agentReview"]["opinions"]
    assert opinion["text"] == (original if keeps_original else rewritten)
    assert opinion["needsCheck"] is keeps_original
    # 걸린 의견만 초안 고쳐 쓰기 호출(1회)에 같이 간다
    request = json.loads(sdk.requests[-1]["messages"][-1]["content"][0]["text"])
    assert [o["index"] for o in request["opinions"]] == [0]
    assert request["rewrite"] == []
    verify = next(s for s in run["steps"] if s["title"] == "의견 확인")
    assert ("고쳐 다시 확인" in verify["summary"]) is (not keeps_original)
