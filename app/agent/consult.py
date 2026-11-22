"""상담 안내 정하기(T10, agent-design 2.1, 계약 4.9·4.11).

- 표현 목록(코드, `app/services/safety.py`)이 사연·답 원문에서 찾은 표현을 받는다.
- 실제 분석은 에이전트가 문맥을 읽어 상담을 권할지(`consult`) 정하고, 사연·답 원문을 인용한다.
  서버는 인용이 AI가 본 가린 사연·답에 있는지 확인한다(원칙 3). AI가 지어낸 인용만 거른다.
- 가짜 분석·미리 만든 결과는 표현 목록만으로 정한다.

결과는 `matchedPhrases`(화면에 보이는 확인된 글자)와 step 목록이다.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.masking import MaskedText
from app.agent.output import Question
from app.agent.steps import StepType

# 상담 안내로 끝날 때 AI가 질문을 내지 않았으면 쓰는 질문(계약 4.11: 상황을 묻는 질문이 있다)
REFERRAL_QUESTION = Question(
    text="어떤 상황에서 통장(계좌)을 건네거나 돈을 옮기게 됐는지 알려 주세요.",
    why="사연의 표현만으로는 상황을 알 수 없어요. 답해 주시면 다시 살펴볼게요.",
)
SAFETY_TITLE = "상담 안내 확인"
QUOTE_CHARS = 60
REASON_CHARS = 80
_SPACE = re.compile(r"\s+")


@dataclass
class ConsultDecision:
    # 상담 안내로 끝나면 화면에 보일 확인된 글자. 아니면 None
    phrases: tuple[str, ...] | None = None
    steps: list[tuple[StepType, str, str]] = field(default_factory=list)


def _squash(text: str) -> str:
    return _SPACE.sub("", text)


def _quoted(phrases: tuple[str, ...]) -> str:
    return ", ".join(f"'{p}'" for p in phrases)


def by_phrases(code_hits: tuple[str, ...]) -> ConsultDecision:
    """가짜 분석·미리 만든 결과: 표현 목록만으로 정한다."""
    if not code_hits:
        return ConsultDecision()
    summary = f"사연의 {_quoted(code_hits)} 표현이 있어 초안 대신 상담 안내를 드립니다."
    return ConsultDecision(code_hits, [("SAFETY", SAFETY_TITLE, summary)])


def check_consult(
    raw: Any, basis: MaskedText | None, code_hits: tuple[str, ...]
) -> ConsultDecision:
    """AI의 상담 권유(`compare.OUTPUT_SCHEMA` `consult`)를 확인한다(T10-d).

    - 권하고 인용이 원문에 있으면 → 그 인용으로 상담 안내
    - 권했지만 원문에 있는 인용이 없으면 → 코드가 찾은 표현으로 안내, 그것도 없으면 안내 안 함
      (step `VERIFY`)
    - 권하지 않으면 → 코드가 찾았어도 안내 안 함(step `SAFETY`에 이유)
    """
    # drafting → scripted → 이 모듈 순서로 불러오므로 여기서 불러온다(순환 import 방지)
    from app.agent.drafting import JUDGMENT

    item = raw if isinstance(raw, dict) else {}
    recommend = item.get("recommend") is True
    if not recommend:
        if not code_hits:
            return ConsultDecision()
        reason = str(item.get("reason") or "").strip()[:REASON_CHARS]
        summary = f"사연의 {_quoted(code_hits)}를 문맥으로 확인해 상담 안내는 하지 않았습니다."
        if reason and not JUDGMENT.search(reason):
            summary += f" {reason}"
        return ConsultDecision(None, [("SAFETY", SAFETY_TITLE, summary)])

    text = _squash(basis or "")
    verified: list[str] = []
    missing = 0
    for quote in item.get("quotes") or []:
        if not isinstance(quote, str) or not quote.strip():
            continue
        quote = quote.strip()[:QUOTE_CHARS]
        if text and _squash(quote) in text:
            if quote not in verified:
                verified.append(quote)
        else:
            missing += 1
    steps: list[tuple[StepType, str, str]] = []
    if missing:
        steps.append(
            ("VERIFY", "상담 안내 인용 확인", f"사연·답에서 찾지 못한 인용 {missing}개를 뺐습니다.")
        )
    if verified:
        phrases = tuple(verified)
        steps.append(
            (
                "SAFETY",
                SAFETY_TITLE,
                f"사연의 {_quoted(phrases)}를 문맥으로 확인해 초안 대신 상담 안내를 드립니다.",
            )
        )
        return ConsultDecision(phrases, steps)
    if code_hits:
        steps.append(
            (
                "SAFETY",
                SAFETY_TITLE,
                f"사연의 {_quoted(code_hits)} 표현이 있어 초안 대신 상담 안내를 드립니다.",
            )
        )
        return ConsultDecision(code_hits, steps)
    summary = "원문에서 확인한 표현이 없어 상담 안내를 하지 않았습니다."
    steps.append(("VERIFY", "상담 안내 인용 확인", summary))
    return ConsultDecision(None, steps)
