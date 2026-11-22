"""상담 안내 표현 찾기(T10, 계약 4.9·4.11, agent-design 2.1 ⓪ SAFETY).

사연과 답 **원문**에서 정해 둔 표현을 코드로 찾는다. 코드는 후보만 찾고 판단하지 않는다(11/22 결정).

- 실제 분석: 부정문까지 포함한 후보 전부(`find_candidates`)를 runner가 가려 에이전트에 "확인할
  표현"으로 넘기고, 에이전트가 문맥을 읽어 상담을 권할지 정한다.
- 부정문을 뺀 목록(`find_phrases`)은 AI가 없는 곳에서만 쓴다: 가짜 분석·미리 만든 결과의 결정,
  AI가 권했지만 인용이 원문에 없을 때 대신 보여 줄 표현.

이 안내는 사람이나 사건을 판정하는 것이 아니라, 이의제기 전에 상담이 먼저 필요해 보이는 표현이
있음을 알리는 것이다(계약 4.11).
"""

import re
from collections.abc import Iterable

REFERRAL_CODE = "LEGAL_CONSULT"
REFERRAL_MESSAGE = (
    "사연에 통장을 빌려주거나 남의 돈을 대신 보낸 것으로 보이는 표현이 있어 소명서 초안을 만들지 "
    "않았습니다. 이런 경우에는 이의제기 전에 법률 상담을 먼저 받으세요."
)
CONTACTS = (
    {"name": "대한법률구조공단", "phone": "132"},
    {"name": "금융감독원", "phone": "1332"},
)

_JOSA = r"\s*(?:을|를|이|가|은|는|도|와|랑|까지)?\s*"
_PATTERNS = (
    # 1. 통장·계좌·체크카드 대여·양도
    re.compile(
        # 그냥 "카드"는 넣지 않는다("카드를 판매하는 가게"가 걸림)
        rf"(?:통장|계좌|체크\s?카드|직불\s?카드){_JOSA}"
        r"(?:빌려|대여|양도|넘겨|넘겼|건네|건넸|팔았|팔아|판매|매매)"
    ),
    # 2. 비밀번호·OTP 전달
    re.compile(
        rf"(?:비밀번호|비번|OTP|보안\s?카드|인증서){_JOSA}"
        r"(?:알려|전달|넘겨|넘겼|가르쳐|보내|보냈)"
    ),
    # 3. 환전·구매대행·송금 알바
    re.compile(r"(?:환전|구매\s?대행|송금|이체|대리\s?입금)\s*(?:알바|아르바이트|부업|대행)"),
    # 4. 현금 인출 후 전달
    re.compile(
        rf"(?:현금|돈){_JOSA}(?:인출|찾아|뽑아)[^.!?\n]{{0,20}}?"
        r"(?:전달|건네|건넸|넘겨|넘겼|갖다\s?줬)"
    ),
)
# 걸린 곳 바로 뒤에 부정이 오면 걸지 않는다("통장을 빌려준 적이 없습니다")
_NEGATION = re.compile(r"적이\s?없|적\s?없|지\s?않|않았|않습|거절|거부|안\s?했")
NEGATION_WINDOW = 15


def find_phrases(texts: Iterable[str]) -> list[str]:
    """부정문을 뺀 표현(글자 그대로), 나온 순서, 중복 없이. AI가 없는 곳에서만 쓴다."""
    return _collect(texts, skip_negated=True)


def find_candidates(texts: Iterable[str]) -> list[str]:
    """부정문까지 포함한 후보 전부. 실제 분석에서 에이전트에 넘겨 문맥으로 판단하게 한다."""
    return _collect(texts, skip_negated=False)


def _collect(texts: Iterable[str], skip_negated: bool) -> list[str]:
    found: list[str] = []
    for text in texts:
        for _, phrase in _matches(text or "", skip_negated):
            if phrase not in found:
                found.append(phrase)
    return found


def _matches(text: str, skip_negated: bool) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(text):
            after = text[m.end() : m.end() + NEGATION_WINDOW]
            if skip_negated and _NEGATION.search(after):
                continue
            hits.append((m.start(), m.group(0).strip()))
    return sorted(hits)
