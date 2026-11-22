"""T14 개인정보 가리기(계약 테스트 아님, T14 계획 테스트 1~6)."""

import json
import time

import fake_claude
import pytest

from app.agent.extract.pdf_text import extract_pdf_text
from app.agent.masking import (
    MaskedText,
    collect_names,
    collect_narrative_names,
    mask_name,
    mask_regions,
    mask_text,
)
from app.config import Settings
from app.main import create_app
from app.models import AnalysisRun, Evidence
from app.services.samples import SAMPLE_DIR, SCENARIOS
from scripts.make_samples import (
    BUSINESS_FIELDS,
    GOODS_CHAT,
    GOODS_CHAT_TITLE,
    THREAT_CHAT,
    THREAT_TITLE,
    chat_lines,
)

API = "/api/v1"
MISSING = "proofy-no-such-tesseract"
# 합성 서류에 적힌 가상 원문 값. 가린 글에 하나도 남으면 안 된다
RAW_VALUES = (
    "정하늘",
    "박서진",
    "김민수",
    "한도윤",
    "이준호",
    "999-0000-1234-56",
    "999-0000-5678-90",
    "123-45-67890",
    "010-0000-4821",
)


# 1: 번호 규칙. 같은 줄의 날짜·시각·금액·잔액은 그대로
@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("주민번호 990101-1234567", "주민번호 ******-*******"),
        ("연락처 010-0000-4821", "연락처 010-****-4821"),
        ("연락처 01012345678", "연락처 010****5678"),
        ("사무실 02-123-4567", "사무실 02-***-4567"),
        ("등록번호 123-45-67890", "등록번호 ***-**-*****"),
        ("계좌번호 999-0000-1234-56", "계좌번호 ***-****-**34-56"),
        ("샘플은행 11012345678901 입금", "샘플은행 **********8901 입금"),
        (
            "2026-11-08 14:22 입금 150,000 300,500 체크카드 결제",
            "2026-11-08 14:22 입금 150,000 300,500 체크카드 결제",
        ),
        ("조회기간 2026-11-01 ~ 2026-11-14", "조회기간 2026-11-01 ~ 2026-11-14"),
    ],
)
def test_number_rules(raw, masked):
    assert mask_text(raw) == masked


def test_mask_name_shapes():
    assert mask_name("김민수") == "김*수"
    assert mask_name("이준") == "이*"
    assert mask_name("남궁민희") == "남**희"
    assert mask_name("김 민수") == "김*수"


# 2: 이름 모으기
def test_collect_names_from_labels_and_rows():
    lines = [
        "예금주 정하늘",
        "대표자                    정하늘",
        "성명: 한도윤",
        "2026-11-08 14:22 입금 150,000 300,500 김민수",
        "2026-11-10 19:05 출금 45,000 255,500 체크카드 결제",
        "은행 샘플은행(가상)",
        "상호 하늘가죽공방",
        "이름을 알려 주세요",
    ]
    assert collect_names(lines) == {"정하늘", "한도윤", "김민수"}


def test_collect_narrative_names():
    narrative = (
        "거래처 김민수 씨에게 물건을 보냈고, 아저씨가 받았습니다. 박서진씨도 압니다. 마음씨 좋은 분"
    )
    assert collect_narrative_names(narrative) == {"김민수", "박서진"}


# 3: 한 서류에서 모은 이름이 다른 서류 줄과 사연에서도(띄어쓰기 무시) 가려진다
def test_case_name_list_applies_everywhere():
    names = collect_names(["예금주 정하늘", "2026-11-08 14:22 입금 150,000 300,500 김민수"])
    assert mask_text("김민수 (거래처)", names) == "김*수 (거래처)"
    assert (
        mask_text("샘플은행 999-0000-1234-56 정하늘입니다", names)
        == "샘플은행 ***-****-**34-56 정*늘입니다"
    )
    assert mask_text("김 민수 사장님께 보냈습니다", names) == "김*수 사장님께 보냈습니다"
    assert isinstance(mask_text("글", names), MaskedText)


def _pdf_lines(key: str) -> list[str]:
    pages, _ = extract_pdf_text((SAMPLE_DIR / key / "transaction_record.pdf").read_bytes())
    return [r["text"] for p in pages for r in p["regions"]]


def _regions(lines: list[str]) -> list[dict]:
    return [{"index": i, "page": 1, "text": t} for i, t in enumerate(lines)]


# 4: 완료 조건. 샘플 서류(텍스트 PDF는 실제 추출, PNG는 생성 스크립트의 줄 — 이 PC엔 OCR이 없다)와
# 사연을 사건 단위로 가리면 가상 원문 값이 하나도 남지 않는다
@pytest.mark.parametrize(
    ("scenario", "documents"),
    [
        (
            "GOODS",
            [
                _pdf_lines("goods"),
                chat_lines(GOODS_CHAT_TITLE, GOODS_CHAT),
                [f"{k} {v}" for k, v in BUSINESS_FIELDS],
            ],
        ),
        ("UNEXPECTED", [_pdf_lines("unexpected"), chat_lines(THREAT_TITLE, THREAT_CHAT)]),
    ],
)
def test_sample_documents_leave_no_raw_values(scenario, documents):
    narrative = SCENARIOS[scenario].narrative
    names = collect_names(line for doc in documents for line in doc)
    names |= collect_narrative_names(narrative)
    sent = [mask_regions(_regions(doc), names)[1] for doc in documents]
    sent.append(mask_text(narrative, names))
    joined = "\n".join(sent)
    leaked = [v for v in RAW_VALUES if v in joined]
    assert leaked == []
    # 대조에 쓰는 금액·날짜는 남는다
    assert "2026-11-" in joined and ("150,000" in joined or "100,000" in joined)


# 5·6: 분석 실행과 연결
def _client(tmp_path, agent: str):
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm=agent,
        scripted_stage_delay_seconds=0,
        tesseract_cmd=MISSING,
        pdftoppm_cmd=MISSING,
    )
    return TestClient(create_app(settings), raise_server_exceptions=False)


def _run(client, case_id: str, auth: dict[str, str], **body) -> dict:
    res = client.post(f"{API}/cases/{case_id}/analysis-runs", json=body, headers=auth)
    assert res.status_code == 202, res.text
    run_id = res.json()["runId"]
    end = time.monotonic() + 20
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def test_claude_mode_saves_masked_text(tmp_path, monkeypatch):
    # ② 대조는 가짜 Claude가 서류 줄을 한 번 조회하고 빈 결과를 낸다(T16)
    sdk = fake_claude.install(monkeypatch, [_read_record_then_answer])
    with _client(tmp_path, "claude") as client:
        body = client.post(f"{API}/cases/sample", json={"scenario": "GOODS"}).json()
        case_id, auth = body["caseId"], {"X-Case-Token": body["caseToken"]}
        narrative = SCENARIOS["GOODS"].narrative + " 거래처 김민수 씨 번호는 010-1234-5678입니다."
        run = _run(client, case_id, auth, narrative=narrative)
        assert run["status"] == "SUCCEEDED"

        with client.app.state.session_factory() as db:
            record = (
                db.query(Evidence).filter_by(case_id=case_id, doc_type="TRANSACTION_RECORD").one()
            )
            assert record.masked_text is not None
            assert all("maskedText" in r for r in record.regions_json)
            for value in ("정하늘", "박서진", "김민수", "999-0000-1234-56"):
                assert value not in record.masked_text
            assert "김*수" in record.masked_text and "150,000" in record.masked_text
            # 원문 `text`는 서버 안 금액·날짜 확인용으로 남는다(ERD 3.3)
            assert any("김민수" in r["text"] for r in record.regions_json)

            saved = db.get(AnalysisRun, run["runId"]).masked_narrative
            assert "김*수 씨" in saved and "010-****-5678" in saved
            assert "김민수" not in saved and "010-1234-5678" not in saved

    # 외부 AI에 보낸 글(첫 메시지·도구 결과)에도 원래 이름·번호가 없다(원칙 4)
    sent = repr([r["messages"] for r in sdk.requests])
    assert "김*수" in sent and "150,000" in sent
    for value in ("정하늘", "박서진", "김민수", "010-1234-5678", "999-0000-1234-56"):
        assert value not in sent


def _read_record_then_answer(requests):
    first = requests[0]["messages"][0]["content"][0]["text"]
    record = next(d for d in json.loads(first)["documents"] if d["docType"] == "TRANSACTION_RECORD")
    args = {"reason": "거래내역서를 보려고", "evidenceId": record["evidenceId"], "page": None}
    return fake_claude.tool_use(("u1", "get_evidence_regions", args))


def test_scripted_mode_masks_narrative_and_keeps_results(client):
    body = client.post(f"{API}/cases/sample", json={"scenario": "UNEXPECTED"}).json()
    case_id, auth = body["caseId"], {"X-Case-Token": body["caseToken"]}
    narrative = SCENARIOS["UNEXPECTED"].narrative + " 제 번호는 010-1234-5678입니다."
    run = _run(client, case_id, auth, narrative=narrative)
    assert run["status"] == "SUCCEEDED"

    with client.app.state.session_factory() as db:
        saved = db.get(AnalysisRun, run["runId"]).masked_narrative
    assert "010-****-5678" in saved and "010-1234-5678" not in saved

    result = client.get(f"{API}/cases/{case_id}/result", headers=auth).json()
    narrative_sources = [
        s for f in result["findings"] for s in f["sources"] if s["kind"] == "NARRATIVE"
    ]
    assert narrative_sources and all(s["verified"] for s in narrative_sources)
