"""개인정보 가리기(T14). 외부 AI에 보내기 전에 서버 코드가 규칙으로만 가린다(원칙 4).

가리기 전 글자를 AI에 보낼 수 없으므로 이름 찾기도 AI에 맡기지 않는다.

- 번호: 주민등록번호, 전화번호, 사업자등록번호, 계좌번호. 금액·날짜·시각은 대조에 쓰므로
  그대로 둔다.
- 이름: **사건 이름 목록**. 한 사건의 서류에서 `예금주`·`대표자`·`성명` 뒤의 이름과 거래내역 행의
  거래상대 칸을 모으고, 사연에서는 `○○○ 씨`를 모은다. 이 목록의 이름을 그 사건의 모든 서류 줄과
  사연에서 띄어쓰기를 무시하고 가린다(`김민수`, `김 민수` → `김*수`).
- 한 글자 틀리게 읽은 이름(OCR `김민슈`)은 찾지 못한다(T14 결정 5, 남은 위험).

`MaskedText`는 이 모듈의 함수만 만든다. 외부 AI 호출(`agent/llm.py`, T16)은 이 타입만 받는다.
"""

import json
import re
from collections.abc import Iterable
from typing import Any


class MaskedText(str):
    """개인정보를 가린 글. 이 모듈 밖에서 만들지 않는다."""

    __slots__ = ()


_HANGUL_NAME = r"[가-힣]{2,4}"

# 번호 규칙. 앞의 것부터 적용한다(가린 자리는 `*`라 뒤 규칙에 다시 걸리지 않는다)
_RRN = re.compile(r"(?<!\d)\d{6}\s?-\s?[1-4]\d{6}(?!\d)")
_MOBILE = re.compile(r"(?<!\d)(01[016789])([-.\s]?)(\d{3,4})([-.\s]?)(\d{4})(?!\d)")
_LANDLINE = re.compile(r"(?<![\d-])(0\d{1,2})-(\d{3,4})-(\d{4})(?![\d-])")
_BUSINESS = re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{5}(?![\d-])")
# 하이픈으로 이은 숫자 묶음 또는 붙여 쓴 숫자. 숫자 합계 10~14자리만 계좌로 본다(날짜는 8자리)
_ACCOUNT = re.compile(r"(?<![\d-])\d{2,6}(?:-\d{1,7}){1,4}(?![\d-])|(?<![\d,])\d{10,14}(?![\d,])")
_ACCOUNT_DIGITS = range(10, 15)
_KEEP_TAIL = 4

# 이름 모으기
_LABELED = re.compile(
    rf"(?:^|\s)(?:예금주|대표자|성명)(?:\s*[:：]\s*|\s+)({_HANGUL_NAME})(?![가-힣])"
)
# 거래내역 행: 날짜 (시각) 입금|출금 금액 (잔액) 거래상대.
# 거래 행 추출(T15, `agent/transactions.py`)도 같은 규칙을 쓴다.
# 두 곳이 다르면 행으로 뽑힌 줄의 거래상대 이름이 가려지지 않는다
_AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?![\d,])"
TX_ROW = re.compile(
    r"^\s*(?P<y>\d{4})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})"
    r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?"
    r"\s+(?P<dir>입금|출금)"
    rf"\s+(?P<amount>{_AMOUNT})"
    rf"(?:\s+{_AMOUNT})?"
    r"(?:\s+(?P<rest>.*?))?\s*$"
)
# 씨 뒤에는 조사가 붙을 수 있다(`김민수 씨에게`). `아저씨`·`아가씨`·`마음씨`는 이름이 아니다
_NARRATIVE_SSI = re.compile(r"(?<![가-힣])([가-힣]{2,3})\s?씨")
_NOT_NAMES = frozenset({"아저", "아가", "마음"})


def _mask_digits(value: str, keep_tail: int = 0) -> str:
    """숫자만 `*`로 바꾸고 끝 `keep_tail`자리 숫자는 남긴다. 하이픈 등 모양은 둔다."""
    total = sum(c.isdigit() for c in value)
    seen = 0
    out = []
    for c in value:
        if c.isdigit():
            seen += 1
            out.append(c if seen > total - keep_tail else "*")
        else:
            out.append(c)
    return "".join(out)


def _mask_account(m: re.Match[str]) -> str:
    value = m.group(0)
    if sum(c.isdigit() for c in value) not in _ACCOUNT_DIGITS:
        return value
    return _mask_digits(value, _KEEP_TAIL)


def _mask_numbers(text: str) -> str:
    text = _RRN.sub(lambda m: _mask_digits(m.group(0)), text)
    text = _MOBILE.sub(
        lambda m: f"{m[1]}{m[2]}{'*' * len(m[3])}{m[4]}{m[5]}",
        text,
    )
    text = _LANDLINE.sub(lambda m: f"{m[1]}-{'*' * len(m[2])}-{m[3]}", text)
    text = _BUSINESS.sub(lambda m: _mask_digits(m.group(0)), text)
    return _ACCOUNT.sub(_mask_account, text)


def mask_name(name: str) -> MaskedText:
    """`김민수` → `김*수`, `이준` → `이*`, `남궁민희` → `남**희`. 거래상대 칸(T15)에도 쓴다."""
    name = re.sub(r"\s+", "", name)
    if len(name) <= 1:
        return MaskedText(name)
    if len(name) == 2:
        return MaskedText(name[0] + "*")
    return MaskedText(name[0] + "*" * (len(name) - 2) + name[-1])


def collect_names(lines: Iterable[str]) -> set[str]:
    """서류 줄에서 이름을 모은다: `예금주`·`대표자`·`성명` 뒤, 거래내역 행의 거래상대 칸."""
    names: set[str] = set()
    for line in lines:
        names.update(_LABELED.findall(line))
        row = TX_ROW.match(line)
        if row and row["rest"] and re.fullmatch(_HANGUL_NAME, row["rest"]):
            names.add(row["rest"])
    return names


def collect_narrative_names(narrative: str) -> set[str]:
    """사연에서 `○○○ 씨` 앞의 이름을 모은다(사연에만 나오는 이름 대비)."""
    return {n for n in _NARRATIVE_SSI.findall(narrative) if n not in _NOT_NAMES}


def _name_pattern(names: Iterable[str]) -> re.Pattern[str] | None:
    # 긴 이름부터 찾는다. 글자 사이 띄어쓰기는 무시한다(T14 결정 5)
    ordered = sorted({n for n in names if len(n) >= 2}, key=len, reverse=True)
    if not ordered:
        return None
    return re.compile("|".join(r"\s*".join(map(re.escape, n)) for n in ordered))


def mask_text(text: str, names: Iterable[str] = ()) -> MaskedText:
    """번호 규칙과 이름 목록으로 가린다."""
    masked = _mask_numbers(text)
    pattern = _name_pattern(names)
    if pattern is not None:
        masked = pattern.sub(lambda m: mask_name(m.group(0)), masked)
    return MaskedText(masked)


def mask_regions(
    regions: list[dict[str, Any]], names: Iterable[str]
) -> tuple[list[dict[str, Any]], MaskedText]:
    """서류 줄마다 `maskedText`를 붙인 새 목록과, 가린 줄을 이은 글(`evidence.masked_text`)."""
    names = tuple(names)
    # `maskedText`는 `MaskedText` 그대로 둔다.
    # 외부 AI에 보낼 때 이 타입으로 가린 글인지 확인한다(T16)
    out = [{**r, "maskedText": mask_text(r["text"], names)} for r in regions]
    return out, MaskedText("\n".join(r["maskedText"] for r in out))


def masked_part(source: MaskedText, part: str) -> MaskedText:
    """가린 글의 일부(거래 행의 거래상대 칸 등)도 가린 글이다. `source` 안에 없으면 거부한다."""
    if not isinstance(source, MaskedText) or part not in source:
        raise ValueError("가린 글의 일부가 아닙니다")
    return MaskedText(part)


# `seal_payload`에서 글자 값을 그대로 둘 수 있는 칸.
# 모두 코드가 만든 값이다(ID, 종류, 날짜, 고정 라벨)
CODE_KEYS = frozenset(
    {
        "evidenceId",
        "docType",
        "docTypeLabel",
        "transactionId",
        "occurredAt",
        "direction",
        "inflowType",
        "fixedChecklist",
    }
)


def seal_payload(payload: Any) -> MaskedText:
    """외부 AI에 보낼 자료를 JSON 글로 묶는다(원칙 4를 코드로 보장, T16).

    글자 값은 `MaskedText`이거나 `CODE_KEYS` 칸의 코드 값이어야 한다. 숫자·참거짓·null은 그대로.
    가리지 않은 글이 섞여 있으면 `TypeError`.
    """
    _check_sealed(payload, None)
    return MaskedText(json.dumps(payload, ensure_ascii=False))


def _check_sealed(value: Any, key: str | None) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _check_sealed(v, k)
    elif isinstance(value, list | tuple):
        for v in value:
            _check_sealed(v, key)
    elif isinstance(value, str):
        if not isinstance(value, MaskedText) and key not in CODE_KEYS:
            raise TypeError(f"가리지 않은 글은 외부 AI에 보낼 수 없습니다(칸 {key})")
    elif value is not None and not isinstance(value, int | float | bool):
        raise TypeError(f"보낼 수 없는 값입니다(칸 {key})")
