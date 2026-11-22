"""분석기가 내는 결과 모양. 가짜 분석기(T08)와 Claude 분석기(T16)가 같은 모양을 낸다.

분석기는 DB를 만지지 않고 이 모양만 채운다. 저장·검증(같은 사건 소속, 인용 대조)은
`app/services/results.py`가 한다. 거래 행은 저장 전이라 ID가 없으므로 `key`로 가리킨다.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.agent.extract import Extraction
from app.agent.masking import MaskedText, join_masked

FindingStatus = Literal["MATCH", "CONFLICT", "STATEMENT_ONLY", "UNKNOWN"]
ConflictField = Literal["AMOUNT", "DATE", "COUNTERPARTY", "OTHER"]
SourceKind = Literal["NARRATIVE", "EVIDENCE", "TRANSACTION"]
# 초안 묶음(계약 2절 `DraftSection`). 이 순서대로 쓴다
DraftSection = Literal["DEPOSIT_REASON", "NO_INVOLVEMENT", "VICTIM_CONTEXT"]

# 한 실행당 AI 권장 항목 상한(계약 4.8)
MAX_RECOMMENDED = 3


@dataclass(frozen=True)
class TransactionRow:
    """거래내역서에서 뽑은 거래 행(ERD 3.4)."""

    key: str
    evidence_id: str
    region_index: int
    direction: Literal["IN", "OUT"]
    amount_krw: int
    occurred_at: date
    counterparty_masked: str | None
    raw_text: str


@dataclass(frozen=True)
class Conflict:
    field: ConflictField
    statement: str
    found: str


@dataclass(frozen=True)
class Source:
    kind: SourceKind
    quote: str | None = None
    evidence_id: str | None = None
    page: int | None = None
    region_index: int | None = None
    transaction_key: str | None = None


@dataclass(frozen=True)
class Finding:
    claim: str
    status: FindingStatus
    # 화면 문장. FE 타입이 null을 받지 않아 항상 채운다
    note: str
    conflict: Conflict | None = None
    sources: tuple[Source, ...] = ()


@dataclass(frozen=True)
class RecommendedDoc:
    label: str
    note: str
    accepted_doc_types: tuple[str, ...]


@dataclass(frozen=True)
class DraftSentence:
    """초안 문장. 근거는 `AnalysisOutput.findings`의 번호(0부터)로만 가리킨다.

    서버가 번호를 이 실행의 대조 항목 ID로 바꾸고, 없는 번호는 버린다(원칙 3).
    확인 필요 여부는 서버가 정한다(`app/services/drafts.py`). 분석기는 검사 사유만 넘긴다.
    """

    section: DraftSection
    text: str
    finding_indexes: tuple[int, ...] = ()
    # 분석기 후검증(T17)이 남긴 사유. `NUMBER_MISMATCH`·`JUDGMENT_EXPRESSION`만.
    # 최종 확인 필요 여부와 사유 순서는 서버가 정한다(`app/services/drafts.py`)
    check_reason: str | None = None


LawSource = Literal["LAW", "DECREE", "FORM4"]

# 한 실행당 의견·질문 상한(계약 4.11)
MAX_OPINIONS = 3
MAX_QUESTIONS = 3


@dataclass(frozen=True)
class LawRef:
    """근거 조항(T23·T24). `label`·`verified`는 서버가 원문과 대조해 붙인다(`agent/law.py`)."""

    ref: str
    source: LawSource
    label: str
    quote: str
    verified: bool


@dataclass(frozen=True)
class Opinion:
    """AI 조건부 의견(T24). 근거는 대조 항목 번호와 법령 조항으로만. 초안에는 넣지 않는다."""

    text: str
    finding_indexes: tuple[int, ...] = ()
    law_refs: tuple[LawRef, ...] = ()
    # 서버 검사 사유: LAW_QUOTE_NOT_FOUND · JUDGMENT_EXPRESSION · NUMBER_MISMATCH. 있으면 확인 필요
    check_reason: str | None = None


@dataclass(frozen=True)
class Question:
    """AI 질문(T24). 사용자가 답하면 다음 분석에 넘긴다(T25)."""

    text: str
    why: str
    finding_indexes: tuple[int, ...] = ()
    law_refs: tuple[LawRef, ...] = ()


@dataclass(frozen=True)
class MaskedAnswer:
    """사용자가 답한 질문과 답(T25). runner가 사건 이름 목록으로 가린 글."""

    question: MaskedText
    answer: MaskedText


@dataclass
class AnalysisOutput:
    """세 단계가 차례로 채운다."""

    # AI가 본 사연(마스킹본, runner가 ① 단계 전에 채움). 인용 대조 기준
    masked_narrative: MaskedText | None = None
    # 지금까지 답한 질문·답(T25, 답한 순서). runner가 가린다. 에이전트 첫 메시지와 인용 대조에 쓴다
    masked_answers: list[MaskedAnswer] = field(default_factory=list)
    # 지난 성공 분석 성찰(T25, agent-design-v2 4.6). runner가 가린 첫 메시지용 자료. 첫 분석은 None
    masked_previous: dict[str, Any] | None = None
    # 표현 목록이 찾은 상담 안내 표현(T10)을 가린 글. 에이전트 첫 메시지 `checkPhrases`
    masked_check_phrases: list[MaskedText] = field(default_factory=list)
    # 상담 안내로 끝나면 화면에 보일 확인된 표현(`matchedPhrases`). 이때 대조·의견·초안은 없다
    referral: tuple[str, ...] | None = None
    transactions: list[TransactionRow] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    recommended: list[RecommendedDoc] = field(default_factory=list)
    draft_sentences: list[DraftSentence] = field(default_factory=list)
    # AI 의견·질문(T24, 계약 4.11 `agentReview`). 번호는 `findings` 순서(0부터)
    opinions: list[Opinion] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    # 서류별로 읽은 글자(evidenceId → 추출 결과). ① 단계가 채우고 runner가 줄마다 `maskedText`를
    # 붙인다(T14). 저장은 그때 이미 끝났다. AI에는 `maskedText`만 보낸다
    extractions: dict[str, Extraction] = field(default_factory=dict)
    # 외부 AI를 부른 실행만 채운다(T16). 비용 기록용(`analysis_runs.model`, `usage_events`)
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_micro_usd: int | None = None

    def quote_basis(self) -> MaskedText | None:
        """사연 인용(`NARRATIVE`)을 대조할 글: 가린 사연 + 가린 질문·답(T25).

        답은 사용자 진술이라 사연과 같이 `NARRATIVE` 근거로 인용할 수 있다(계약 4.9).
        """
        if self.masked_narrative is None:
            return None
        parts = [self.masked_narrative]
        for a in self.masked_answers:
            parts += [a.question, a.answer]
        return join_masked(parts, "\n\n")
