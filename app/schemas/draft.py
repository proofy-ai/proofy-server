"""소명서 초안(계약 4.12). 판정 필드는 두지 않는다(CLAUDE.md 원칙 1)."""

from typing import Literal

from pydantic import Field, StrictBool, StrictInt

from app.schemas.common import CamelModel, UtcDatetime

DraftSection = Literal["DEPOSIT_REASON", "NO_INVOLVEMENT", "VICTIM_CONTEXT"]
# 계약 2절 순서. 여러 사유가 겹치면 앞의 것 하나만 준다
NeedsCheckReason = Literal[
    "CONFLICT",
    "NO_SOURCE",
    "QUOTE_NOT_FOUND",
    "NUMBER_MISMATCH",
    "JUDGMENT_EXPRESSION",
    "SOURCE_UNREAD",
]

MAX_SENTENCE_LENGTH = 1000
MAX_SENTENCES = 100


class DraftSentenceOut(CamelModel):
    sentence_id: str
    # 사용자가 더한 문장은 null
    section: DraftSection | None
    text: str
    origin: Literal["AI", "USER"]
    finding_ids: list[str]
    needs_check: bool
    needs_check_reason: NeedsCheckReason | None
    confirmed: bool
    edited: bool


class DraftWarning(CamelModel):
    code: Literal["CONFLICT_NOT_IN_DRAFT"]
    finding_id: str
    message: str


class DraftOut(CamelModel):
    version: int
    based_on_run_id: str
    sentences: list[DraftSentenceOut]
    warnings: list[DraftWarning]
    unconfirmed_count: int
    full_text: str
    updated_at: UtcDatetime


class DraftResponse(CamelModel):
    draft: DraftOut


class DraftSentenceIn(CamelModel):
    # null이면 새 문장
    sentence_id: str | None = None
    text: str = Field(max_length=MAX_SENTENCE_LENGTH)
    # 생략하면 기존 값 유지(글이 바뀐 문장은 false, 계약 4.12)
    confirmed: StrictBool | None = None


class DraftPut(CamelModel):
    expected_version: StrictInt
    sentences: list[DraftSentenceIn] = Field(max_length=MAX_SENTENCES)
