"""T17 초안 작성 + 후검증. 실제 Claude는 부르지 않고 가짜 SDK(`fake_claude`)로 돌린다.

계약 테스트(README 승인 목록): T17-a 인용 검증, T17-b 초안 근거 교차 차단, T17-c 1회 고쳐 쓰기.
"""

import json
import time
from datetime import date

import fake_claude
import pytest

from app.agent.drafting import Drafter, check_sentence
from app.agent.llm import ClaudeClient, Deadline
from app.agent.masking import mask_text
from app.agent.output import AnalysisOutput, DraftSentence, Finding, Source, TransactionRow
from app.agent.runner import RunContext
from app.config import Settings
from app.main import create_app

API = "/api/v1"
MISSING = "proofy-no-such-tesseract"

TX_QUERY = {
    "reason": "사연의 11월 8일 대금 입금을 확인하려고",
    "from": "2026-11-01",
    "to": "2026-11-10",
    "direction": "IN",
    "counterparty": None,
    "minAmount": None,
    "maxAmount": None,
}
# 샘플 사연(test01)에 실제로 있는 문장
NARRATIVE_QUOTE = "11월 8일 대금을 계좌로 받았습니다"


def _compare_answer(narrative_quote: str = NARRATIVE_QUOTE) -> dict:
    """대조 단계 답: 0번 = 15만 원 입금 일치(사연 인용 + 거래 t2)."""
    return {
        "findings": [
            {
                "claim": "11월 8일 대금 15만 원을 받았습니다",
                "status": "MATCH",
                "note": "거래내역서의 입금 행과 같습니다.",
                "conflict": None,
                "sources": [
                    {
                        "kind": "NARRATIVE",
                        "quote": narrative_quote,
                        "evidenceId": None,
                        "regionIndex": None,
                        "transactionId": None,
                    },
                    {
                        "kind": "TRANSACTION",
                        "quote": None,
                        "evidenceId": None,
                        "regionIndex": None,
                        "transactionId": "t2",
                    },
                ],
            }
        ],
        "recommendedDocs": [],
    }


def _draft(*sentences: tuple[str, str, list[int]]) -> dict:
    return {
        "sentences": [
            {"section": section, "text": text, "findingIndexes": indexes}
            for section, text, indexes in sentences
        ]
    }


def _rewrite(index: int, text: str) -> dict:
    return {"sentences": [{"index": index, "text": text}]}


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

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


def _analyze(client, monkeypatch, compare_answer: dict, *draft_responses):
    sdk = fake_claude.install(
        monkeypatch,
        [
            fake_claude.tool_use(("u1", "get_transactions", TX_QUERY)),
            fake_claude.text(compare_answer),
            *[fake_claude.text(r) for r in draft_responses],
        ],
    )
    body = client.post(f"{API}/cases/sample", json={"scenario": "GOODS"}).json()
    case_id, auth = body["caseId"], {"X-Case-Token": body["caseToken"]}
    res = client.post(f"{API}/cases/{case_id}/analysis-runs", json={}, headers=auth)
    assert res.status_code == 202, res.text
    run_id = res.json()["runId"]
    end = time.monotonic() + 60
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            break
        time.sleep(0.02)
    assert run["status"] == "SUCCEEDED", run
    draft = client.get(f"{API}/cases/{case_id}/draft", headers=auth).json()["draft"]
    return run, draft, sdk


# T17-a 인용 검증: 사연에 없는 인용을 근거로 단 항목에 연결된 문장은 확인 필요(QUOTE_NOT_FOUND)
def test_t17a_sentence_on_unverified_quote_needs_check(client, monkeypatch):
    sentence = "본인은 2026년 11월 8일 거래처로부터 대금 150,000원을 받았습니다."
    run, draft, _ = _analyze(
        client,
        monkeypatch,
        _compare_answer("사연에 없는 문장입니다"),
        _draft(("DEPOSIT_REASON", sentence, [0])),
    )
    [s] = draft["sentences"]
    assert s["text"] == sentence
    assert s["needsCheck"] is True and s["needsCheckReason"] == "QUOTE_NOT_FOUND"
    assert len(s["findingIds"]) == 1


def test_sentence_on_verified_sources_passes(client, monkeypatch):
    sentence = "본인은 2026년 11월 8일 거래처로부터 대금 150,000원을 받았습니다."
    run, draft, _ = _analyze(
        client, monkeypatch, _compare_answer(), _draft(("DEPOSIT_REASON", sentence, [0]))
    )
    [s] = draft["sentences"]
    assert s["needsCheck"] is False and s["needsCheckReason"] is None
    assert not [x for x in run["steps"] if x["type"] == "VERIFY"]


# T17-b 근거 교차 차단(초안): 없는 항목 번호를 단 문장은 그 연결이 빠지고 NO_SOURCE
def test_t17b_unknown_finding_index_is_dropped(client, monkeypatch):
    run, draft, _ = _analyze(
        client,
        monkeypatch,
        _compare_answer(),
        _draft(("DEPOSIT_REASON", "거래처에 물건을 납품했습니다.", [99])),
    )
    [s] = draft["sentences"]
    assert s["findingIds"] == []
    assert s["needsCheck"] is True and s["needsCheckReason"] == "NO_SOURCE"


# T17-c 1회 고쳐 쓰기: 고친 문장이 통과하면 고친 문장, 또 걸리면 원래 문장 + 사유
@pytest.mark.parametrize(
    ("original", "rewritten", "final_text", "reason"),
    [
        (
            "본인은 11월 8일 대금 200,000원을 받았습니다.",
            "본인은 11월 8일 대금 150,000원을 받았습니다.",
            "본인은 11월 8일 대금 150,000원을 받았습니다.",
            None,
        ),
        (
            "본인은 11월 8일 대금 200,000원을 받았습니다.",
            "본인은 11월 9일 대금 150,000원을 받았습니다.",
            "본인은 11월 8일 대금 200,000원을 받았습니다.",
            "NUMBER_MISMATCH",
        ),
        (
            "본인은 11월 8일 대금 150,000원을 받았으므로 확실히 해제될 것입니다.",
            "본인은 11월 8일 대금 150,000원을 받았습니다.",
            "본인은 11월 8일 대금 150,000원을 받았습니다.",
            None,
        ),
        (
            "본인은 11월 8일 대금 150,000원을 받았으므로 확실히 해제될 것입니다.",
            "정상 거래라 지급정지가 풀릴 것입니다.",
            "본인은 11월 8일 대금 150,000원을 받았으므로 확실히 해제될 것입니다.",
            "JUDGMENT_EXPRESSION",
        ),
    ],
)
def test_t17c_rewrite_once(client, monkeypatch, original, rewritten, final_text, reason):
    other = "본인은 이 돈이 범죄와 관련된 돈이라는 사실을 알지 못했습니다."
    run, draft, sdk = _analyze(
        client,
        monkeypatch,
        _compare_answer(),
        _draft(("DEPOSIT_REASON", original, [0]), ("NO_INVOLVEMENT", other, [])),
        _rewrite(0, rewritten),
    )
    first, second = draft["sentences"]
    assert first["text"] == final_text
    assert first["needsCheck"] is (reason is not None)
    assert first["needsCheckReason"] == reason
    # 걸리지 않은 문장은 고쳐 쓰기에 보내지 않는다
    rewrite_request = json.loads(sdk.requests[-1]["messages"][-1]["content"][0]["text"])
    assert [r["index"] for r in rewrite_request["rewrite"]] == [0]
    assert second["text"] == other and second["needsCheckReason"] == "NO_SOURCE"
    [verify] = [x for x in run["steps"] if x["type"] == "VERIFY"]
    assert ("고쳐 다시 확인" in verify["summary"]) is (reason is None)


def test_draft_request_uses_enum_indexes_and_masked_text(client, monkeypatch):
    _, _, sdk = _analyze(
        client,
        monkeypatch,
        _compare_answer(),
        _draft(("DEPOSIT_REASON", "본인은 11월 8일 대금을 받았습니다.", [0])),
    )
    draft_request = sdk.requests[2]
    items = draft_request["output_config"]["format"]["schema"]["properties"]["sentences"]["items"]
    assert items["properties"]["findingIndexes"]["items"]["enum"] == [0]
    assert draft_request["tools"] == []
    sent = draft_request["messages"][0]["content"][0]["text"]
    for raw in ("정하늘", "김민수", "박서진"):
        assert raw not in sent


# 단위: 숫자·판정 표현 검사, 마감이 가까우면 고쳐 쓰지 않음


def _ctx(deadline: float) -> RunContext:
    return RunContext(
        case_id="c",
        run_id="r",
        agent="claude",
        inflow_type="GOODS",
        reported_amount_krw=150_000,
        narrative="",
        sample_scenario=None,
        evidence=(),
        deadline=deadline,
        reported_occurred_at=date(2026, 11, 8),
    )


def _out() -> AnalysisOutput:
    out = AnalysisOutput(masked_narrative=mask_text(""))
    out.transactions.append(
        TransactionRow("t1", "e1", 0, "IN", 150_000, date(2026, 11, 8), None, "")
    )
    out.findings.append(
        Finding(
            "대금을 받았습니다",
            "MATCH",
            "같습니다.",
            sources=(Source("TRANSACTION", transaction_key="t1"), Source("NARRATIVE", "12만원")),
        )
    )
    return out


@pytest.mark.parametrize(
    ("text", "indexes", "reason"),
    [
        ("11월 8일 15만 원을 받았습니다.", (0,), None),
        ("11월 8일 12만원으로 합의했습니다.", (0,), None),
        ("11월 9일 150,000원을 받았습니다.", (0,), "NUMBER_MISMATCH"),
        ("30만 원을 받았습니다.", (0,), "NUMBER_MISMATCH"),
        # 근거 항목이 없는 본인 진술은 숫자를 대조하지 않는다(서버가 NO_SOURCE로 표시)
        ("30만 원을 받았습니다.", (), None),
        ("지급정지가 해제될 것으로 보입니다.", (), "JUDGMENT_EXPRESSION"),
        ("이의제기가 받아들여질 가능성이 높습니다.", (0,), "JUDGMENT_EXPRESSION"),
        ("카드 결제 승인 내역이 있습니다.", (0,), None),
    ],
)
def test_check_sentence(text, indexes, reason):
    out = _out()
    sentence = DraftSentence("DEPOSIT_REASON", text, indexes)
    ctx = _ctx(time.monotonic() + 100)
    assert check_sentence(sentence, out.findings, out, ctx) == reason


def test_no_rewrite_when_deadline_is_near():
    sdk = fake_claude.FakeSdk(
        [fake_claude.text(_draft(("DEPOSIT_REASON", "30만 원을 받았습니다.", [0])))]
    )
    deadline = time.monotonic() + 30  # 고쳐 쓰기 기준 40초보다 적게 남음
    claude = ClaudeClient(None, "claude-opus-5-5", "low", Deadline(deadline), client=sdk)
    out = _out()
    steps: list[tuple] = []
    rec = type("Rec", (), {"step": lambda self, *a, **k: steps.append(a), "stage": None})()
    Drafter(claude).run(_ctx(deadline), rec, out)
    assert len(sdk.requests) == 1
    [sentence] = out.draft_sentences
    assert sentence.text == "30만 원을 받았습니다." and sentence.check_reason == "NUMBER_MISMATCH"
