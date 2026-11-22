"""분석기가 내는 결과 모양. 가짜 분석기(T08)와 Claude 분석기(T16)가 같은 모양을 낸다.

분석기는 DB를 만지지 않고 이 모양만 채운다. 저장·검증(같은 사건 소속, 인용 대조)은
`app/services/results.py`가 한다. 거래 행은 저장 전이라 ID가 없으므로 `key`로 가리킨다.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.agent.extract import Extraction
from app.agent.masking import MaskedText

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
    확인 필요 여부는 분석기가 정하지 않는다(`app/services/drafts.py`).
    """

    section: DraftSection
    text: str
    finding_indexes: tuple[int, ...] = ()


@dataclass
class AnalysisOutput:
    """세 단계가 차례로 채운다."""

    # AI가 본 사연(마스킹본, runner가 ① 단계 전에 채움). 인용 대조 기준
    masked_narrative: MaskedText | None = None
    transactions: list[TransactionRow] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    recommended: list[RecommendedDoc] = field(default_factory=list)
    draft_sentences: list[DraftSentence] = field(default_factory=list)
    # 서류별로 읽은 글자(evidenceId → 추출 결과). ① 단계가 채우고 runner가 줄마다 `maskedText`를
    # 붙인다(T14). 저장은 그때 이미 끝났다. AI에는 `maskedText`만 보낸다
    extractions: dict[str, Extraction] = field(default_factory=dict)
    # 외부 AI를 부른 실행만 채운다(T16). 비용 기록용(`analysis_runs.model`, `usage_events`)
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_micro_usd: int | None = None
