"""T04 서류 목록·체크리스트.

계약 관련 테스트 T04-a~d(11/21 승인). 기대값은 서버 상수가 아니라 계약 4.2 표를 옮겨 적은 것이다.
"""

import pytest

from app.services.checklist import UploadedEvidence, compute_status
from app.services.requirements import requirements_for

# (code, category, acceptedDocTypes, requiredForAnalysis) — 계약 v0.6.2 4.2
COMMON_HEAD = [
    ("OBJECTION_FORM", "OFFICIAL_REQUIRED", [], False),
    ("ID_COPY", "OFFICIAL_REQUIRED", [], False),
]
NOTICE = ("NOTICE", "OPTIONAL", ["NOTICE"], False)
EXPECTED = {
    "SALARY": [
        *COMMON_HEAD,
        ("SALARY_DEPOSIT", "TYPE_GUIDE", ["TRANSACTION_RECORD"], True),
        ("EMPLOYMENT_PROOF", "TYPE_GUIDE", ["INSURANCE_ELIGIBILITY", "EMPLOYMENT_CERT"], False),
        NOTICE,
    ],
    "GOODS": [
        *COMMON_HEAD,
        ("BUSINESS_REG", "TYPE_GUIDE", ["BUSINESS_REG"], False),
        ("COUNTERPARTY_CHAT", "TYPE_GUIDE", ["CHAT"], False),
        (
            "TRADE_DOCUMENT",
            "TYPE_GUIDE",
            ["CONTRACT", "TAX_INVOICE", "TRANSACTION_STATEMENT"],
            False,
        ),
        ("DEPOSIT_RECORD", "ANALYSIS_INPUT", ["TRANSACTION_RECORD"], True),
        NOTICE,
    ],
    "UNEXPECTED": [
        *COMMON_HEAD,
        ("THREAT_MESSAGE", "TYPE_GUIDE", ["CHAT"], False),
        ("UNKNOWN_DEPOSIT_RECORD", "ANALYSIS_INPUT", ["TRANSACTION_RECORD"], True),
        NOTICE,
        ("INCIDENT_REPORT", "OPTIONAL", ["OTHER"], False),
    ],
    "OTHER": [
        *COMMON_HEAD,
        ("DEPOSIT_RECORD", "ANALYSIS_INPUT", ["TRANSACTION_RECORD"], True),
        NOTICE,
    ],
}

CHECKLIST_ITEM_KEYS = {
    "itemId", "code", "label", "category", "status", "acceptedDocTypes",
    "requiredForAnalysis", "satisfiedBy", "checked", "note", "sourceRef",
}  # fmt: skip


def _create_case(client, inflow_type: str = "GOODS") -> tuple[str, dict[str, str]]:
    body = {
        "noticeReceivedDate": "2026-11-10",
        "publicNoticeDate": "2026-11-17",
        "inflow": {"type": inflow_type, "amountKrw": 150000, "occurredAt": None},
        "hasPriorFreeze": False,
    }
    res = client.post("/api/v1/cases", json=body)
    assert res.status_code == 201, res.text
    return res.json()["caseId"], {"X-Case-Token": res.json()["caseToken"]}


def _by_code(items: list[dict]) -> dict[str, dict]:
    return {i["code"]: i for i in items}


# T04-a: 유형별 목록이 계약 4.2 표와 같다
@pytest.mark.parametrize("inflow_type", ["SALARY", "GOODS", "UNEXPECTED", "OTHER"])
def test_requirements_match_contract(client, inflow_type):
    res = client.get("/api/v1/meta/requirements", params={"inflowType": inflow_type})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["inflowType"] == inflow_type

    actual = [
        (i["code"], i["category"], i["acceptedDocTypes"], i["requiredForAnalysis"])
        for i in body["items"]
    ]
    assert actual == EXPECTED[inflow_type]

    # "AI 분석에 필요"는 거래내역서 항목 하나뿐
    required = [i for i in body["items"] if i["requiredForAnalysis"]]
    assert len(required) == 1
    assert required[0]["acceptedDocTypes"] == ["TRANSACTION_RECORD"]

    # 신분증은 받지 않는다
    items = _by_code(body["items"])
    assert items["ID_COPY"]["uploadable"] is False
    assert items["OBJECTION_FORM"]["uploadable"] is False
    assert all(i["uploadable"] for c, i in items.items() if c not in ("ID_COPY", "OBJECTION_FORM"))


def test_requirements_without_or_with_bad_inflow_type_is_400(client):
    for params in ({}, {"inflowType": "LOAN"}):
        res = client.get("/api/v1/meta/requirements", params=params)
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# T04-b: 분석 전 체크리스트 모양·상태·missingCount, 체크하면 1 감소
def test_checklist_before_analysis(client):
    case_id, auth = _create_case(client, "GOODS")
    res = client.get(f"/api/v1/cases/{case_id}/checklist", headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {"items", "missingCount"}
    assert all(set(i) == CHECKLIST_ITEM_KEYS for i in body["items"])
    assert [i["code"] for i in body["items"]] == [c for c, *_ in EXPECTED["GOODS"]]

    items = _by_code(body["items"])
    assert items["ID_COPY"]["status"] == "NOT_COLLECTED"
    assert items["OBJECTION_FORM"]["status"] == "GUIDE_ONLY"
    missing = [c for c, i in items.items() if c not in ("ID_COPY", "OBJECTION_FORM")]
    assert all(items[c]["status"] == "MISSING" and items[c]["satisfiedBy"] == [] for c in missing)
    assert body["missingCount"] == len(missing) == 5

    item_id = items["TRADE_DOCUMENT"]["itemId"]
    res = client.patch(
        f"/api/v1/cases/{case_id}/checklist/{item_id}", json={"checked": True}, headers=auth
    )
    assert res.status_code == 200, res.text
    assert set(res.json()) == {"item"}
    assert res.json()["item"]["checked"] is True
    assert res.json()["item"]["status"] == "MISSING"  # 체크는 충족 여부와 별개

    body = client.get(f"/api/v1/cases/{case_id}/checklist", headers=auth).json()
    assert body["missingCount"] == 4
    assert _by_code(body["items"])["TRADE_DOCUMENT"]["itemId"] == item_id


# T04-c: acceptedDocTypes 중 하나만 있어도 충족, OTHER 서류가 INCIDENT_REPORT를 충족
def test_status_is_satisfied_by_any_accepted_doc_type():
    goods = {r.code: r for r in requirements_for("GOODS")}
    evidence = [
        UploadedEvidence("e1", "TAX_INVOICE"),
        UploadedEvidence("e2", "CHAT"),
        UploadedEvidence("e3", "TRANSACTION_STATEMENT"),
    ]
    assert compute_status(goods["TRADE_DOCUMENT"], evidence) == ("SATISFIED", ["e1", "e3"])
    assert compute_status(goods["COUNTERPARTY_CHAT"], evidence) == ("SATISFIED", ["e2"])
    assert compute_status(goods["BUSINESS_REG"], evidence) == ("MISSING", [])
    assert compute_status(goods["ID_COPY"], evidence) == ("NOT_COLLECTED", [])

    unexpected = {r.code: r for r in requirements_for("UNEXPECTED")}
    other = [UploadedEvidence("e9", "OTHER")]
    assert compute_status(unexpected["INCIDENT_REPORT"], other) == ("SATISFIED", ["e9"])
    assert compute_status(unexpected["THREAT_MESSAGE"], other) == ("MISSING", [])


# T04-d: 입금 유형을 바꾸면 목록이 바뀌고 같은 code의 checked는 유지
def test_inflow_type_change_rebuilds_list_and_keeps_checked(client):
    case_id, auth = _create_case(client, "GOODS")
    url = f"/api/v1/cases/{case_id}/checklist"
    items = _by_code(client.get(url, headers=auth).json()["items"])
    notice_id = items["NOTICE"]["itemId"]
    client.patch(f"{url}/{notice_id}", json={"checked": True}, headers=auth)
    client.patch(f"{url}/{items['TRADE_DOCUMENT']['itemId']}", json={"checked": True}, headers=auth)

    new_inflow = {"type": "UNEXPECTED", "amountKrw": 100000, "occurredAt": None}
    res = client.patch(f"/api/v1/cases/{case_id}", json={"inflow": new_inflow}, headers=auth)
    assert res.status_code == 200

    items = _by_code(client.get(url, headers=auth).json()["items"])
    assert list(items) == [c for c, *_ in EXPECTED["UNEXPECTED"]]
    assert items["NOTICE"]["itemId"] == notice_id
    assert items["NOTICE"]["checked"] is True
    assert items["THREAT_MESSAGE"]["checked"] is False

    # 다시 물품 거래로 돌아오면 빠졌던 항목은 새로 만든다(체크 없음)
    res = client.patch(
        f"/api/v1/cases/{case_id}", json={"inflow": {**new_inflow, "type": "GOODS"}}, headers=auth
    )
    items = _by_code(client.get(url, headers=auth).json()["items"])
    assert items["TRADE_DOCUMENT"]["checked"] is False
    assert items["NOTICE"]["checked"] is True


# 아래는 계약 테스트가 아닌 동작 확인


def test_patch_item_of_other_case_is_404(client):
    case_a, auth_a = _create_case(client)
    case_b, auth_b = _create_case(client)
    item_b = client.get(f"/api/v1/cases/{case_b}/checklist", headers=auth_b).json()["items"][0]

    res = client.patch(
        f"/api/v1/cases/{case_a}/checklist/{item_b['itemId']}",
        json={"checked": True},
        headers=auth_a,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_checklist_requires_token_and_check_does_not_bump_input_version(client):
    case_id, auth = _create_case(client)
    res = client.get(f"/api/v1/cases/{case_id}/checklist")
    assert res.status_code == 401

    item = client.get(f"/api/v1/cases/{case_id}/checklist", headers=auth).json()["items"][0]
    res = client.patch(
        f"/api/v1/cases/{case_id}/checklist/{item['itemId']}", json={"checked": "yes"}, headers=auth
    )
    assert res.status_code == 400
    client.patch(
        f"/api/v1/cases/{case_id}/checklist/{item['itemId']}", json={"checked": True}, headers=auth
    )
    case = client.get(f"/api/v1/cases/{case_id}", headers=auth).json()["case"]
    assert case["inputVersion"] == 1


def test_deleting_case_removes_checklist_rows(client, app):
    from app.models import ChecklistItemRow

    case_id, auth = _create_case(client)
    client.get(f"/api/v1/cases/{case_id}/checklist", headers=auth)
    assert client.delete(f"/api/v1/cases/{case_id}", headers=auth).status_code == 204
    with app.state.session_factory() as db:
        assert db.query(ChecklistItemRow).filter_by(case_id=case_id).count() == 0
