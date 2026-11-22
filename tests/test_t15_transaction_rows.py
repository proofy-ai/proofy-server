"""T15 거래 행 추출(계약 테스트 아님, T15 계획 테스트 1~5. 6은 기존 T08 테스트)."""

import time
from datetime import date

import fake_claude
import pytest

from app.agent.extract.pdf_text import extract_pdf_text
from app.agent.masking import collect_names, mask_regions
from app.agent.transactions import parse_rows, row_matches_source
from app.config import Settings
from app.main import create_app
from app.models import Transaction
from app.services.samples import SAMPLE_DIR

API = "/api/v1"
MISSING = "proofy-no-such-tesseract"


def _sample_regions(key: str) -> list[dict]:
    pages, _ = extract_pdf_text((SAMPLE_DIR / key / "transaction_record.pdf").read_bytes())
    regions = [r for p in pages for r in p["regions"]]
    masked, _ = mask_regions(regions, collect_names(r["text"] for r in regions))
    return masked


def _regions(*lines: str) -> list[dict]:
    regions = [{"index": i, "page": 1, "text": t} for i, t in enumerate(lines)]
    masked, _ = mask_regions(regions, collect_names(lines))
    return masked


def _summary(rows) -> list[tuple]:
    return [
        (r.key, r.region_index, r.occurred_at, r.direction, r.amount_krw, r.counterparty_masked)
        for r in rows
    ]


# 1: 완료 조건. T12 거래내역서에서 문제된 입금 행이 나온다
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (
            "goods",
            [
                ("t1", 7, date(2026, 11, 3), "IN", 32_000, "박*진"),
                ("t2", 8, date(2026, 11, 8), "IN", 150_000, "김*수"),
                ("t3", 9, date(2026, 11, 10), "OUT", 45_000, "체크카드 결제"),
            ],
        ),
        (
            "unexpected",
            [
                ("t1", 7, date(2026, 11, 9), "OUT", 23_000, "체크카드 결제"),
                ("t2", 8, date(2026, 11, 12), "IN", 100_000, "이*호"),
            ],
        ),
    ],
)
def test_sample_statement_rows(key, expected):
    assert _summary(parse_rows(_sample_regions(key), "e1")) == expected


# 2: 다른 모양(점 날짜, 시각 없음, 잔액 없음, 초까지 있는 시각)
def test_other_row_shapes():
    rows = parse_rows(
        _regions(
            "2026.11.08 입금 150,000 김민수",
            "2026/11/09 09:01:30 출금 5000 1,000 편의점",
            "2026-11-10 입금 7,000",
        ),
        "e1",
        start_key=4,
    )
    assert _summary(rows) == [
        ("t4", 0, date(2026, 11, 8), "IN", 150_000, "김*수"),
        # 2~4글자 거래상대는 상호여도 이름으로 보고 가린다(T14 남은 위험 ②, 더 가리는 쪽)
        ("t5", 1, date(2026, 11, 9), "OUT", 5_000, "편*점"),
        ("t6", 2, date(2026, 11, 10), "IN", 7_000, None),
    ]


# 3: 행이 아닌 줄은 행이 되지 않는다
def test_non_rows_are_skipped():
    rows = parse_rows(
        _regions(
            "거래일시 구분 거래금액 거래후잔액 거래상대·적요",
            "조회기간 2026-11-01 ~ 2026-11-14",
            "조회기간 내 거래 3건",
            "내일 입금할게요. 계좌 알려 주세요",
            "2026-11-08 입금 0 100 김민수",
            "2026-13-40 입금 1,000 100 김민수",
        ),
        "e1",
    )
    assert rows == []


# 4: 원문은 raw_text에만, 거래상대는 가린 값
def test_raw_text_and_masked_counterparty():
    (row,) = parse_rows(_regions("2026-11-08 14:22 입금 150,000 300,500 김민수"), "e1")
    assert row.raw_text == "2026-11-08 14:22 입금 150,000 300,500 김민수"
    assert row.counterparty_masked == "김*수"
    assert row_matches_source(row, row.raw_text)
    assert not row_matches_source(row, "2026-11-08 14:22 입금 120,000 김민수")


# 5: AGENT_LLM=claude 분석에서 실제로 뽑은 행이 저장되고 탭 A 근거가 된다
# (② 대조는 가짜 Claude: 입금을 조회하고 돌려받은 t2를 근거로 댄다, T16)
def _run(client, case_id: str, auth: dict[str, str]) -> dict:
    res = client.post(f"{API}/cases/{case_id}/analysis-runs", json={}, headers=auth)
    assert res.status_code == 202, res.text
    run_id = res.json()["runId"]
    end = time.monotonic() + 20
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def test_claude_mode_saves_parsed_rows(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    query = {
        "reason": "사연의 11월 8일 대금 입금을 확인하려고",
        "from": "2026-11-01",
        "to": "2026-11-10",
        "direction": "IN",
        "counterparty": None,
        "minAmount": 150000,
        "maxAmount": 150000,
    }
    answer = {
        "findings": [
            {
                "claim": "11월 8일 15만 원을 입금받았습니다",
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
            }
        ],
        "recommendedDocs": [],
    }
    fake_claude.install(
        monkeypatch,
        [fake_claude.tool_use(("u1", "get_transactions", query)), fake_claude.text(answer)],
    )

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm="claude",
        scripted_stage_delay_seconds=0,
        tesseract_cmd=MISSING,
        pdftoppm_cmd=MISSING,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        body = client.post(f"{API}/cases/sample", json={"scenario": "GOODS"}).json()
        case_id, auth = body["caseId"], {"X-Case-Token": body["caseToken"]}
        run = _run(client, case_id, auth)
        assert run["status"] == "SUCCEEDED"
        step = next(s for s in run["steps"] if "거래내역 행 정리" in s["title"])
        assert step["type"] == "OCR" and "거래 3건(입금 2, 출금 1)" in step["summary"]

        with client.app.state.session_factory() as db:
            saved = (
                db.query(Transaction)
                .filter_by(analysis_run_id=run["runId"])
                .order_by(Transaction.region_index)
                .all()
            )
            assert [(t.region_index, t.amount_krw, t.counterparty_masked) for t in saved] == [
                (7, 32_000, "박*진"),
                (8, 150_000, "김*수"),
                (9, 45_000, "체크카드 결제"),
            ]

        result = client.get(f"{API}/cases/{case_id}/result", headers=auth).json()
        tx_sources = [
            s for f in result["findings"] for s in f["sources"] if s["kind"] == "TRANSACTION"
        ]
        assert {
            (s["occurredAt"], s["direction"], s["amountKrw"], s["counterparty"]) for s in tx_sources
        } == {("2026-11-08", "IN", 150_000, "김*수")}
