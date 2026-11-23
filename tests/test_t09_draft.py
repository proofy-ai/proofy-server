"""T09 초안 API(계약 4.12). 계약 테스트 T09-a~d(11/22 사용자 "기존 계약대로 완성"으로 진행)."""

import time

import pytest

from app.services.drafts import amounts, mentions_statement, month_days
from tests.test_t08_result import API, _analyze, _result, _sample

DRAFT_KEYS = {
    "version",
    "basedOnRunId",
    "sentences",
    "warnings",
    "unconfirmedCount",
    "fullText",
    "updatedAt",
}
SENTENCE_KEYS = {
    "sentenceId",
    "section",
    "text",
    "origin",
    "findingIds",
    "needsCheck",
    "needsCheckReason",
    "confirmed",
    "edited",
}


def _draft(client, case_id: str, auth: dict[str, str]) -> dict:
    res = client.get(f"{API}/cases/{case_id}/draft", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["draft"]


def _put(client, case_id: str, auth: dict[str, str], body: dict):
    return client.put(f"{API}/cases/{case_id}/draft", json=body, headers=auth)


def _keep_all(draft: dict) -> list[dict]:
    return [{"sentenceId": s["sentenceId"], "text": s["text"]} for s in draft["sentences"]]


def _wait(client, case_id: str, auth: dict[str, str], run_id: str) -> None:
    end = time.monotonic() + 60
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            assert run["status"] == "SUCCEEDED", run
            return
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def _analyzed(client, scenario: str = "GOODS") -> tuple[str, dict[str, str], dict]:
    case_id, auth = _sample(client, scenario)
    run = _analyze(client, case_id, auth)
    return case_id, auth, run


# T09-a: GOODS 초안 응답 모양과 확인 필요 규칙
def test_goods_draft_shape_and_rules(client):
    case_id, auth, run = _analyzed(client)
    findings = _result(client, case_id, auth)["findings"]
    f1, f2, f3 = (f["findingId"] for f in findings)
    assert [f["status"] for f in findings] == ["MATCH", "CONFLICT", "STATEMENT_ONLY"]

    draft = _draft(client, case_id, auth)
    assert set(draft) == DRAFT_KEYS
    assert draft["version"] == 1
    assert draft["basedOnRunId"] == run["runId"]
    assert draft["warnings"] == []

    s1, s2, s3 = draft["sentences"]
    for s in draft["sentences"]:
        assert set(s) == SENTENCE_KEYS
        assert (s["origin"], s["confirmed"], s["edited"]) == ("AI", False, False)
    assert [s["section"] for s in draft["sentences"]] == [
        "DEPOSIT_REASON",
        "DEPOSIT_REASON",
        "NO_INVOLVEMENT",
    ]
    # "150,000원"은 f2의 진술 값이라 분석기가 연결하지 않았어도 서버가 붙인다
    assert "150,000원" in s1["text"]
    assert s1["findingIds"] == [f1, f2]
    assert (s1["needsCheck"], s1["needsCheckReason"]) == (True, "CONFLICT")
    assert s2["findingIds"] == [f3]
    assert (s2["needsCheck"], s2["needsCheckReason"]) == (True, "NO_SOURCE")
    assert s3["findingIds"] == []
    assert (s3["needsCheck"], s3["needsCheckReason"]) == (True, "NO_SOURCE")

    assert draft["unconfirmedCount"] == 3
    assert draft["fullText"] == f"{s1['text']} {s2['text']}\n\n{s3['text']}"


# T09-b: PUT 규칙
def test_put_rules(client):
    case_id, auth, _ = _analyzed(client)
    draft = _draft(client, case_id, auth)
    s1, s2, s3 = draft["sentences"]

    body = {
        "expectedVersion": 1,
        "sentences": [
            # 글을 바꾸고 같은 요청에서 확인 → true
            {"sentenceId": s1["sentenceId"], "text": s1["text"] + " 추가 설명", "confirmed": True},
            # 글을 바꾸고 confirmed 생략 → false
            {"sentenceId": s2["sentenceId"], "text": "판매한 물건은 11월 9일 택배로 보냈습니다."},
            # 새 문장(section은 보내도 무시)
            {
                "sentenceId": None,
                "text": "송장 번호 화면을 함께 제출합니다.",
                "section": "VICTIM_CONTEXT",
            },
            # s3은 빠짐 → 삭제
        ],
    }
    res = _put(client, case_id, auth, body)
    assert res.status_code == 200, res.text
    saved = res.json()["draft"]
    assert saved["version"] == 2
    n1, n2, n3 = saved["sentences"]
    assert len(saved["sentences"]) == 3
    assert s3["sentenceId"] not in {s["sentenceId"] for s in saved["sentences"]}

    assert (n1["edited"], n1["confirmed"]) == (True, True)
    # 고쳐도 근거·확인 필요는 그대로
    assert (n1["findingIds"], n1["needsCheck"], n1["needsCheckReason"]) == (
        s1["findingIds"],
        True,
        "CONFLICT",
    )
    assert (n2["edited"], n2["confirmed"], n2["needsCheckReason"]) == (True, False, "NO_SOURCE")
    assert n3["origin"] == "USER"
    assert (n3["section"], n3["needsCheck"], n3["needsCheckReason"]) == (None, False, None)
    assert n3["findingIds"] == []
    assert saved["unconfirmedCount"] == 1
    assert _draft(client, case_id, auth) == saved

    # 글은 그대로, 확인만 → 이전에 확인한 문장이 그대로 남고 edited는 안 바뀐다
    keep = _keep_all(saved)
    keep[1]["confirmed"] = True
    res = _put(client, case_id, auth, {"expectedVersion": 2, "sentences": keep})
    assert res.status_code == 200, res.text
    again = res.json()["draft"]
    assert [s["confirmed"] for s in again["sentences"]] == [True, True, False]
    assert again["unconfirmedCount"] == 0
    assert again["version"] == 3

    # 옛 버전으로 저장 → 409
    res = _put(client, case_id, auth, {"expectedVersion": 2, "sentences": keep})
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["code"] == "VERSION_CONFLICT"
    assert error["details"] == {"currentVersion": 3}


# T09-c: 다시 분석
def test_reanalysis_with_edited_draft(client):
    case_id, auth, _ = _analyzed(client)

    # 저장한 적 없으면 그냥 다시 분석된다
    second = _analyze(client, case_id, auth)
    draft = _draft(client, case_id, auth)
    assert draft["basedOnRunId"] == second["runId"]
    assert draft["version"] == 2

    keep = _keep_all(draft)
    keep[0]["confirmed"] = True
    res = _put(client, case_id, auth, {"expectedVersion": 2, "sentences": keep})
    assert res.status_code == 200, res.text

    res = client.post(f"{API}/cases/{case_id}/analysis-runs", json={}, headers=auth)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "DRAFT_HAS_EDITS"

    res = client.post(
        f"{API}/cases/{case_id}/analysis-runs", json={"overwriteEditedDraft": True}, headers=auth
    )
    assert res.status_code == 202, res.text
    third_id = res.json()["runId"]
    _wait(client, case_id, auth, third_id)
    draft = _draft(client, case_id, auth)
    assert draft["basedOnRunId"] == third_id
    assert draft["version"] == 4  # 이어서 +1(되돌리지 않음)
    assert all(s["confirmed"] is False for s in draft["sentences"])
    # 새 초안은 저장한 적이 없으므로 다시 분석이 409 없이 된다
    _analyze(client, case_id, auth)


# T09-d: 결과 API의 draft, 다른 사건 토큰
def test_result_draft_and_other_case_token(client):
    case_id, auth, _ = _analyzed(client)
    other_id, other_auth = _sample(client)
    result = _result(client, case_id, auth)
    draft = _draft(client, case_id, auth)
    assert result["draft"] == draft
    assert result["summary"]["sentencesNeedingCheck"] == 3

    res = client.get(f"{API}/cases/{case_id}/draft", headers=other_auth)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "CASE_TOKEN_INVALID"
    body = {"expectedVersion": 1, "sentences": _keep_all(draft)}
    res = _put(client, case_id, other_auth, body)
    assert res.status_code == 401
    assert _draft(client, case_id, auth)["version"] == 1


# 아래는 계약 테스트가 아닌 동작 확인


def test_draft_before_analysis_is_404(client):
    case_id, auth = _sample(client)
    res = client.get(f"{API}/cases/{case_id}/draft", headers=auth)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_unexpected_draft_sections(client):
    case_id, auth, run = _analyzed(client, "UNEXPECTED")
    draft = _draft(client, case_id, auth)
    sections = [s["section"] for s in draft["sentences"]]
    assert sections == [
        "DEPOSIT_REASON",
        "DEPOSIT_REASON",
        "NO_INVOLVEMENT",
        "VICTIM_CONTEXT",
        "VICTIM_CONTEXT",
    ]
    reasons = [s["needsCheckReason"] for s in draft["sentences"]]
    assert reasons == ["CONFLICT", None, "NO_SOURCE", None, "NO_SOURCE"]
    assert draft["fullText"].count("\n\n") == 2
    assert draft["warnings"] == []
    step = next(s for s in run["steps"] if s["type"] == "DRAFT")
    assert step["summary"] == "초안 문장 5개를 작성했습니다."


def test_deleting_conflict_sentence_adds_warning(client):
    case_id, auth, _ = _analyzed(client)
    findings = _result(client, case_id, auth)["findings"]
    draft = _draft(client, case_id, auth)
    res = _put(client, case_id, auth, {"expectedVersion": 1, "sentences": _keep_all(draft)[1:]})
    assert res.status_code == 200, res.text
    assert res.json()["draft"]["warnings"] == [
        {
            "code": "CONFLICT_NOT_IN_DRAFT",
            "findingId": findings[1]["findingId"],
            "message": "자료와 어긋난 내용이 초안에 설명되지 않았습니다.",
        }
    ]


@pytest.mark.parametrize(
    ("sentences", "field"),
    [
        ([{"sentenceId": "없는-문장", "text": "글"}], "sentences.0.sentenceId"),
        ([{"sentenceId": None, "text": "   "}], "sentences.0.text"),
    ],
)
def test_put_invalid_is_400(client, sentences, field):
    case_id, auth, _ = _analyzed(client)
    res = _put(client, case_id, auth, {"expectedVersion": 1, "sentences": sentences})
    assert res.status_code == 400
    error = res.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in error["details"]["fields"]
    assert _draft(client, case_id, auth)["version"] == 1


def test_number_and_date_parsing():
    assert amounts("대금 150,000원을 받았다") == {150_000}
    assert amounts("15만 원, 12만원") == {150_000, 120_000}
    assert month_days("2026년 11월 11일, 11/12") == {(11, 11), (11, 12)}
    conflict = {"field": "AMOUNT", "statement": "150,000원"}
    assert mentions_statement("15만 원을 받았습니다", conflict)
    assert not mentions_statement("12만 원을 받았습니다", conflict)
    assert mentions_statement("11월 11일 입금", {"field": "DATE", "statement": "11월 11일"})


def test_sample_file_is_attachment(client):
    items = client.get(f"{API}/samples").json()["items"]
    res = client.get(items[0]["files"][0]["url"])
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith("attachment")
