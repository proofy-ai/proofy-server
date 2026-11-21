"""T12 합성 샘플 서류가 가짜 분석기(`app/agent/scripted.py`)의 값과 맞는지(계약 테스트 아님).

서류는 `scripts/make_samples.py`로 만들어 커밋한 파일이다. 스크립트를 고치면 다시 돌려야 한다.
"""

import re

import pytest
from PIL import Image
from pypdf import PdfReader

from app.agent.scripted import (
    GOODS_CHAT_QUOTE,
    GOODS_CHAT_REGION,
    GOODS_ROWS,
    THREAT_QUOTE,
    THREAT_REGION,
    UNEXPECTED_ROWS,
)
from app.services.samples import SAMPLE_DIR, SCENARIOS
from scripts.make_samples import (
    CARD,
    FULL_NAMES,
    GOODS_CHAT,
    GOODS_CHAT_TITLE,
    THREAT_CHAT,
    THREAT_TITLE,
    chat_lines,
)

ROWS = {"goods": GOODS_ROWS, "unexpected": UNEXPECTED_ROWS}
DATE_LINE = re.compile(r"^\d{4}-\d{2}-\d{2} ")


def _pdf_lines(key: str) -> list[str]:
    text = PdfReader(SAMPLE_DIR / key / "transaction_record.pdf").pages[0].extract_text()
    return [line.strip() for line in text.splitlines() if line.strip()]


@pytest.mark.parametrize("key", ["goods", "unexpected"])
def test_statement_rows_match_scripted_rows_one_line_each(key):
    lines = _pdf_lines(key)
    assert "합성 데이터" in lines[0]
    row_lines = [line for line in lines if DATE_LINE.match(line)]
    # 가짜 분석기와 정확히 같은 행만(T12 결정 ③)
    assert len(row_lines) == len(ROWS[key])
    for line, (_, day, direction, amount, who) in zip(row_lines, ROWS[key], strict=True):
        # 날짜·구분·금액·상대가 한 줄에 있다(행 추출 T15는 줄 단위)
        assert line.startswith(day.isoformat())
        assert ("입금" if direction == "IN" else "출금") in line
        assert f" {amount:,} " in line
        assert (FULL_NAMES[who] if who else CARD) in line


def test_full_names_mask_to_scripted_counterparty():
    for masked, full in FULL_NAMES.items():
        assert f"{full[0]}*{full[-1]}" == masked


def test_quotes_sit_on_scripted_region_lines():
    assert chat_lines(GOODS_CHAT_TITLE, GOODS_CHAT)[GOODS_CHAT_REGION] == GOODS_CHAT_QUOTE
    assert chat_lines(THREAT_TITLE, THREAT_CHAT)[THREAT_REGION] == THREAT_QUOTE


def test_every_sample_file_is_marked_synthetic():
    for scenario in SCENARIOS.values():
        for doc in scenario.documents:
            path = SAMPLE_DIR / scenario.key / doc.file_name
            if path.suffix == ".pdf":
                meta = PdfReader(path).metadata
                assert "합성 데이터" in (meta.author or "")
            else:
                with Image.open(path) as img:
                    assert "합성 데이터" in img.info.get("Description", "")
