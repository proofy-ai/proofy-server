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
    # 상담 안내(T10). 지금은 항상 null
    referral: dict | None
    ai_notice: str
    deadline: Deadline
    findings: list[FindingOut]
    checklist: ChecklistResponse
    # 초안(4.12와 같은 모양). 상담 안내로 끝난 실행은 null
    draft: DraftOut | None
    unread_evidence: list[UnreadEvidence]
    summary: ResultSummary
