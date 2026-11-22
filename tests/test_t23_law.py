"""T23 법령 조회 도구. 단위 테스트(계약 테스트 아님). 실제 Claude는 부르지 않는다."""

import fake_claude
import flow

from app.agent import law
from app.agent.compare import ClaudeAnalyzer


def test_articles_split_by_article_without_addenda():
    articles = law.articles()
    assert articles["LAW:7"].title == "지급정지 등에 대한 이의제기"
    assert articles["DECREE:7"].title == "지급정지 등에 대한 이의제기"
    assert articles["LAW:2의2"].label == "법 제2조의2"
    # 부칙의 "제1조(시행일)"이 본문 제1조를 덮지 않는다
    assert articles["LAW:1"].title == "목적"
    assert articles["DECREE:1"].title == "목적"
    assert "LAW:19" not in articles
    assert articles["FORM4"].label == "별지 제4호 이의제기신청서"
    # 개정 이력 표시는 조회 글에서 뺀다
    assert "<개정" not in articles["LAW:7"].text


def test_search_finds_objection_article():
    assert law.search("재화 용역 대가 이의제기")[0]["ref"] == "LAW:7"
    assert law.search("제7조")[0]["ref"] == "LAW:7"
    assert law.search("시행령 제7조")[0]["ref"] == "DECREE:7"
    assert law.search("없는낱말없는낱말") == []


def test_check_quote_ignores_spaces_and_labels_paragraph_and_item():
    ok, label = law.check_quote("LAW:7", "재화 또는 용역의  공급에 대한\n대가로 받았거나")
    assert (ok, label) == (True, "법 제7조 제1항 제2호")
    assert law.check_quote("LAW:7", "명의인은 다음 각 호의") == (True, "법 제7조 제1항")
    assert law.check_quote("LAW:7", "제3조제3항 또는 제6조제2항") == (True, "법 제7조 제2항")
    assert law.check_quote("DECREE:7", "별지 제4호서식의 이의제기신청서") == (True, "시행령 제7조")
    assert law.check_quote("FORM4", "이의제기 사유(구체적으로 기재합니다)")[0] is True
    # 원문에 없는 인용, 다른 조항의 인용, 없는 조항
    assert law.check_quote("LAW:7", "지급정지가 해제된다") == (False, "법 제7조")
    assert law.check_quote("LAW:8", "재화 또는 용역의 공급에 대한 대가로")[0] is False
    assert law.check_quote("LAW:99", "아무 글") == (False, None)


def test_law_tools_leave_steps_and_remember_refs(claude_app, monkeypatch):
    client = claude_app
    case_id, auth = flow.sample(client)
    seen: list[set[str]] = []
    original = ClaudeAnalyzer.compare

    def compare(self, ctx, rec, out):
        original(self, ctx, rec, out)
        seen.append(set(self.seen_law_refs))

    monkeypatch.setattr(ClaudeAnalyzer, "compare", compare)
    sdk = fake_claude.install(
        monkeypatch,
        [
            fake_claude.tool_use(
                ("u1", "search_law", {"reason": "물품 대금이 사유가 되는지", "query": "재화 대가"}),
                ("u2", "get_law_article", {"reason": "제7조 원문을 읽으려고", "ref": "LAW:7"}),
                ("u3", "get_law_article", {"reason": "없는 조항", "ref": "LAW:99"}),
            ),
            fake_claude.text(fake_claude.EMPTY),
        ],
    )
    run = flow.run(client, case_id, auth)
    assert run["status"] == "SUCCEEDED"
    steps = [s for s in run["steps"] if s["title"] == "법령 조회"]
    assert [s["type"] for s in steps] == ["TOOL_CALL"] * 3
    assert steps[0]["summary"].startswith("물품 대금이 사유가 되는지 → 조항 ")
    assert steps[1]["summary"] == "제7조 원문을 읽으려고 → 법 제7조"
    assert steps[2]["status"] == "FAILED"
    assert "LAW:7" in seen[0] and "LAW:99" not in seen[0]

    # AI가 받은 조항 원문
    results = sdk.requests[1]["messages"][-1]["content"]
    assert "재화 또는 용역의 공급에 대한 대가로" in str(results[1]["content"])
    assert results[2]["is_error"] is True
