"""분석 단계·step·오류 정의(계약 4.10).

화면 단계(`stages`)는 세 개다. ⓪ SAFETY와 ①-b 거래 행 추출은 `EXTRACTING`에, ④ VERIFY는 `DRAFTING`에
포함해 보여 준다(`docs/agent-design.md` 2절). FE는 문구를 하드코딩하지 않고 `label`을 그대로 쓴다.
"""

from typing import Literal, Protocol

Stage = Literal["EXTRACTING", "COMPARING", "DRAFTING", "FINISHED"]
StepType = Literal[
    "OCR", "TOOL_CALL", "FINDING", "CONFLICT", "DRAFT", "VERIFY", "FALLBACK", "SAFETY", "FAILED"
]
StepStatus = Literal["DONE", "FAILED"]

# 화면에 보이는 세 단계와 라벨(순서대로)
STAGES: tuple[tuple[Stage, str], ...] = (
    ("EXTRACTING", "글자 읽는 중"),
    ("COMPARING", "거래내역과 대조 중"),
    ("DRAFTING", "초안 작성 중"),
)


class Recorder(Protocol):
    """분석기가 진행을 남기는 곳. 구현은 서비스 계층(DB에 바로 저장)에 있다."""

    def stage(self, stage: Stage) -> None: ...

    def step(
        self, type: StepType, title: str, summary: str | None, status: StepStatus = "DONE"
    ) -> None: ...


class AgentError(Exception):
    """분석 실패. `code`는 계약 4.10의 `error.code` 값이다."""

    code = "AGENT_FAILED"
    message = "분석 중 문제가 생겼습니다. 다시 시도해 주세요."

    def __init__(self, message: str | None = None) -> None:
        if message:
            self.message = message
        super().__init__(self.message)


class AgentTimeout(AgentError):
    code = "AGENT_TIMEOUT"
    message = "분석 시간이 너무 오래 걸려 멈췄습니다. 다시 시도해 주세요."


class AgentRefused(AgentError):
    code = "AGENT_REFUSED"
    message = "AI가 이 분석을 처리하지 못했습니다. 사연을 확인하고 다시 시도해 주세요."


class RunStopped(Exception):
    """실행이 밖에서 끝났다(시간 초과 처리, 사건 삭제). 결과를 쓰지 않고 조용히 멈춘다."""
