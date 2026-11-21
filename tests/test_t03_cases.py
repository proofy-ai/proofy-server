"""T03 사건 API.

계약 테스트 4·5·7(docs/tasks/README.md, 11/21 승인)과 추가 테스트 T03-a~c(11/21 승인).
"""

from datetime import timedelta

import pytest

from app.models import Case
from app.services.clock import utc_now
from app.services.deadline import today_kst

CASE_BODY = {
    "noticeReceivedDate": "2026-11-10",
    "publicNoticeDate": "2026-11-17",
    "inflow": {"type": "GOODS", "amountKrw": 150000, "occurredAt": None},
    "hasPriorFreeze": False,
}


def _create(client) -> tuple[str, str, dict]:
    res = client.post("/api/v1/cases", json=CASE_BODY)
    assert res.status_code == 201, res.text
    body = res.json()
    return body["caseId"], body["caseToken"], body


def _auth(token: str) -> dict[str, str]:
    return {"X-Case-Token": token}


def _assert_error(res, status: int, code: str) -> None:
    assert res.status_code == status, res.text
    error = res.json()["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]


# 계약 테스트 4: caseToken은 생성 응답에서만 주고 조회 응답에는 없음
def test_case_token_only_in_create_response(client):
    case_id, token, body = _create(client)
    assert token.startswith("pk_")
    assert body["case"]["caseId"] == case_id
    assert body["case"]["inputVersion"] == 1

    res = client.get(f"/api/v1/cases/{case_id}", headers=_auth(token))
    assert res.status_code == 200
    assert token not in res.text
    assert "caseToken" not in res.text
    assert set(res.json()) == {"case"}


# 계약 테스트 5: 오류 응답 모양이 같음, 토큰 없음·불일치 401, 없는 사건 404
def test_auth_errors_share_error_shape(client):
    case_id, _, _ = _create(client)

    _assert_error(client.get(f"/api/v1/cases/{case_id}"), 401, "CASE_TOKEN_INVALID")
    _assert_error(
        client.get(f"/api/v1/cases/{case_id}", headers=_auth("pk_wrong")), 401, "CASE_TOKEN_INVALID"
    )
    _assert_error(
        client.get("/api/v1/cases/00000000-0000-0000-0000-000000000000", headers=_auth("pk_any")),
        404,
        "CASE_NOT_FOUND",
    )


# 계약 테스트 7: 사건 A의 토큰으로 사건 B를 조회·수정·삭제하면 막힘
def test_token_of_other_case_is_rejected(client):
    _, token_a, _ = _create(client)
    case_b, token_b, _ = _create(client)
    url_b = f"/api/v1/cases/{case_b}"

    _assert_error(client.get(url_b, headers=_auth(token_a)), 401, "CASE_TOKEN_INVALID")
    _assert_error(
        client.patch(url_b, json={"narrative": "바꾸려는 사연"}, headers=_auth(token_a)),
        401,
        "CASE_TOKEN_INVALID",
    )
    _assert_error(client.delete(url_b, headers=_auth(token_a)), 401, "CASE_TOKEN_INVALID")

    res = client.get(url_b, headers=_auth(token_b))
    assert res.status_code == 200
    assert res.json()["case"]["narrative"] is None
    assert res.json()["case"]["inputVersion"] == 1


# T03-a: 미래 통지일 → 400, details.fields에 noticeReceivedDate
def test_future_notice_date_is_rejected(client):
    tomorrow = (today_kst() + timedelta(days=1)).isoformat()
    res = client.post("/api/v1/cases", json={**CASE_BODY, "noticeReceivedDate": tomorrow})
    _assert_error(res, 400, "VALIDATION_ERROR")
    assert "noticeReceivedDate" in res.json()["error"]["details"]["fields"]


# T03-b: 값이 실제로 바뀔 때만 inputVersion +1
def test_input_version_increases_only_on_real_change(client):
    case_id, token, _ = _create(client)
    url = f"/api/v1/cases/{case_id}"
    narrative = {"narrative": "거래처에 가죽 지갑 3개를 납품하고 대금을 받았습니다."}

    res = client.patch(url, json=narrative, headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["case"]["inputVersion"] == 2

    res = client.patch(url, json=narrative, headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["case"]["inputVersion"] == 2


# T03-c: 만료된 사건 → 404 CASE_NOT_FOUND
def test_expired_case_is_not_found(client, app):
    case_id, token, _ = _create(client)
    with app.state.session_factory() as db:
        case = db.get(Case, case_id)
        case.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()

    _assert_error(
        client.get(f"/api/v1/cases/{case_id}", headers=_auth(token)), 404, "CASE_NOT_FOUND"
    )


# 아래는 계약 테스트가 아닌 동작 확인(필요할 때 바로 쓰는 테스트)


def test_case_response_has_contract_keys(client):
    _, _, body = _create(client)
    case = body["case"]
    assert set(case) == {
        "caseId", "status", "isSample", "sampleScenario", "noticeReceivedDate", "publicNoticeDate",
        "inflow", "hasPriorFreeze", "narrative", "inputVersion", "deadline", "evidenceCount",
        "latestRun", "hasResult", "createdAt", "expiresAt",
    }  # fmt: skip
    assert case["status"] == "DRAFT"
    assert case["inflow"] == {"type": "GOODS", "amountKrw": 150000, "occurredAt": None}
    assert case["deadline"]["deadlineDate"] == "2027-01-17"
    assert case["createdAt"].endswith("Z") and len(case["createdAt"]) == 20


@pytest.mark.parametrize(
    "change",
    [
        {"inflow": {"type": "GOODS", "amountKrw": "150000", "occurredAt": None}},  # 문자열 금액
        {"inflow": {"type": "GOODS", "amountKrw": 0, "occurredAt": None}},
        {"inflow": {"type": "LOAN", "amountKrw": 150000, "occurredAt": None}},
        {"hasPriorFreeze": "no"},
    ],
)
def test_invalid_create_body_is_400(client, change):
    _assert_error(
        client.post("/api/v1/cases", json={**CASE_BODY, **change}), 400, "VALIDATION_ERROR"
    )


def test_has_prior_freeze_key_is_required_but_null_allowed(client):
    body = {k: v for k, v in CASE_BODY.items() if k != "hasPriorFreeze"}
    _assert_error(client.post("/api/v1/cases", json=body), 400, "VALIDATION_ERROR")
    res = client.post("/api/v1/cases", json={**CASE_BODY, "hasPriorFreeze": None})
    assert res.status_code == 201
    assert res.json()["case"]["hasPriorFreeze"] is None


def test_patch_rules(client):
    case_id, token, _ = _create(client)
    url = f"/api/v1/cases/{case_id}"

    # 통지일은 null로 지울 수 없다
    res = client.patch(url, json={"noticeReceivedDate": None}, headers=_auth(token))
    _assert_error(res, 400, "VALIDATION_ERROR")
    assert "noticeReceivedDate" in res.json()["error"]["details"]["fields"]

    # 사연 2000자 초과
    res = client.patch(url, json={"narrative": "가" * 2001}, headers=_auth(token))
    _assert_error(res, 400, "VALIDATION_ERROR")

    # 공고일을 null(모름)로 바꾸면 D-day가 "공고일 확인 필요"
    res = client.patch(url, json={"publicNoticeDate": None}, headers=_auth(token))
    case = res.json()["case"]
    assert case["publicNoticeDate"] is None
    assert case["deadline"]["state"] == "UNKNOWN_NOTICE_DATE"
    assert case["inputVersion"] == 2

    # 입금 정보는 통째로 교체, 같은 값이면 그대로
    new_inflow = {"type": "UNEXPECTED", "amountKrw": 100000, "occurredAt": "2026-11-05"}
    res = client.patch(url, json={"inflow": new_inflow}, headers=_auth(token))
    assert res.json()["case"]["inflow"] == new_inflow
    assert res.json()["case"]["inputVersion"] == 3
    res = client.patch(url, json={"inflow": new_inflow}, headers=_auth(token))
    assert res.json()["case"]["inputVersion"] == 3

    # 실패한 수정은 아무것도 바꾸지 않는다
    assert client.get(url, headers=_auth(token)).json()["case"]["inputVersion"] == 3


def test_delete_case(client, app):
    case_id, token, _ = _create(client)
    url = f"/api/v1/cases/{case_id}"

    res = client.delete(url, headers=_auth(token))
    assert res.status_code == 204
    assert res.content == b""
    _assert_error(client.get(url, headers=_auth(token)), 404, "CASE_NOT_FOUND")

    from app.models import CaseInflow

    with app.state.session_factory() as db:
        assert db.query(CaseInflow).filter_by(case_id=case_id).count() == 0
