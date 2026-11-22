"""T13 글자 추출(계약 테스트 아님, T13 계획 테스트 a~e)."""

import io
import shutil
import time

import fake_claude
import pytest
from PIL import Image

from app.agent.extract import extract_document
from app.agent.extract.ocr import TesseractEngine, count_low_confidence, parse_tsv
from app.agent.scripted import (
    GOODS_CHAT_QUOTE,
    GOODS_CHAT_REGION,
    THREAT_QUOTE,
    THREAT_REGION,
)
from app.config import Settings
from app.main import create_app
from app.services.samples import SAMPLE_DIR

API = "/api/v1"
# 테스트 PC에 Tesseract가 있어도 없는 것처럼 만들 때 쓰는 경로
MISSING = "proofy-no-such-tesseract"
NO_OCR = TesseractEngine(tesseract_cmd=MISSING, pdftoppm_cmd=MISSING)
HAS_TESSERACT = shutil.which("tesseract") is not None


def _sample_bytes(key: str, name: str) -> bytes:
    return (SAMPLE_DIR / key / name).read_bytes()


# a: T12 거래내역서는 OCR 없이 읽히고, 거래 한 행이 한 영역
@pytest.mark.parametrize(
    ("key", "row"),
    [
        ("goods", ["2026-11-08", "입금", "150,000", "김민수"]),
        ("unexpected", ["2026-11-12", "입금", "100,000", "이준호"]),
    ],
)
def test_text_pdf_is_read_without_ocr(key, row):
    result = extract_document(_sample_bytes(key, "transaction_record.pdf"), NO_OCR)
    assert result.status == "READY"
    assert result.method == "PDF_TEXT"
    assert result.low_confidence == 0
    assert [r["index"] for r in result.regions] == list(range(len(result.regions)))
    assert all(r["page"] == 1 and r["bbox"] is None for r in result.regions)
    assert any(all(part in r["text"] for part in row) for r in result.regions)
    assert "합성 데이터" in result.text


# b: 글자 없는 PDF는 OCR로 넘어가고, OCR이 없으면 FAILED(예외 없음). 모르는 형식도 FAILED
def test_image_only_pdf_goes_to_ocr_and_fails_softly():
    buffer = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buffer, "PDF")
    result = extract_document(buffer.getvalue(), NO_OCR)
    assert result.status == "FAILED"
    assert result.method is None
    assert "pdftoppm" in (result.error or "")

    png = extract_document(_sample_bytes("goods", "chat.png"), NO_OCR)
    assert png.status == "FAILED"
    assert "tesseract" in (png.error or "")

    unknown = extract_document(b"GIF89a....", NO_OCR)
    assert unknown.status == "FAILED"


# c: Tesseract TSV를 줄 단위로 묶고, txt의 띄어쓰기를 쓰고, 신뢰도를 평균한다
def test_parse_tsv_groups_words_into_lines():
    header = "\t".join(
        "level page_num block_num par_num line_num word_num left top width height conf text".split()
    )
    rows = [
        "1\t1\t0\t0\t0\t0\t0\t0\t720\t1280\t-1\t",
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t20\t96\t3개",
        "5\t1\t1\t1\t1\t2\t45\t20\t60\t20\t90\t12만원에",
        "5\t1\t1\t1\t1\t3\t110\t20\t60\t20\t84\t할게요",
        "5\t1\t1\t1\t2\t1\t10\t60\t40\t20\t50\t흐린줄",
    ]
    text = "3개 12만원에 할게요\n흐린줄\n"
    page = parse_tsv("\n".join([header, *rows]), 2, start_index=5, text=text)
    assert (page["width"], page["height"]) == (720, 1280)
    first, second = page["regions"]
    assert first == {
        "index": 5,
        "page": 2,
        "text": "3개 12만원에 할게요",
        "bbox": [10, 20, 160, 20],
        "confidence": 0.9,
    }
    assert second["index"] == 6 and second["confidence"] == 0.5
    assert count_low_confidence([page]) == 1


# d: AGENT_LLM=claude면 분석 ① 단계가 실제로 읽어 저장하고, 다시 분석하면 읽은 것을 다시 쓴다
@pytest.fixture
def claude_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    # ② 대조는 가짜 Claude가 빈 결과를 낸다(T16). 여기서는 ① 추출만 본다
    fake_claude.install(monkeypatch, [])

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm="claude",
        scripted_stage_delay_seconds=0,
        tesseract_cmd=MISSING,
        pdftoppm_cmd=MISSING,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


def _run_analysis(client, case_id: str, auth: dict[str, str], **body) -> dict:
    res = client.post(f"{API}/cases/{case_id}/analysis-runs", json=body, headers=auth)
    assert res.status_code == 202, res.text
    run_id = res.json()["runId"]
    end = time.monotonic() + 10
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def test_claude_mode_extracts_and_saves(claude_client):
    client = claude_client
    body = client.post(f"{API}/cases/sample", json={"scenario": "GOODS"}).json()
    case_id, auth = body["caseId"], {"X-Case-Token": body["caseToken"]}

    run = _run_analysis(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    # 서류 읽기 step만 센다(거래 행 정리 step도 `OCR` 종류다, T15)
    ocr_steps = [s for s in run["steps"] if s["type"] == "OCR" and s["title"].endswith(" 읽기")]
    # 실제 추출 step만 있고 가짜 분석기의 흉내 step은 없다
    assert len(ocr_steps) == 3
    assert ocr_steps[0]["status"] == "DONE" and "OCR 없이" in ocr_steps[0]["summary"]
    assert all(s["status"] == "FAILED" for s in ocr_steps[1:])

    items = client.get(f"{API}/cases/{case_id}/evidence", headers=auth).json()["items"]
    status = {i["docType"]: (i["extractStatus"], i["lowConfidenceRegions"]) for i in items}
    assert status["TRANSACTION_RECORD"] == ("READY", 0)
    assert status["CHAT"] == ("FAILED", None)
    assert status["BUSINESS_REG"] == ("FAILED", None)

    result = client.get(f"{API}/cases/{case_id}/result", headers=auth).json()
    unread = {u["originalName"] for u in result["unreadEvidence"]}
    assert unread == {"대화내역_샘플.png", "사업자등록증명_샘플.png"}

    again = _run_analysis(client, case_id, auth)
    first = next(s for s in again["steps"] if s["type"] == "OCR")
    assert "전에 읽은 글자" in first["summary"]


def test_scripted_mode_does_not_extract(client):
    body = client.post(f"{API}/cases/sample", json={"scenario": "UNEXPECTED"}).json()
    case_id, auth = body["caseId"], {"X-Case-Token": body["caseToken"]}
    run = _run_analysis(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    items = client.get(f"{API}/cases/{case_id}/evidence", headers=auth).json()["items"]
    assert all(i["extractStatus"] == "UPLOADED" for i in items)


# e: Tesseract가 있는 곳(Docker 등)에서만.
# 대화·협박 PNG의 인용 문구가 가짜 분석기와 같은 줄에 나온다
@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract가 없음")
@pytest.mark.parametrize(
    ("key", "name", "quote", "region"),
    [
        ("goods", "chat.png", GOODS_CHAT_QUOTE, GOODS_CHAT_REGION),
        ("unexpected", "threat_message.png", THREAT_QUOTE, THREAT_REGION),
    ],
)
def test_ocr_reads_sample_png_quotes(key, name, quote, region):
    result = extract_document(_sample_bytes(key, name), TesseractEngine())
    assert result.status == "READY" and result.method == "OCR"
    compact = "".join(quote.split())
    assert "".join(result.regions[region]["text"].split()) == compact
