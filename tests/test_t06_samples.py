"""T06 체험 계정(샘플 사건). 계약 테스트 6(11/21 승인)과 T06-a·b(11/21 승인)."""

from datetime import timedelta

import pytest

from app.services.deadline import today_kst

EXPECTED_DOCS = {
    "GOODS": ["TRANSACTION_RECORD", "CHAT", "BUSINESS_REG"],
    "UNEXPECTED": ["TRANSACTION_RECORD", "CHAT"],
}


def _create_sample(client, scenario: str) -> tuple[str, dict[str, str], dict]:
    res = client.post("/api/v1/cases/sample", json={"scenario": scenario})
    assert res.status_code == 201, res.text
    body = res.json()
    return body["caseId"], {"X-Case-Token": body["caseToken"]}, body


# 계약 테스트 6: 체험 계정 사건이 서류가 채워진 채 생기고 바로 분석 가능한 상태
@pytest.mark.parametrize("scenario", ["GOODS", "UNEXPECTED"])
def test_sample_case_is_ready_for_analysis(client, scenario):
    case_id, auth, body = _create_sample(client, scenario)
    assert body["caseToken"].startswith("pk_")
    case = body["case"]
    assert case["isSample"] is True
    assert case["sampleScenario"] == scenario
    assert case["inflow"]["type"] == scenario
    assert case["status"] == "DRAFT"
    assert case["inputVersion"] == 1
    assert len(case["narrative"]) >= 20
    assert case["evidenceCount"] == len(EXPECTED_DOCS[scenario])

    # 통지일·공고일은 오늘 기준 상대 날짜, D-day가 계산됨
    today = today_kst()
    assert case["noticeReceivedDate"] == (today - timedelta(days=6)).isoformat()
    assert case["publicNoticeDate"] == (today - timedelta(days=4)).isoformat()
    assert case["deadline"]["state"] in ("OK", "URGENT")

    items = client.get(f"/api/v1/cases/{case_id}/evidence", headers=auth).json()["items"]
    assert [i["docType"] for i in items] == EXPECTED_DOCS[scenario]
    assert all(i["isSample"] and i["extractStatus"] == "UPLOADED" for i in items)

    # 분석 시작 조건: 사연 20자 이상 + "AI 분석에 필요" 항목(거래내역서) 충족
    checklist = client.get(f"/api/v1/cases/{case_id}/checklist", headers=auth).json()["items"]
    required = [i for i in checklist if i["requiredForAnalysis"]]
    assert len(required) == 1
    assert required[0]["status"] == "SATISFIED"


# T06-a: 같은 시나리오를 두 번 만들면 모두 따로이고, 한쪽 서류를 지워도 다른 쪽은 그대로
def test_each_sample_case_is_independent(client):
    case_1, auth_1, body_1 = _create_sample(client, "GOODS")
    case_2, auth_2, body_2 = _create_sample(client, "GOODS")
    assert case_1 != case_2
    assert body_1["caseToken"] != body_2["caseToken"]

    items_1 = client.get(f"/api/v1/cases/{case_1}/evidence", headers=auth_1).json()["items"]
    items_2 = client.get(f"/api/v1/cases/{case_2}/evidence", headers=auth_2).json()["items"]
    assert not {i["evidenceId"] for i in items_1} & {i["evidenceId"] for i in items_2}

    first = items_1[0]["evidenceId"]
    res = client.delete(f"/api/v1/cases/{case_1}/evidence/{first}", headers=auth_1)
    assert res.status_code == 204
    case_1_now = client.get(f"/api/v1/cases/{case_1}", headers=auth_1).json()["case"]
    assert case_1_now["evidenceCount"] == 2
    assert case_1_now["inputVersion"] == 2  # 샘플을 바꾸면 "샘플 그대로"가 아니게 됨
    case_2_now = client.get(f"/api/v1/cases/{case_2}", headers=auth_2).json()["case"]
    assert case_2_now["evidenceCount"] == 3
    assert case_2_now["inputVersion"] == 1


# T06-b: 샘플 목록·파일 내려받기, 없는 파일 404, SALARY 400
def test_samples_list_and_download(client):
    res = client.get("/api/v1/samples")
    assert res.status_code == 200
    items = res.json()["items"]
    assert [s["scenario"] for s in items] == ["GOODS", "UNEXPECTED"]
    for sample in items:
        assert [f["docType"] for f in sample["files"]] == EXPECTED_DOCS[sample["scenario"]]
        for f in sample["files"]:
            assert set(f) == {"name", "docType", "url"}
            assert f["url"].startswith("/api/v1/samples/")
            file_res = client.get(f["url"])
            assert file_res.status_code == 200
            expected = "application/pdf" if f["url"].endswith(".pdf") else "image/png"
            assert file_res.headers["content-type"] == expected
            assert file_res.content[:4] in (b"%PDF", b"\x89PNG")

    for url in ("/api/v1/samples/goods/secret.pdf", "/api/v1/samples/goods/..%2F..%2Fmain.py"):
        res = client.get(url)
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "NOT_FOUND"

    res = client.post("/api/v1/cases/sample", json={"scenario": "SALARY"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "scenario" in res.json()["error"]["details"]["fields"]


# 아래는 계약 테스트가 아닌 동작 확인


def test_unknown_scenario_is_400(client):
    res = client.post("/api/v1/cases/sample", json={"scenario": "LOAN"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_sample_narratives_avoid_referral_phrases():
    # 상담 안내 표현 목록(계약 4.9)에 걸리면 샘플 시연이 초안 없이 끝난다(목록 자체는 T10)
    from app.services.samples import SCENARIOS

    phrases = ["통장을 빌려", "대여", "양도", "비밀번호", "환전", "구매대행", "송금 알바", "인출"]
    for scenario in SCENARIOS.values():
        assert not [p for p in phrases if p in scenario.narrative]
