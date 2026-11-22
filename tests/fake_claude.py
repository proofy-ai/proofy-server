"""테스트용 가짜 Claude SDK 클라이언트(T16). 실제 API는 부르지 않는다.

`responses`의 응답을 차례로 돌려주고, 받은 요청(kwargs)을 `requests`에 모은다.
응답 항목이 함수면 그때까지의 요청을 보고 응답을 만든다.
"""

import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import app.agent.compare as compare
from app.agent.llm import ClaudeClient


def text(payload: dict[str, Any], model: str = "claude-opus-5-5") -> SimpleNamespace:
    return response([SimpleNamespace(type="text", text=json.dumps(payload))], "end_turn", model)


def tool_use(*calls: tuple[str, str, dict[str, Any]]) -> SimpleNamespace:
    blocks = [SimpleNamespace(type="tool_use", id=i, name=n, input=a) for i, n, a in calls]
    return response(blocks, "tool_use")


def refusal() -> SimpleNamespace:
    r = response([], "refusal")
    r.stop_details = SimpleNamespace(category="cyber", explanation=None)
    return r


def response(content: list[Any], stop: str, model: str = "claude-opus-5-5") -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=100,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(
        content=content, stop_reason=stop, model=model, usage=usage, stop_details=None
    )


EMPTY = {"findings": [], "recommendedDocs": []}


class FakeSdk:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        # 이력은 이후 턴에서 늘어나므로 그때의 사본을 남긴다
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        item = self.responses.pop(0) if self.responses else text(EMPTY)
        return item(self.requests) if isinstance(item, Callable) else item


def install(monkeypatch, responses: list[Any]) -> FakeSdk:
    """`ClaudeAnalyzer`가 만드는 클라이언트를 가짜 SDK로 바꾼다."""
    sdk = FakeSdk(responses)

    def factory(api_key, model, effort, deadline):
        return ClaudeClient(api_key, model, effort, deadline, client=sdk)

    monkeypatch.setattr(compare, "ClaudeClient", factory)
    return sdk
