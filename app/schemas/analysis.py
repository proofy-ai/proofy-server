"""분석 실행 요청·응답(계약 4.9·4.10)."""

from typing import Literal

from pydantic import Field, StrictBool

from app.schemas.case import MAX_NARRATIVE
from app.schemas.common import CamelModel, UtcDatetime

RunStatus = Literal["RUNNING", "SUCCEEDED", "FAILED"]
StageStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED"]


class AnswerIn(CamelModel):
    """질문에 단 답(계약 v0.8 4.9). 길이·질문 확인은 서비스가 해서 오류 칸을 `answers`로 모은다."""

    question_id: str
    answer: str


class AnalysisStart(CamelModel):
    # 있으면 먼저 저장한 뒤 사전 조건을 검사한다(계약 4.9)
    narrative: str | None = Field(default=None, max_length=MAX_NARRATIVE)
    overwrite_edited_draft: StrictBool = False
    # 결과 화면 질문의 답(T25). 답을 쓴 질문만 보낸다
    answers: list[AnswerIn] | None = None


class AnalysisStarted(CamelModel):
    run_id: str
    status: RunStatus
    stage: str


class StageOut(CamelModel):
    key: str
    label: str
    status: StageStatus


class StepOut(CamelModel):
    seq: int
    type: str
    title: str
    summary: str | None
    status: str
    # 저장할 때 이미 ISO 8601 UTC 문자열로 만든다
    at: str


class RunError(CamelModel):
    code: str
    message: str


class AnalysisRunOut(CamelModel):
    run_id: str
    status: RunStatus
    stage: str
    stages: list[StageOut]
    steps: list[StepOut]
    error: RunError | None
    started_at: UtcDatetime
    finished_at: UtcDatetime | None
