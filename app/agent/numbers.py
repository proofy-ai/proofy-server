"""문장 속 금액·날짜 읽기.

초안 확인 필요 규칙(`services/drafts.py`, T09)과 초안 후검증(T17)이 같이 쓴다.

읽기만 하고 계산하지 않는다(원칙 2). "15만 원" → 150000, "11월 8일"·"2026-11-08"·"11/8" → (11, 8).
"""

import re

# "15만 원", "12만원", "15만 2000원"
_MAN_WON = re.compile(r"(\d[\d,]*)\s*만(?:\s*(\d[\d,]*))?\s*원")
# "150,000원"
_WON = re.compile(r"(\d[\d,]*)\s*원")
_MONTH_DAY = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_ISO_DATE = re.compile(r"\d{4}-(\d{1,2})-(\d{1,2})")
_SLASH_DATE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)")


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def amounts(text: str) -> set[int]:
    """문장 속 원 단위 금액들."""
    found = set()
    for man, rest in _MAN_WON.findall(text):
        found.add(_int(man) * 10_000 + (_int(rest) if rest else 0))
    for won in _WON.findall(text):
        found.add(_int(won))
    return found


def month_days(text: str) -> set[tuple[int, int]]:
    """문장 속 (월, 일)들."""
    found = set()
    for pattern in (_MONTH_DAY, _ISO_DATE, _SLASH_DATE):
        for month, day in pattern.findall(text):
            found.add((int(month), int(day)))
    return found
