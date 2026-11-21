"""분석 실행의 유일한 입구(CLAUDE.md 코드 구조).

분석기를 골라 ①②③ 단계를 순서대로 부른다. DB를 직접 만지지 않고, 넘겨받은 기록기로만 단계·step을
남긴다. 마감(150초)은 단계 사이마다 확인한다.
"""

import time
from dataclasses import dataclass
from typing import Protocol

from app.agent.steps import STAGES, AgentTimeout, Recorder


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    doc_type: str
    original_name: str


@dataclass(frozen=True)
class RunContext:
    case_id: str
    run_id: str
    agent: str
    inflow_type: str
    reported_amount_krw: int
    narrative: str
    sample_scenario: str | None
    evidence: tuple[EvidenceRef, ...]
    # time.monotonic() 기준 마감 시각
    deadline: float

    def check_deadline(self) -> None:
        if time.monotonic() > self.deadline:
            raise AgentTimeout()


class Analyzer(Protocol):
    def extract(self, ctx: RunContext, rec: Recorder) -> None: ...

    def compare(self, ctx: RunContext, rec: Recorder) -> None: ...

    def draft(self, ctx: RunContext, rec: Recorder) -> None: ...


class EmptyAnalyzer:
    """아무것도 하지 않는 분석기. 가짜 분석기(T08)가 생기기 전 실행 흐름 확인용."""

    def extract(self, ctx: RunContext, rec: Recorder) -> None:
        pass

    def compare(self, ctx: RunContext, rec: Recorder) -> None:
        pass

    def draft(self, ctx: RunContext, rec: Recorder) -> None:
        pass


def select_analyzer(agent: str) -> Analyzer:
    """`AGENT_LLM` 값으로 분석기를 고른다. scripted는 T08, claude는 T16에서 붙인다."""
    return EmptyAnalyzer()


def execute(ctx: RunContext, rec: Recorder) -> None:
    analyzer = select_analyzer(ctx.agent)
    steps = {
        "EXTRACTING": analyzer.extract,
        "COMPARING": analyzer.compare,
        "DRAFTING": analyzer.draft,
    }
    for stage, _label in STAGES:
        ctx.check_deadline()
        rec.stage(stage)
        steps[stage](ctx, rec)
    ctx.check_deadline()
