"""거래내역서 줄 → 거래 행(T15). AI 없이 코드 규칙으로만 뽑는다(T15 결정 1, 원칙 2).

한 줄이 `날짜 (시각) 입금|출금 금액 (잔액) 거래상대` 모양이면 거래 행이다.
날짜·방향·금액은 원문 줄(`text`)에서, 거래상대는 가린 줄(`maskedText`, T14)에서 가져온다.
규칙에 맞지 않는 줄(머리 줄, 조회기간, 대화 문장, 모양이 다른 은행 표)은 행이 되지 않는다.
"""

from collections.abc import Iterable
from datetime import date
from typing import Any

from app.agent.masking import TX_ROW
from app.agent.output import TransactionRow

_DIRECTIONS = {"입금": "IN", "출금": "OUT"}


def _parse(line: str) -> tuple[date, str, int, str | None] | None:
    m = TX_ROW.match(line)
    if m is None:
        return None
    try:
        day = date(int(m["y"]), int(m["m"]), int(m["d"]))
    except ValueError:
        return None
    amount = int(m["amount"].replace(",", ""))
    if amount <= 0:
        return None
    return day, _DIRECTIONS[m["dir"]], amount, (m["rest"] or None)


def row_matches_source(row: TransactionRow, text: str) -> bool:
    """금액·날짜 문자열이 그 줄에 실제로 있는가(ERD 3.4 저장 조건). T16 AI가 고른 행에도 쓴다."""
    amount_forms = {f"{row.amount_krw:,}", str(row.amount_krw)}
    d = row.occurred_at
    date_forms = {f"{d.year}{sep}{d.month:02d}{sep}{d.day:02d}" for sep in "-./"} | {
        f"{d.year}{sep}{d.month}{sep}{d.day}" for sep in "-./"
    }
    return any(a in text for a in amount_forms) and any(f in text for f in date_forms)


def parse_rows(
    regions: Iterable[dict[str, Any]], evidence_id: str, start_key: int = 1
) -> list[TransactionRow]:
    """거래내역서 한 장의 줄에서 거래 행을 뽑는다. 열쇠는 `t{start_key}`부터 줄 순서대로."""
    rows: list[TransactionRow] = []
    for region in regions:
        text = region["text"]
        parsed = _parse(text)
        if parsed is None:
            continue
        day, direction, amount, _ = parsed
        masked = _parse(region.get("maskedText", ""))
        counterparty = masked[3] if masked is not None else None
        row = TransactionRow(
            key=f"t{start_key + len(rows)}",
            evidence_id=evidence_id,
            region_index=region["index"],
            direction=direction,  # type: ignore[arg-type]
            amount_krw=amount,
            occurred_at=day,
            counterparty_masked=counterparty[:100] if counterparty else None,
            raw_text=text.strip(),
        )
        if row_matches_source(row, text):
            rows.append(row)
    return rows
