"""외부 AI(Claude) 호출의 유일한 곳(CLAUDE.md 코드 구조, `docs/agent-design.md` 5절).

- 사용자 글과 도구 결과는 `MaskedText`(가린 글)만 받는다(원칙 4). 아니면 `TypeError`.
- 요청 하나 = `turn()` 한 번. 도구 루프와 프롬프트는 `agent/compare.py`가 짠다.
- SDK 재시도는 끄고(`max_retries=0`) 실행 마감 안에서만 직접 다시 시도한다.
- thinking 파라미터는 넣지 않는다(Opus 5.5는 adaptive로 돈다).
  응답 블록은 바꾸지 않고 이력에 붙인다.
- 안전 분류기 거절에 대비해 서버측 fallback을 켜고, 대신 답한 모델의 단가로 비용을 센다.

가져온 코드(corebank-objection-agent, 원칙 6):
- `objection_agent/llm/claude.py` 27~66행 단가표·`cost_micro_usd`, 41~51행 재시도 상수,
  153~173행 `_create`, 176~181행 `_retry_after`, 198~211행 `_tool_error`·`_tool_content`,
  234~240행 `_usage`
- `objection_agent/llm/port.py` 32~44행 `Usage`, 66~93행 `Deadline`(점유 시계 뺌)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import anthropic

from app.agent.masking import MaskedText
from app.agent.steps import AgentError, AgentRefused, AgentTimeout

logger = logging.getLogger(__name__)

# 백만 토큰당 달러 = 토큰당 백만분의 1달러(입력, 출력, 캐시 읽기, 5분 캐시 쓰기)
PRICES_MICRO_USD = {
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.2, "cache_write": 5.0},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.1, "cache_write": 2.5},
    "claude-haiku-5-5": {"input": 0.1, "output": 0.5, "cache_read": 0.01, "cache_write": 0.125},
}
# 모르는 모델(서버측 fallback이 고른 모델 등)은 가장 비싼 단가로 센다
PRICE_MICRO_USD = {"input": 10.0, "output": 50.0, "cache_read": 1.0, "cache_write": 12.5}

# 서버측 fallback이 없는 모델에는 보내지 않는다
NO_FALLBACK_PREFIXES = ("claude-haiku",)
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# 요청 하나의 시간 제한(초). 실행 마감이 더 가까우면 그쪽에 맞춘다
REQUEST_TIMEOUT = 90.0
# 다시 시도할 응답 코드. 429는 분당 한도, 529는 과부하
RETRY_STATUSES = (429, 500, 502, 503, 504, 529)
MAX_ATTEMPTS = 4
# 모델 호출 직전에 이만큼 남아 있지 않으면 부르지 않는다
CALL_RESERVE_SECONDS = 10.0
# 도구 결과 상한(agent-design 2.4)
MAX_TOOL_ITEMS = 200
MAX_TOOL_CHARS = 60_000
MAX_OUTPUT_TOKENS = 16_000


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    @property
    def all_input_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class Deadline:
    """실행 마감(`time.monotonic()` 기준)."""

    expires_at: float

    def remaining(self) -> float:
        return self.expires_at - time.monotonic()

    def check(self, reserve: float = 0.0) -> None:
        if self.remaining() <= reserve:
            raise AgentTimeout()


def _price(model: str) -> dict[str, float]:
    """응답 모델 이름(접미사가 붙을 수 있다)으로 단가를 찾는다."""
    return next((v for k, v in PRICES_MICRO_USD.items() if model.startswith(k)), PRICE_MICRO_USD)


def cost_micro_usd(usage: Usage, model: str = "claude-opus-5-5") -> int:
    price = _price(model)
    return round(
        usage.input_tokens * price["input"]
        + usage.output_tokens * price["output"]
        + usage.cache_read_tokens * price["cache_read"]
        + usage.cache_write_tokens * price["cache_write"]
    )


def user_text(text: MaskedText) -> dict[str, Any]:
    """사용자 메시지 글 블록. 가린 글만 받는다."""
    _require_masked(text)
    return {"type": "text", "text": str(text)}


def tool_result(tool_use_id: str, content: MaskedText) -> dict[str, Any]:
    _require_masked(content)
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": str(content)}


def tool_error(tool_use_id: str, message: str) -> dict[str, Any]:
    """도구 오류. `message`는 코드가 만든 고정 안내문이다(사용자 글을 넣지 않는다)."""
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": message, "is_error": True}


def limit_items(items: list[Any]) -> tuple[list[Any], str | None]:
    """도구 결과를 건수·글자 수 상한 안으로 줄인다. 잘랐으면 모델에 줄 안내문도 돌려준다."""
    kept = items[:MAX_TOOL_ITEMS]
    while len(json.dumps(kept, ensure_ascii=False)) > MAX_TOOL_CHARS and kept:
        kept = kept[: len(kept) * 3 // 4]
    if len(kept) < len(items):
        return kept, f"전체 {len(items)}건 중 앞 {len(kept)}건만 보냄. 범위를 좁혀 다시 조회하세요"
    return kept, None


def _require_masked(text: Any) -> None:
    if not isinstance(text, MaskedText):
        raise TypeError("외부 AI에는 가린 글(MaskedText)만 보낼 수 있습니다")


@dataclass
class Turn:
    content: list[Any]
    stop_reason: str | None
    model: str

    def text(self) -> str:
        return "".join(b.text for b in self.content if b.type == "text")

    def tool_uses(self) -> list[Any]:
        return [b for b in self.content if b.type == "tool_use"]


class ClaudeClient:
    """한 실행에 하나. 토큰·비용을 모은다."""

    def __init__(
        self,
        api_key: str | None,
        model: str,
        effort: str,
        deadline: Deadline,
        client: Any | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise AgentError("AI 연결 설정이 없습니다. 관리자에게 알려 주세요.")
            client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        self._client = client
        self._model = model
        self._effort = effort
        self.deadline = deadline
        self.usage = Usage()
        self.cost_micro_usd = 0
        # 마지막으로 답한 모델(서버측 fallback이면 다른 모델)
        self.model = model

    def turn(
        self,
        system: str,
        tools: list[dict[str, Any]],
        schema: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> Turn:
        """요청 한 번. 거절·출력 한도 초과는 `AgentRefused`, 마감은 `AgentTimeout`."""
        fallback: dict[str, Any] = (
            {}
            if self._model.startswith(NO_FALLBACK_PREFIXES)
            else {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        )
        response = self._create(
            model=self._model,
            max_tokens=MAX_OUTPUT_TOKENS,
            # 최상위 자동 캐시: 도구 루프의 앞 턴 이력을 다음 턴에 캐시 읽기로 센다
            cache_control={"type": "ephemeral"},
            system=system,
            tools=tools,
            output_config={
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=messages,
            **fallback,
        )
        model = getattr(response, "model", None) or self._model
        turn_usage = _usage(response.usage)
        self.usage.add(turn_usage)
        self.cost_micro_usd += cost_micro_usd(turn_usage, model)
        self.model = model

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            logger.warning(
                "모델이 거절함: category=%s",
                getattr(details, "category", None) if details else None,
            )
            raise AgentRefused()
        if response.stop_reason == "max_tokens":
            logger.warning("모델 출력이 한도를 넘음")
            raise AgentRefused()
        return Turn(list(response.content), response.stop_reason, model)

    def _create(self, **kwargs: Any) -> Any:
        """요청 하나. 일시 오류는 실행 마감 안에서만 다시 시도하고,
        요청 시간 제한도 마감에 맞춘다."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.deadline.check(CALL_RESERVE_SECONDS)
            timeout = min(REQUEST_TIMEOUT, self.deadline.remaining() - CALL_RESERVE_SECONDS / 2)
            try:
                return self._client.beta.messages.create(timeout=timeout, **kwargs)
            except anthropic.APIStatusError as exc:
                if exc.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                    logger.warning("Claude 요청 실패: %s", exc.status_code)
                    raise AgentError() from exc
                wait = _retry_after(exc) or min(2.0**attempt, 20.0)
            except anthropic.APIConnectionError as exc:  # 시간 초과 포함
                if attempt == MAX_ATTEMPTS:
                    raise AgentError() from exc
                wait = min(2.0**attempt, 20.0)
            if self.deadline.remaining() - wait <= CALL_RESERVE_SECONDS:
                raise AgentTimeout()
            time.sleep(wait)
        raise AssertionError("도달하지 않는다")  # pragma: no cover


def _retry_after(exc: anthropic.APIStatusError) -> float | None:
    try:
        return float(exc.response.headers.get("retry-after", ""))
    except (TypeError, ValueError, AttributeError):
        return None


def _usage(raw: Any) -> Usage:
    return Usage(
        input_tokens=getattr(raw, "input_tokens", None) or 0,
        output_tokens=getattr(raw, "output_tokens", None) or 0,
        cache_read_tokens=getattr(raw, "cache_read_input_tokens", None) or 0,
        cache_write_tokens=getattr(raw, "cache_creation_input_tokens", None) or 0,
    )
