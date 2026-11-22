"""T10 상담 안내(코드 표현 목록 + AI 문맥 확인)와 판정 필드 부재.

계약 테스트(README 승인 목록): T10-a 결과 모양, T10-b 이전 초안 삭제, T10-c 걸리지 않음,
T10-d AI 문맥 확인(가짜 SDK), T10-e 판정 필드 부재.
"""

import json

import fake_claude
import flow
import pytest

from app.models import Draft, UsageEvent
from app.services.safety import find_candidates, find_phrases

API = flow.API
LENDING = (
    "아는 형이 부탁해서 통장을 빌려주고 30만 원을 받았습니다. "
    "그 뒤 계좌가 지급정지됐다는 통지를 받았습니다."
)
NEGATED = (
    "온라인 쇼핑몰을 운영합니다. 통장을 빌려준 적이 없습니다. "
    "11월 8일 가죽 지갑 대금 15만 원을 받았습니다."
)
REFERRAL_KEYS = {"code", "matchedPhrases", "message", "contacts"}


def _result(client, case_id, auth):
    res = client.get(f"{API}/cases/{case_id}/result", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _draft_status(client, case_id, auth):
    return client.get(f"{API}/cases/{case_id}/draft", headers=auth).status_code


def _assert_referral_result(result, phrases):
    referral = result["referral"]
    assert set(referral) == REFERRAL_KEYS
    assert referral["code"] == "LEGAL_CONSULT"
    assert referral["matchedPhrases"] == phrases
    assert referral["message"]
    assert [c["phone"] for c in referral["contacts"]] == ["132", "1332"]
    assert result["findings"] == []
    assert result["draft"] is None
    assert result["unreadEvidence"] == []
    summary = result["summary"]
    assert set(summary["findingCounts"].values()) == {0}
    assert summary["missingDocuments"] == 0
    assert summary["sentencesNeedingCheck"] == 0
    assert summary["unreadEvidence"] == 0
    # 체크리스트는 평소대로, 의견 없이 상황을 묻는 질문
    assert result["checklist"]["items"]
    review = result["agentReview"]
    assert review["opinions"] == []
    assert len(review["questions"]) >= 1
    assert all(q["findingIds"] == [] for q in review["questions"])


# ---- T10-a 상담 안내 결과 모양(가짜 분석) ----


def test_t10a_referral_result_shape(client):
    case_id, auth = flow.sample(client, "GOODS")
    run = flow.run(client, case_id, auth, {"narrative": LENDING})
    assert run["status"] == "SUCCEEDED"
    types = [s["type"] for s in run["steps"]]
    assert "SAFETY" in types
    # 대조·초안 step이 없다
    assert "FINDING" not in types and "DRAFT" not in types
    assert [s["status"] for s in run["stages"]] == ["DONE", "DONE", "DONE"]

    _assert_referral_result(_result(client, case_id, auth), ["통장을 빌려"])
    assert _draft_status(client, case_id, auth) == 404
    with client.app.state.session_factory() as db:
        event = db.query(UsageEvent).filter_by(run_id=run["runId"]).one()
        assert event.referral is True


# ---- T10-b 다시 분석해 상담 안내로 끝나면 이전 초안 삭제 ----


def test_t10b_referral_deletes_previous_draft(client):
    case_id, auth = flow.sample(client, "GOODS")
    flow.run(client, case_id, auth)
    draft = client.get(f"{API}/cases/{case_id}/draft", headers=auth).json()["draft"]
    # 직접 고친 초안이 있어도(확인창 뒤 덮어쓰기) 상담 안내로 끝나면 지운다
    sentences = [{"sentenceId": s["sentenceId"], "text": s["text"]} for s in draft["sentences"]]
    res = client.put(
        f"{API}/cases/{case_id}/draft",
        json={"expectedVersion": draft["version"], "sentences": sentences[:1]},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    run = flow.run(client, case_id, auth, {"narrative": LENDING, "overwriteEditedDraft": True})
    assert run["status"] == "SUCCEEDED"
    assert _draft_status(client, case_id, auth) == 404
    with client.app.state.session_factory() as db:
        assert db.query(Draft).filter_by(case_id=case_id).count() == 0
    # 지웠으므로 다음 분석은 고친 초안 확인(409) 없이 시작된다
    assert flow.start(client, case_id, auth, {"narrative": NEGATED}).status_code == 202


# ---- T10-c 걸리지 않음 ----


@pytest.mark.parametrize("scenario", ["GOODS", "UNEXPECTED"])
def test_t10c_samples_are_not_referred(client, scenario):
    case_id, auth = flow.sample(client, scenario)
    run = flow.run(client, case_id, auth)
    assert "SAFETY" not in [s["type"] for s in run["steps"]]
    result = _result(client, case_id, auth)
    assert result["referral"] is None
    assert result["draft"] is not None


def test_t10c_negated_sentence_is_not_referred(client):
    case_id, auth = flow.sample(client, "GOODS")
    flow.run(client, case_id, auth, {"narrative": NEGATED})
    assert _result(client, case_id, auth)["referral"] is None


def test_phrase_groups_and_order():
    text = (
        "체크카드를 건넸고 비밀번호도 알려줬어요. 환전 알바라고 했습니다. "
        "들어온 돈을 인출해서 모르는 사람에게 전달했습니다. 체크카드를 건넸고요."
    )
    assert find_phrases([text]) == [
        "체크카드를 건넸",
        "비밀번호도 알려",
        "환전 알바",
        "돈을 인출해서 모르는 사람에게 전달",
    ]
    assert find_phrases(["통장을 빌려달라고 했지만 거절했습니다."]) == []
    assert find_phrases(["카드를 판매하는 가게에서 일합니다."]) == []


# ---- T10-d AI 문맥 확인(가짜 SDK) ----

MIXED = (
    "친구가 통장을 빌려주면 돈을 준다는 이야기를 듣고 걱정이 됐습니다. 저는 온라인 쇼핑몰을 "
    "운영하고 11월 8일 가죽 지갑 대금 15만 원을 받았습니다."
)
TX_QUERY = {
    "reason": "사연의 11월 8일 대금 입금을 확인하려고",
    "from": "2026-11-01",
    "to": "2026-11-10",
    "direction": "IN",
    "counterparty": None,
    "minAmount": None,
    "maxAmount": None,
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


def _answer(consult):
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
                "planItem": None,
            }
        ],
        "recommendedDocs": [],
        "opinions": [],
        "questions": [
            {
                "text": "어떤 일로 통장 이야기를 듣게 됐는지 알려 주세요.",
                "why": "사연의 표현만으로는 상황을 알 수 없어요.",
                "findingIndexes": [0],
                "lawRefs": [],
            }
        ],
        "consult": consult,
    }


def _claude(client, monkeypatch, narrative, consult):
    sdk = fake_claude.install(
        monkeypatch,
        [
            fake_claude.tool_use(("u1", "get_transactions", TX_QUERY)),
            fake_claude.text(_answer(consult)),
            fake_claude.text(DRAFT),
        ],
    )
    case_id, auth = flow.sample(client)
    run = flow.run(client, case_id, auth, {"narrative": narrative})
    assert run["status"] == "SUCCEEDED", run
    return run, _result(client, case_id, auth), sdk, (case_id, auth)


def _steps(run, type_):
    return [s for s in run["steps"] if s["type"] == type_]


def test_t10d_verified_quote_becomes_matched_phrase(claude_app, monkeypatch):
    consult = {"recommend": True, "quotes": ["부탁해서 통장을 빌려주고"], "reason": "계좌를 넘김"}
    run, result, sdk, (case_id, auth) = _claude(claude_app, monkeypatch, LENDING, consult)
    first = json.loads(sdk.requests[0]["messages"][0]["content"][0]["text"])
    assert first["checkPhrases"] == ["통장을 빌려"]
    _assert_referral_result(result, ["부탁해서 통장을 빌려주고"])
    assert _steps(run, "SAFETY")
    # 초안 요청을 보내지 않았다
    assert len(sdk.requests) == 2
    assert _draft_status(claude_app, case_id, auth) == 404


def test_t10d_unverified_quote_falls_back_to_code_phrases(claude_app, monkeypatch):
    consult = {"recommend": True, "quotes": ["계좌를 팔았습니다"], "reason": "계좌를 넘김"}
    run, result, _, _ = _claude(claude_app, monkeypatch, LENDING, consult)
    assert result["referral"]["matchedPhrases"] == ["통장을 빌려"]
    assert [s["title"] for s in _steps(run, "VERIFY")] == ["상담 안내 인용 확인"]


def test_t10d_unverified_quote_without_code_phrase_is_not_referred(claude_app, monkeypatch):
    consult = {"recommend": True, "quotes": ["계좌를 팔았습니다"], "reason": "계좌를 넘김"}
    narrative = "온라인 쇼핑몰을 운영합니다. 11월 8일 가죽 지갑 대금 15만 원을 받았습니다."
    run, result, _, _ = _claude(claude_app, monkeypatch, narrative, consult)
    assert result["referral"] is None
    assert result["draft"] is not None
    verify = [s["summary"] for s in _steps(run, "VERIFY")]
    assert "원문에서 확인한 표현이 없어 상담 안내를 하지 않았습니다." in verify
    assert _steps(run, "SAFETY") == []


def test_t10d_agent_declines_even_when_code_found(claude_app, monkeypatch):
    consult = {"recommend": False, "quotes": [], "reason": "남의 이야기를 들은 것이라 해당 없음"}
    run, result, _, _ = _claude(claude_app, monkeypatch, MIXED, consult)
    assert result["referral"] is None
    assert result["draft"] is not None
    safety = _steps(run, "SAFETY")
    assert len(safety) == 1
    assert safety[0]["summary"].startswith("사연의 '통장을 빌려'를 문맥으로 확인해 상담 안내는")


# ---- T10-e 판정 필드 부재 ----

JUDGEMENT_WORDS = (
    "release",
    "accept",
    "approv",
    "verdict",
    "judg",
    "decision",
    "likelihood",
    "probab",
    "chance",
    "score",
    "outcome",
    "eligib",
    "predict",
)
# 계약에 있는 서류 종류 칸(받는 서류 종류)이라 판정과 무관하다
ALLOWED_KEYS = {"acceptedDocTypes"}


def _keys(value, found):
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(value, list):
        for v in value:
            _keys(v, found)
    return found


@pytest.mark.parametrize("narrative", [None, LENDING])
@pytest.mark.parametrize("scenario", ["GOODS", "UNEXPECTED"])
def test_t10e_no_judgement_keys(client, scenario, narrative):
    case_id, auth = flow.sample(client, scenario)
    flow.run(client, case_id, auth, {"narrative": narrative} if narrative else None)
    payloads = [_result(client, case_id, auth)]
    draft = client.get(f"{API}/cases/{case_id}/draft", headers=auth)
    if draft.status_code == 200:
        payloads.append(draft.json())
    for payload in payloads:
        keys = _keys(payload, set()) - ALLOWED_KEYS
        bad = {k for k in keys for w in JUDGEMENT_WORDS if w in k.lower()}
        assert bad == set()
    assert payloads[0]["agentReview"] is not None


# ---- 11/22 결정: 코드는 후보만 찾고 판단은 AI가 한다 ----


def test_candidates_keep_negated_phrases():
    assert find_candidates([NEGATED]) == ["통장을 빌려"]
    assert find_phrases([NEGATED]) == []


def test_negated_phrase_goes_to_agent_and_agent_decides(claude_app, monkeypatch):
    consult = {"recommend": False, "quotes": [], "reason": "빌려준 적이 없다는 문장"}
    run, result, sdk, _ = _claude(claude_app, monkeypatch, NEGATED, consult)
    first = json.loads(sdk.requests[0]["messages"][0]["content"][0]["text"])
    # 부정문이어도 코드가 미리 거르지 않고 후보로 넘긴다
    assert first["checkPhrases"] == ["통장을 빌려"]
    assert result["referral"] is None
    assert len(_steps(run, "SAFETY")) == 1


def test_negated_phrase_is_not_used_when_agent_quote_is_wrong(claude_app, monkeypatch):
    # AI가 권했지만 인용이 원문에 없으면 대신 보여 줄 표현은 부정문을 뺀 목록에서만 고른다
    consult = {"recommend": True, "quotes": ["계좌를 팔았습니다"], "reason": "계좌를 넘김"}
    run, result, _, _ = _claude(claude_app, monkeypatch, NEGATED, consult)
    assert result["referral"] is None
    verify = [s["summary"] for s in _steps(run, "VERIFY")]
    assert "원문에서 확인한 표현이 없어 상담 안내를 하지 않았습니다." in verify
