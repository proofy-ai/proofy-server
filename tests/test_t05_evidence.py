"""T05 증빙 업로드. 계약 관련 테스트 T05-a~c(11/21 승인)."""

from app.models import Evidence, EvidenceFile
from app.services.evidence import MAX_FILE_BYTES

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

EVIDENCE_KEYS = {
    "evidenceId", "docType", "originalName", "mimeType", "sizeBytes", "extractStatus",
    "lowConfidenceRegions", "isSample", "createdAt",
}  # fmt: skip


def _create_case(client) -> tuple[str, dict[str, str]]:
    body = {
        "noticeReceivedDate": "2026-11-10",
        "publicNoticeDate": "2026-11-17",
        "inflow": {"type": "GOODS", "amountKrw": 150000, "occurredAt": None},
        "hasPriorFreeze": False,
    }
    res = client.post("/api/v1/cases", json=body)
    assert res.status_code == 201, res.text
    return res.json()["caseId"], {"X-Case-Token": res.json()["caseToken"]}


def _upload(client, case_id, auth, data=PNG, name="chat.jpg", doc_type="CHAT", ctype="image/jpeg"):
    return client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": (name, data, ctype)},
        data={"docType": doc_type},
        headers=auth,
    )


def _case(client, case_id, auth) -> dict:
    return client.get(f"/api/v1/cases/{case_id}", headers=auth).json()["case"]


def _error_code(res) -> str:
    return res.json()["error"]["code"]


# T05-a: 업로드 응답 모양, 형식은 파일 내용 기준, inputVersion·evidenceCount·체크리스트 반영
def test_upload_png(client):
    case_id, auth = _create_case(client)

    res = _upload(client, case_id, auth, data=PNG, name="chat.jpg", ctype="image/jpeg")
    assert res.status_code == 201, res.text
    assert set(res.json()) == {"evidence"}
    evidence = res.json()["evidence"]
    assert set(evidence) == EVIDENCE_KEYS
    assert evidence["mimeType"] == "image/png"  # 이름·Content-Type이 아니라 내용으로 판별
    assert evidence["docType"] == "CHAT"
    assert evidence["originalName"] == "chat.jpg"
    assert evidence["sizeBytes"] == len(PNG)
    assert evidence["extractStatus"] == "UPLOADED"
    assert evidence["lowConfidenceRegions"] is None
    assert evidence["isSample"] is False
    assert evidence["createdAt"].endswith("Z")

    case = _case(client, case_id, auth)
    assert case["inputVersion"] == 2
    assert case["evidenceCount"] == 1

    items = client.get(f"/api/v1/cases/{case_id}/checklist", headers=auth).json()["items"]
    chat = next(i for i in items if i["code"] == "COUNTERPARTY_CHAT")
    assert chat["status"] == "SATISFIED"
    assert chat["satisfiedBy"] == [evidence["evidenceId"]]


# T05-b: 413·415·409, 실패한 요청은 inputVersion을 바꾸지 않는다
def test_upload_limits(client):
    case_id, auth = _create_case(client)

    too_big = b"%PDF-" + b"0" * (MAX_FILE_BYTES - 4)
    assert len(too_big) == MAX_FILE_BYTES + 1
    res = _upload(client, case_id, auth, data=too_big, name="big.pdf", ctype="application/pdf")
    assert res.status_code == 413
    assert _error_code(res) == "FILE_TOO_LARGE"

    res = _upload(client, case_id, auth, data=b"hello", name="fake.pdf", ctype="application/pdf")
    assert res.status_code == 415
    assert _error_code(res) == "UNSUPPORTED_FILE_TYPE"
    assert _case(client, case_id, auth)["inputVersion"] == 1

    for i in range(8):
        data = (PNG, PDF, JPEG)[i % 3]
        assert _upload(client, case_id, auth, data=data, name=f"f{i}").status_code == 201
    assert _case(client, case_id, auth)["inputVersion"] == 9

    res = _upload(client, case_id, auth, data=PNG, name="ninth.png")
    assert res.status_code == 409
    assert _error_code(res) == "EVIDENCE_LIMIT"
    case = _case(client, case_id, auth)
    assert case["inputVersion"] == 9
    assert case["evidenceCount"] == 8


# T05-c: 지우기 204, 목록·inputVersion 반영, 다른 사건 404, 사건 삭제 시 파일까지 삭제
def test_delete_evidence(client, app):
    case_a, auth_a = _create_case(client)
    case_b, auth_b = _create_case(client)
    first = _upload(client, case_a, auth_a, name="first.png").json()["evidence"]["evidenceId"]
    second = _upload(client, case_a, auth_a, data=PDF, name="second.pdf").json()["evidence"]
    other = _upload(client, case_b, auth_b).json()["evidence"]["evidenceId"]

    items = client.get(f"/api/v1/cases/{case_a}/evidence", headers=auth_a).json()["items"]
    assert [i["evidenceId"] for i in items] == [first, second["evidenceId"]]  # 올린 순서

    res = client.delete(f"/api/v1/cases/{case_a}/evidence/{first}", headers=auth_a)
    assert res.status_code == 204
    items = client.get(f"/api/v1/cases/{case_a}/evidence", headers=auth_a).json()["items"]
    assert [i["evidenceId"] for i in items] == [second["evidenceId"]]
    assert _case(client, case_a, auth_a)["inputVersion"] == 4  # 올리기 2번 + 지우기 1번

    res = client.delete(f"/api/v1/cases/{case_a}/evidence/{other}", headers=auth_a)
    assert res.status_code == 404
    assert _error_code(res) == "NOT_FOUND"

    assert client.delete(f"/api/v1/cases/{case_a}", headers=auth_a).status_code == 204
    with app.state.session_factory() as db:
        assert db.query(Evidence).filter_by(case_id=case_a).count() == 0
        assert db.get(EvidenceFile, second["evidenceId"]) is None
        # 다른 사건의 서류는 남는다
        assert db.get(EvidenceFile, other) is not None


# 아래는 계약 테스트가 아닌 동작 확인


def test_upload_validation_and_auth(client):
    case_id, auth = _create_case(client)

    res = _upload(client, case_id, auth, doc_type="ID_CARD")
    assert res.status_code == 400
    assert _error_code(res) == "VALIDATION_ERROR"

    res = _upload(client, case_id, {})
    assert res.status_code == 401
    assert _error_code(res) == "CASE_TOKEN_INVALID"


def test_file_is_stored_in_db_with_clean_name(client, app):
    case_id, auth = _create_case(client)
    res = _upload(client, case_id, auth, data=PDF, name="C:\\Users\\me\\거래내역서.pdf")
    evidence = res.json()["evidence"]
    assert evidence["originalName"] == "거래내역서.pdf"
    with app.state.session_factory() as db:
        assert db.get(EvidenceFile, evidence["evidenceId"]).content == PDF
