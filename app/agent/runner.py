"""분석 실행의 유일한 입구(CLAUDE.md 코드 구조).

분석기를 골라 ①②③ 단계를 순서대로 부른다. DB를 직접 만지지 않고, 넘겨받은 기록기로만 단계·step을
남기며, 결과는 `AnalysisOutput`으로 돌려준다(저장은 서비스 계층).
마감(150초)은 단계 사이마다 확인한다.
"""

import time
from dataclasses import dataclass
from typing import Protocol

from app.agent.output import AnalysisOutput
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
    # 가짜 분석의 단계 사이 쉬는 시간(SCRIPTED_STAGE_DELAY_SECONDS)
    stage_delay_seconds: float = 0

    def check_deadline(self) -> None:
        if time.monotonic() > self.deadline:
            raise AgentTimeout()


class Analyzer(Protocol):
    def extract(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None: ...

    def compare(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None: ...

    def draft(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None: ...


def select_analyzer(agent: str) -> Analyzer:
    """`AGENT_LLM` 값으로 분석기를 고른다. 실행마다 새로 만든다. claude는 T16에서 붙인다."""
    # scripted가 이 모듈의 RunContext를 쓰므로 여기서 불러온다
    from app.agent.scripted import ScriptedAnalyzer

    return ScriptedAnalyzer()


def execute(ctx: RunContext, rec: Recorder) -> AnalysisOutput:
    analyzer = select_analyzer(ctx.agent)
    out = AnalysisOutput()
    steps = {
        "EXTRACTING": analyzer.extract,
        "COMPARING": analyzer.compare,
        "DRAFTING": analyzer.draft,
    }
    for stage, _label in STAGES:
        ctx.check_deadline()
        rec.stage(stage)
        steps[stage](ctx, rec, out)
    ctx.check_deadline()
    return out
