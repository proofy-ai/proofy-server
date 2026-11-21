"""가짜 분석기(`AGENT_LLM=scripted`, 계약 7절). Claude를 부르지 않는다.

사건의 입금 유형으로 시나리오를 골라 정해 둔 대조 결과를 낸다
(샘플이 아닌 사건도 FE 연동에 쓸 수 있게).
근거는 그 사건에 올린 서류 중 `docType`이 맞는 첫 서류에 붙이고, 없으면 그 근거를 뺀다.
고정값은 계약 4.11(GOODS)·4.3.1(UNEXPECTED) 예시와 같고, 합성 서류(T12)도 이 값에 맞춰 만든다.
"""

import re
import time
from datetime import date, timedelta

from app.agent.output import (
    AnalysisOutput,
    Conflict,
    DraftSentence,
    Finding,
    RecommendedDoc,
    Source,
    TransactionRow,
)
from app.agent.runner import EvidenceRef, RunContext
from app.agent.steps import Recorder

YEAR = 2026
STATEMENT_ONLY_NOTE = "사연에만 있고 이를 보여 주는 자료가 없습니다."

DOC_TYPE_LABELS = {
    "NOTICE": "지급정지 통지서",
    "TRANSACTION_RECORD": "거래내역서",
    "INSURANCE_ELIGIBILITY": "건강보험 자격득실 확인서",
    "EMPLOYMENT_CERT": "재직증명서",
    "PAYSLIP": "급여명세서",
    "BUSINESS_REG": "사업자등록증명",
    "CHAT": "대화내역",
    "CONTRACT": "계약서",
    "TAX_INVOICE": "세금계산서",
    "TRANSACTION_STATEMENT": "거래명세서",
    "SHIPPING": "택배 발송 기록",
    "OTHER": "기타 서류",
}

# (key, 날짜, 방향, 금액, 상대방). 거래내역서 줄 순서대로
_Row = tuple[str, date, str, int, str | None]

GOODS_ROWS: tuple[_Row, ...] = (
    ("t1", date(YEAR, 11, 3), "IN", 32_000, "박*진"),
    ("t2", date(YEAR, 11, 8), "IN", 150_000, "김*수"),
    ("t3", date(YEAR, 11, 10), "OUT", 45_000, None),
)
UNEXPECTED_ROWS: tuple[_Row, ...] = (
    ("t1", date(YEAR, 11, 9), "OUT", 23_000, None),
    ("t2", date(YEAR, 11, 12), "IN", 100_000, "이*호"),
)

# 서류 속 인용 문구와 그 줄 번호(위에서 0부터).
# 합성 서류(`scripts/make_samples.py`)도 이 값으로 만든다
GOODS_CHAT_QUOTE = "3개 12만원에 할게요"
GOODS_CHAT_REGION = 12
THREAT_QUOTE = "20만 원 보내면 신고 취하해 줄게"
THREAT_REGION = 3


def _first(ctx: RunContext, doc_type: str) -> EvidenceRef | None:
    return next((e for e in ctx.evidence if e.doc_type == doc_type), None)


def _won(amount: int) -> str:
    return f"{amount:,}원"


def _md(d: date) -> str:
    return f"{d.month}/{d.day}"


class ScriptedAnalyzer:
    """한 실행에 하나씩 만든다."""

    def extract(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None:
        self._pause(ctx)
        # 가짜 분석은 마스킹 전이라 사연을 그대로 대조 기준으로 쓴다(T14가 마스킹본으로 바꾼다)
        out.masked_narrative = ctx.narrative
        for e in ctx.evidence:
            label = DOC_TYPE_LABELS.get(e.doc_type, "서류")
            rec.step("OCR", f"{e.original_name} 읽기", f"{label}의 글자를 읽었습니다.")
        rows = {"GOODS": GOODS_ROWS, "UNEXPECTED": UNEXPECTED_ROWS}.get(ctx.inflow_type, ())
        record = _first(ctx, "TRANSACTION_RECORD")
        if record is None:
            return
        for i, (key, day, direction, amount, who) in enumerate(rows):
            sign = "입금" if direction == "IN" else "출금"
            out.transactions.append(
                TransactionRow(
                    key=key,
                    evidence_id=record.evidence_id,
                    region_index=i,
                    direction=direction,  # type: ignore[arg-type]
                    amount_krw=amount,
                    occurred_at=day,
                    counterparty_masked=who,
                    raw_text=f"{day.isoformat()} {sign} {amount:,} {who or ''}".strip(),
                )
            )

    def compare(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None:
        self._pause(ctx)
        if ctx.inflow_type == "GOODS":
            self._goods(ctx, rec, out)
        elif ctx.inflow_type == "UNEXPECTED":
            self._unexpected(ctx, rec, out)
        else:
            self._statement_only(ctx, out)
        counts = {s: sum(1 for f in out.findings if f.status == s) for s in _STATUS_WORDS}
        summary = " · ".join(f"{_STATUS_WORDS[s]} {n}" for s, n in counts.items() if n)
        rec.step("FINDING", f"사연 속 주장 {len(out.findings)}개 대조", f"{summary}입니다.")
        for f in out.findings:
            if f.conflict is not None:
                rec.step("CONFLICT", "자료와 어긋나는 내용", f.note)

    def draft(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None:
        self._pause(ctx)
        if ctx.inflow_type == "GOODS":
            sentences = _goods_draft()
        elif ctx.inflow_type == "UNEXPECTED":
            sentences = _unexpected_draft()
        else:
            sentences = _statement_only_draft(out)
        out.draft_sentences += sentences
        rec.step("DRAFT", "소명서 초안", f"초안 문장 {len(sentences)}개를 작성했습니다.")

    @staticmethod
    def _pause(ctx: RunContext) -> None:
        # 4번 화면에서 단계가 넘어가는 것이 보이게(계약 7절)
        if ctx.stage_delay_seconds > 0:
            time.sleep(ctx.stage_delay_seconds)

    @staticmethod
    def _query(
        rec: Recorder,
        out: AnalysisOutput,
        reason: str,
        direction: str,
        start: date,
        end: date,
    ) -> list[TransactionRow]:
        """거래 행 조회 흉내. 조회 이유와 건수를 step `TOOL_CALL`에 남긴다."""
        found = [
            t
            for t in out.transactions
            if t.direction == direction and start <= t.occurred_at <= end
        ]
        sign = "입금" if direction == "IN" else "출금"
        rec.step(
            "TOOL_CALL",
            "거래내역 조회",
            f"{reason} {_md(start)}~{_md(end)} {sign}을 조회 → {len(found)}건",
        )
        return found

    def _goods(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None:
        deposits = self._query(
            rec,
            out,
            "사연의 11월 8일 대금 입금을 확인하려고",
            "IN",
            date(YEAR, 11, 1),
            date(YEAR, 11, 10),
        )
        paid = next((t for t in deposits if t.amount_krw == 150_000), None)
        chat = _first(ctx, "CHAT")

        f1_sources = [Source("NARRATIVE", quote="11월 8일 대금을 계좌로 받았습니다")]
        if paid is not None:
            f1_sources.append(Source("TRANSACTION", transaction_key=paid.key))
        f2_sources = []
        if chat is not None:
            f2_sources.append(
                Source(
                    "EVIDENCE",
                    quote=GOODS_CHAT_QUOTE,
                    evidence_id=chat.evidence_id,
                    page=1,
                    region_index=GOODS_CHAT_REGION,
                )
            )
        out.findings += [
            Finding(
                claim="11월 8일 거래처에서 15만 원을 입금받았다",
                status="MATCH",
                note="거래내역서의 입금 행과 금액·날짜가 같습니다.",
                sources=tuple(f1_sources),
            ),
            Finding(
                claim="가죽 지갑 3개를 15만 원에 납품하기로 했다",
                status="CONFLICT",
                note="대화내역의 합의 금액(120,000원)이 사연·입금액(150,000원)과 다릅니다.",
                conflict=Conflict("AMOUNT", _won(150_000), _won(120_000)),
                sources=tuple(f2_sources),
            ),
            Finding(
                claim="물건을 다음 날 택배로 보냈다",
                status="STATEMENT_ONLY",
                note=STATEMENT_ONLY_NOTE,
                sources=(Source("NARRATIVE", quote="물건은 다음 날 택배로 보냈습니다"),),
            ),
        ]
        out.recommended.append(
            RecommendedDoc(
                label="택배 발송 기록(송장 번호 화면)",
                note="사연에 '다음 날 택배로 보냈다'고 했지만 이를 보여 주는 자료가 없습니다.",
                accepted_doc_types=("SHIPPING",),
            )
        )

    def _unexpected(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None:
        deposits = self._query(
            rec,
            out,
            "사연의 11월 11일 입금을 확인하려고",
            "IN",
            date(YEAR, 11, 8),
            date(YEAR, 11, 14),
        )
        deposit = next((t for t in deposits if t.amount_krw == 100_000), None)
        withdrawals: list[TransactionRow] = []
        if deposit is not None:
            start = deposit.occurred_at
            withdrawals = self._query(
                rec,
                out,
                "입금 뒤 돈이 빠져나갔는지 확인하려고",
                "OUT",
                start,
                start + timedelta(days=6),
            )
        threat = _first(ctx, "CHAT")

        u1_sources = [
            Source("NARRATIVE", quote="모르는 사람이 11월 11일 제 계좌로 10만 원을 보냈습니다")
        ]
        u2_sources = [Source("NARRATIVE", quote="받은 돈은 쓰지 않고 그대로 두었습니다")]
        if deposit is not None:
            u1_sources.append(Source("TRANSACTION", transaction_key=deposit.key))
            if not withdrawals:
                u2_sources.append(Source("TRANSACTION", transaction_key=deposit.key))
        u3_sources = []
        if threat is not None:
            u3_sources.append(
                Source(
                    "EVIDENCE",
                    quote=THREAT_QUOTE,
                    evidence_id=threat.evidence_id,
                    page=1,
                    region_index=THREAT_REGION,
                )
            )
        u3_sources.append(
            Source("NARRATIVE", quote="'20만 원 보내면 신고 취하해 줄게'라는 연락이 왔습니다")
        )
        out.findings += [
            Finding(
                claim="11월 11일 모르는 사람에게서 10만 원이 입금됐다",
                status="CONFLICT",
                note="사연의 입금일(11월 11일)과 거래내역서의 입금일(11월 12일)이 다릅니다.",
                conflict=Conflict("DATE", "11월 11일", "11월 12일"),
                sources=tuple(u1_sources),
            ),
            Finding(
                claim="받은 돈은 쓰지 않고 그대로 두었다",
                status="MATCH",
                note="입금 뒤 이 금액이 빠져나간 거래가 없습니다.",
                sources=tuple(u2_sources),
            ),
            Finding(
                claim="'20만 원 보내면 신고 취하해 줄게'라는 문자를 받았다",
                status="MATCH",
                note="협박 문자 캡처에 같은 내용이 있습니다.",
                sources=tuple(u3_sources),
            ),
            Finding(
                claim="바로 은행에 알렸다",
                status="STATEMENT_ONLY",
                note="사연에만 있고 신고 기록이 없습니다. 탭 B의 피해 신고 기록을 확인해 주세요.",
                sources=(Source("NARRATIVE", quote="바로 은행에 알렸습니다"),),
            ),
        ]

    @staticmethod
    def _statement_only(ctx: RunContext, out: AnalysisOutput) -> None:
        """급여·기타: 사연 첫 문장을 진술만 있는 주장 하나로."""
        first = re.split(r"(?<=[.!?])\s+", ctx.narrative.strip(), maxsplit=1)[0]
        sentence = first.rstrip(".!? ")[:100]
        out.findings.append(
            Finding(
                claim=sentence,
                status="STATEMENT_ONLY",
                note=STATEMENT_ONLY_NOTE,
                sources=(Source("NARRATIVE", quote=sentence),),
            )
        )


def _goods_draft() -> list[DraftSentence]:
    """계약 4.12 예시. 번호는 `_goods`의 대조 항목 순서(0 일치, 1 어긋남, 2 진술만).

    "150,000원" 문장은 어긋난 항목(1)을 일부러 연결하지 않는다.
    서버가 진술 값을 보고 붙인다(규칙 2).
    """
    return [
        DraftSentence(
            "DEPOSIT_REASON",
            "본인은 온라인 쇼핑몰을 운영하는 개인사업자로, 2026년 11월 8일 거래처에 가죽 지갑 "
            f"3개를 납품하고 그 대금 {_won(150_000)}을 입금받았습니다.",
            (0,),
        ),
        DraftSentence("DEPOSIT_REASON", "판매한 물건은 다음 날 택배로 발송하였습니다.", (2,)),
        DraftSentence(
            "NO_INVOLVEMENT",
            "본인은 이 대금이 범죄와 관련된 돈이라는 사실을 알지 못했으며, "
            "물건을 판 대가로 받았습니다.",
        ),
    ]


def _unexpected_draft() -> list[DraftSentence]:
    """번호는 `_unexpected`의 대조 항목 순서.

    0 입금일 어긋남, 1 그대로 둠, 2 협박 문자, 3 은행에 알림.
    """
    return [
        DraftSentence(
            "DEPOSIT_REASON",
            f"2026년 11월 11일 본인이 알지 못하는 사람이 본인 계좌로 {_won(100_000)}을 보냈습니다.",
            (0,),
        ),
        DraftSentence("DEPOSIT_REASON", "입금된 돈은 쓰지 않고 그대로 두었습니다.", (1,)),
        DraftSentence(
            "NO_INVOLVEMENT",
            "본인은 돈을 보낸 사람을 알지 못하며, 이 입금이 어떤 돈인지 알지 못했습니다.",
        ),
        DraftSentence(
            "VICTIM_CONTEXT",
            "이후 '20만 원 보내면 신고 취하해 줄게'라는 문자를 받았으며, 그 문자 화면을 함께 "
            "제출합니다.",
            (2,),
        ),
        DraftSentence("VICTIM_CONTEXT", "이 사실을 바로 은행에 알렸습니다.", (3,)),
    ]


def _statement_only_draft(out: AnalysisOutput) -> list[DraftSentence]:
    """급여·기타: 사연 첫 문장(진술만 있는 주장)과 가담하지 않았다는 본인 진술."""
    sentences = []
    if out.findings:
        sentences.append(DraftSentence("DEPOSIT_REASON", f"{out.findings[0].claim}.", (0,)))
    sentences.append(
        DraftSentence(
            "NO_INVOLVEMENT", "본인은 이 입금이 범죄와 관련된 돈이라는 사실을 알지 못했습니다."
        )
    )
    return sentences


_STATUS_WORDS = {
    "MATCH": "일치",
    "CONFLICT": "어긋남",
    "STATEMENT_ONLY": "진술만",
    "UNKNOWN": "확인 못 함",
}
