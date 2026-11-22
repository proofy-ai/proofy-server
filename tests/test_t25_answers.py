"""T25 답변 받기(`answers`)와 지난 분석 성찰(`previousRun`).

계약 테스트(README 승인 목록): T25-a 답 검증, T25-b 답 반영(가짜 분석), T25-c 답이 AI에 가려서 감.
"""

import json

import fake_claude
import flow

API = flow.API


def _result(client, case_id, auth):
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _case(client, case_id, auth):
    return client.get(f"{API}/cases/{case_id}", headers=auth).json()["case"]


def _questions(client, case_id, auth):
    return _result(client, case_id, auth)["agentReview"]["questions"]


def _answer(question_id, text):
    return {"questionId": question_id, "answer": text}


# ---- T25-a 답 검증 ----


def test_t25a_invalid_answers_are_rejected_and_nothing_saved(client):
    case_id, auth = flow.sample(client, "GOODS")
    flow.run(client, case_id, auth)
    old_question = _questions(client, case_id, auth)[0]["questionId"]
    # 다시 분석하면 질문이 새로 만들어진다 → 앞 실행의 질문은 받지 않는다
    flow.run(client, case_id, auth)
    current = _questions(client, case_id, auth)[0]["questionId"]
    assert current != old_question

    other_id, other_auth = flow.sample(client, "UNEXPECTED")
    flow.run(client, other_id, other_auth)
    other_question = _questions(client, other_id, other_auth)[0]["questionId"]

    before = _case(client, case_id, auth)
    bad_requests = [
        [_answer(old_question, "이전 실행의 질문에 답합니다")],
        [_answer(other_question, "다른 사건의 질문에 답합니다")],
        [_answer("no-such-question", "없는 질문에 답합니다")],
        [_answer(current, "   ")],
        [_answer(current, "가" * 501)],
        # 맞는 답과 섞여 있어도 하나라도 틀리면 모두 저장 안 함
        [_answer(current, "맞는 답입니다"), _answer("no-such-question", "틀린 답")],
    ]
    for answers in bad_requests:
        res = flow.start(
            client, case_id, auth, {"narrative": "바뀐 사연입니다. " * 3, "answers": answers}
        )
        assert res.status_code == 400, (answers, res.text)
        error = res.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert "answers" in error["details"]["fields"]

    after = _case(client, case_id, auth)
    assert after["inputVersion"] == before["inputVersion"]
    assert after["narrative"] == before["narrative"]
    review = _result(client, case_id, auth)["agentReview"]
    assert review["answered"] == []
    # 500자 정확히는 받는다
    res = flow.start(client, case_id, auth, {"answers": [_answer(current, "가" * 500)]})
    assert res.status_code == 202, res.text


# ---- T25-b 답 반영(가짜 분석) ----


def test_t25b_answers_move_to_answered_in_order(client):
    case_id, auth = flow.sample(client, "GOODS")
    flow.run(client, case_id, auth)
    q1, q2 = _questions(client, case_id, auth)
    version = _case(client, case_id, auth)["inputVersion"]

    # 둘째 질문에 먼저 답한다
    run = flow.run(
        client, case_id, auth, {"answers": [_answer(q2["questionId"], "송장 사진이 있어요.")]}
    )
    assert run["status"] == "SUCCEEDED"
    assert _case(client, case_id, auth)["inputVersion"] == version + 1
    # 다시 분석이면 계획 줄에 고정 revision
    plan = next(s for s in run["steps"] if s["title"] == "조사 계획")
    assert plan["summary"].startswith("지난 분석과 답변을 보고 다시 확인합니다 → ")

    review = _result(client, case_id, auth)["agentReview"]
    assert [q["text"] for q in review["questions"]] == [q1["text"]]
    assert [(a["questionId"], a["answer"]) for a in review["answered"]] == [
        (q2["questionId"], "송장 사진이 있어요.")
    ]

    # 남은 질문(새 실행의 같은 글 질문)에 두 번 답하면 마지막 답만 남는다
    q1_again = review["questions"][0]["questionId"]
    answers = [
        _answer(q1_again, "처음 답"),
        _answer(q1_again, "  다음 날 1개를 더 주문받았어요.  "),
    ]
    assert flow.run(client, case_id, auth, {"answers": answers})["status"] == "SUCCEEDED"

    review = _result(client, case_id, auth)["agentReview"]
    assert review["questions"] == []
    assert [(a["text"], a["answer"]) for a in review["answered"]] == [
        (q2["text"], "송장 사진이 있어요."),
        (q1["text"], "다음 날 1개를 더 주문받았어요."),
    ]


# ---- T25-c 답이 AI에 가려서 감(가짜 SDK) ----

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
        {"claim": "택배 발송", "check": "발송 기록", "sources": ["EVIDENCE"]},
    ],
    "revision": None,
}
DRAFT = {
    "sentences": [
        {
            "section": "DEPOSIT_REASON",
            "text": "본인은 11월 8일 대금을 받았습니다.",
            "findingIndexes": [0],
        }
    ]
}
ANSWER = "다음 날 최유나 씨가 1개를 더 주문해서 4개 15만 원이 됐어요."
ANSWER_QUOTE = "1개를 더 주문해서 4개 15만 원이 됐어요"


def _source(kind, quote=None, transaction_id=None):
    return {
        "kind": kind,
        "quote": quote,
        "evidenceId": None,
        "regionIndex": None,
        "transactionId": transaction_id,
    }


def _finding(claim, status, note, sources, plan_item):
    return {
        "claim": claim,
        "status": status,
        "note": note,
        "conflict": None,
        "sources": sources,
        "planItem": plan_item,
    }


def _compare_answer(extra_finding, questions):
    return {
        "findings": [
            _finding(
                "11월 8일 대금 15만 원을 받았습니다",
                "MATCH",
                "거래내역서의 입금 행과 같습니다.",
                [_source("TRANSACTION", transaction_id="t2")],
                0,
            ),
            extra_finding,
        ],
        "recommendedDocs": [],
        "opinions": [],
        "questions": questions,
    }


def _install(monkeypatch, answer):
    return fake_claude.install(
        monkeypatch,
        [
            fake_claude.tool_use(("p1", "make_plan", PLAN), ("u1", "get_transactions", TX_QUERY)),
            fake_claude.text(answer),
            fake_claude.text(DRAFT),
        ],
    )


def _first_payload(request):
    return json.loads(request["messages"][0]["content"][0]["text"])


def test_t25c_answers_reach_agent_masked_and_quotes_verify(claude_app, monkeypatch):
    client = claude_app
    first_answer = _compare_answer(
        _finding(
            "물건은 다음 날 택배로 보냈습니다",
            "STATEMENT_ONLY",
            "사연에만 있고 자료가 없습니다.",
            [_source("NARRATIVE", quote="물건은 다음 날 택배로 보냈습니다")],
            1,
        ),
        [
            {
                "text": "합의는 12만 원인데 입금은 15만 원이에요. 금액이 달라진 이유가 있나요?",
                "why": "자료와 어긋난 금액은 은행이 설명을 요청할 수 있어요.",
                "findingIndexes": [0],
                "lawRefs": [],
            }
        ],
    )
    sdk1 = _install(monkeypatch, first_answer)
    case_id, auth = flow.sample(client)
    assert flow.run(client, case_id, auth)["status"] == "SUCCEEDED"
    first = _first_payload(sdk1.requests[0])
    assert first["answers"] == []
    assert first["previousRun"] is None
    question = _questions(client, case_id, auth)[0]

    second_answer = _compare_answer(
        _finding(
            "추가 주문으로 4개 15만 원이 됐습니다",
            "STATEMENT_ONLY",
            "답에만 있고 자료가 없습니다.",
            [_source("NARRATIVE", quote=ANSWER_QUOTE)],
            None,
        ),
        [],
    )
    sdk2 = _install(monkeypatch, second_answer)
    run = flow.run(client, case_id, auth, {"answers": [_answer(question["questionId"], ANSWER)]})
    assert run["status"] == "SUCCEEDED", run

    # 대조 첫 메시지: 질문·답(이름 가림)과 지난 분석 성찰
    payload = _first_payload(sdk2.requests[0])
    assert payload["answers"] == [
        {"question": question["text"], "answer": ANSWER.replace("최유나", "최*나")}
    ]
    previous = payload["previousRun"]
    assert [(f["claim"], f["status"]) for f in previous["findings"]] == [
        ("물건은 다음 날 택배로 보냈습니다", "STATEMENT_ONLY")
    ]
    assert previous["planCheck"].startswith("계획한 확인 2개")
    assert set(previous) == {
        "findings",
        "planCheck",
        "sentencesNeedingCheck",
        "opinionsNeedingCheck",
    }
    # 초안 첫 메시지에도 가린 답
    draft_request = next(r for r in sdk2.requests if "uploadedDocuments" in _first_payload(r))
    assert _first_payload(draft_request)["answers"] == payload["answers"]
    # 원래 이름은 어떤 요청에도 없다
    assert all(
        "최유나" not in json.dumps(r["messages"], ensure_ascii=False, default=str)
        for r in sdk2.requests
    )

    # 답을 인용한 NARRATIVE 근거는 verified
    result = _result(client, case_id, auth)
    finding = next(f for f in result["findings"] if f["claim"].startswith("추가 주문"))
    assert finding["sources"][0]["kind"] == "NARRATIVE"
    assert finding["sources"][0]["verified"] is True
    assert [a["answer"] for a in result["agentReview"]["answered"]] == [ANSWER]
