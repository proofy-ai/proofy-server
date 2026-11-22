"""분석 결과(계약 4.11). 판정 필드(해제 가능성, 수용 여부 등)는 두지 않는다(CLAUDE.md 원칙 1)."""

from datetime import date
from typing import Literal

from app.schemas.checklist import ChecklistResponse
from app.schemas.common import CamelModel, DocType, UtcDatetime
from app.schemas.deadline import Deadline
from app.schemas.draft import DraftOut

FindingStatus = Literal["MATCH", "CONFLICT", "STATEMENT_ONLY", "UNKNOWN"]
ConflictField = Literal["AMOUNT", "DATE", "COUNTERPARTY", "OTHER"]

AI_NOTICE = (
    "AI가 올린 자료를 정리한 결과입니다. 해제 여부를 판단하지 않으며, "
    "은행 심사 결과와 다를 수 있습니다."
)


class NarrativeSource(CamelModel):
    kind: Literal["NARRATIVE"] = "NARRATIVE"
    quote: str
    verified: bool


class EvidenceSource(CamelModel):
    kind: Literal["EVIDENCE"] = "EVIDENCE"
    evidence_id: str
    doc_type: DocType
    original_name: str
    page: int
    region_index: int
    quote: str
    verified: bool


class TransactionSource(CamelModel):
    kind: Literal["TRANSACTION"] = "TRANSACTION"
    transaction_id: str
    evidence_id: str
    occurred_at: date
    direction: Literal["IN", "OUT"]
    amount_krw: int
    # 가린 이름(김*수)
    counterparty: str | None
    verified: bool


FindingSourceOut = NarrativeSource | EvidenceSource | TransactionSource


class FindingConflict(CamelModel):
    field: ConflictField
    statement: str
    found: str


class FindingOut(CamelModel):
    finding_id: str
    claim: str
    status: FindingStatus
    note: str
    conflict: FindingConflict | None
    sources: list[FindingSourceOut]


class UnreadEvidence(CamelModel):
    evidence_id: str
    original_name: str
    reason: str


LawSource = Literal["LAW", "DECREE", "FORM4"]

AGENT_REVIEW_NOTICE = (
    "올린 자료와 말씀하신 내용을 기준으로 AI가 정리한 의견입니다. "
    "Proofy는 변호사가 아니며, 지급정지 해제 여부는 은행이 판단합니다."
)


class LawRefOut(CamelModel):
    """근거 조항(계약 4.11). `label`·`verified`는 서버가 법령 원문과 대조해 붙인다."""

    source: LawSource
    label: str
    quote: str
    verified: bool


class AgentOpinion(CamelModel):
    opinion_id: str
    text: str
    finding_ids: list[str]
    law_refs: list[LawRefOut]
    needs_check: bool


class AgentQuestion(CamelModel):
    question_id: str
    text: str
    why: str
    finding_ids: list[str]
    law_refs: list[LawRefOut]


class AnsweredQuestion(CamelModel):
    question_id: str
    text: str
    answer: str
    answered_at: UtcDatetime


class AgentReview(CamelModel):
    """AI 조건부 의견·질문(계약 v0.8 4.11). 판정 필드(해제 가능성 등)는 없다."""

    notice: str
    opinions: list[AgentOpinion]
    questions: list[AgentQuestion]
    answered: list[AnsweredQuestion]


class ReferralContact(CamelModel):
    name: str
    phone: str


class Referral(CamelModel):
    """상담 안내(T10, 계약 4.11). 판정이 아니라 상담이 먼저 필요해 보이는 표현을 알린다."""

    code: Literal["LEGAL_CONSULT"]
    # 서버가 사연·답 원문에 있다고 확인한 글자
    matched_phrases: list[str]
    message: str
    contacts: list[ReferralContact]


class ResultSummary(CamelModel):
    finding_counts: dict[FindingStatus, int]
    missing_documents: int
    sentences_needing_check: int
    unread_evidence: int


class ResultResponse(CamelModel):
    run_id: str
    based_on_input_version: int
    is_stale: bool
    generated_at: UtcDatetime
    precomputed: bool
    # 상담 안내(T10). 보통 null. 있으면 findings 빈 목록, draft null, summary 모두 0
    referral: Referral | None
    # AI 의견·질문(T24). 의견·질문·답한 기록이 모두 없으면 null(v0.8 전 결과 포함)
    agent_review: AgentReview | None
    ai_notice: str
    deadline: Deadline
    findings: list[FindingOut]
    checklist: ChecklistResponse
    # 초안(4.12와 같은 모양). 상담 안내로 끝난 실행은 null
    draft: DraftOut | None
    unread_evidence: list[UnreadEvidence]
    summary: ResultSummary
