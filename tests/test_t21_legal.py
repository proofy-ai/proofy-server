"""T21 법령 안내(계약 4.2.1). 계약 테스트 아님(작업 파일의 T21-a·b)."""

import re
from pathlib import Path

import pytest

from app.services.legal import GUIDES, SNAPSHOT_FILES

LEGAL_DIR = Path(__file__).resolve().parents[1] / "app" / "agent" / "law_data"


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


@pytest.mark.parametrize("guide", GUIDES, ids=lambda g: g.code)
def test_quote_is_verbatim_from_snapshot(guide):
    """T21-a: quote의 조각마다 원문 스냅샷에 공백만 빼고 그대로 있다."""
    snapshot = _squash((LEGAL_DIR / SNAPSHOT_FILES[guide.doc]).read_text(encoding="utf-8"))
    for part in guide.quote_parts:
        assert _squash(part) in snapshot, f"{guide.code}: 원문에 없는 인용 {part!r}"


EXPECTED_COMMON = {
    "SALARY": {"REASON_2"},
    "GOODS": {"REASON_2"},
    "UNEXPECTED": {"REASON_3"},
    "OTHER": set(),
}


@pytest.mark.parametrize("inflow_type", list(EXPECTED_COMMON))
def test_items_by_inflow_type(client, inflow_type):
    """T21-b: 사유 세 가지는 모든 유형에, 보통 쓰는 사유 표시와 협박 안내는 유형별로."""
    res = client.get("/api/v1/legal-guides", params={"inflowType": inflow_type})
    assert res.status_code == 200
    body = res.json()
    assert body["inflowType"] == inflow_type
    assert body["disclaimer"]
    items = body["items"]
    codes = [i["code"] for i in items]

    assert {"REASON_1", "REASON_2", "REASON_3"} <= set(codes)
    assert {i["code"] for i in items if i["commonForType"]} == EXPECTED_COMMON[inflow_type]
    assert ("DONT_PAY_THREAT" in codes) == (inflow_type == "UNEXPECTED")

    # 2A 항목이 먼저, 6번 제출 항목이 뒤에 온다
    stages = [i["stage"] for i in items]
    assert stages == sorted(stages, key=["SITUATION", "SUBMIT"].index)
    assert set(stages) == {"SITUATION", "SUBMIT"}

    for item in items:
        assert item["sourceRef"]["url"].startswith("https://www.law.go.kr/")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["effectiveDate"])


@pytest.mark.parametrize("params", [{"inflowType": "WRONG"}, {}])
def test_invalid_inflow_type_is_400(client, params):
    res = client.get("/api/v1/legal-guides", params=params)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
