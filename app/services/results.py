"""분석 결과 저장과 결과 응답(계약 4.11, ERD 3.4·3.6·3.7·3.8).

- 저장: 분석기 출력(`AnalysisOutput`)을 실행에 붙인다. 근거는 **이 사건의 증빙과 이번 실행의
  거래 행**에만 연결하고, 어긋나면 근거를 빼고 로그를 남긴다(CLAUDE.md 원칙 3).
  인용 대조(`verified`)도 여기서 코드가 한다.
- 조회: 가장 최근 성공 실행 것만 준다. 이전 실행의 행은 지우지 않고 조회에서 거른다(ERD 4절).
"""

import logging
import re
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.output import MAX_RECOMMENDED, AnalysisOutput, Finding
from app.errors import ApiError
from app.models import (
    AnalysisRun,
    Case,
    ChecklistItemRow,
    ClaimFinding,
    Evidence,
    FindingSource,
    Transaction,
)
from app.schemas.result import (
    AI_NOTICE,
    EvidenceSource,
    FindingConflict,
    FindingOut,
    FindingSourceOut,
    NarrativeSource,
    ResultResponse,
    ResultSummary,
    TransactionSource,
    UnreadEvidence,
)
from app.services.checklist import get_checklist
from app.services.clock import utc_now
from app.services.deadline import compute_deadline
from app.services.runs import latest_succeeded_run

logger = logging.getLogger("proofy.results")

STATUSES = ("MATCH", "CONFLICT", "STATEMENT_ONLY", "UNKNOWN")
UNKNOWN_NOTE = "자료에서 이 내용을 확인하지 못했습니다."
UNREAD_REASON = "글자를 읽지 못했습니다. 원본을 직접 확인해 주세요."
_SPACE = re.compile(r"\s+")


def _squash(text: str) -> str:
    return _SPACE.sub("", text)


def quote_found(quote: str | None, text: str | None) -> bool:
    """인용이 대조 글에 공백을 무시하고 들어 있나(ERD 3.7 검증 3)."""
    if not quote or not text:
        return False
    return _squash(quote) in _squash(text)


def save_output(db: Session, run: AnalysisRun, out: AnalysisOutput) -> None:
    """출력을 세션에 넣는다(커밋은 부르는 쪽이 실행 마무리와 함께 한다).

    모델 사이에 relationship이 없어 INSERT 순서가 FK를 따르지 않으므로, 참조되는 행부터 flush 한다.
    """
    run.masked_narrative = out.masked_narrative
    evidence = {
        e.id: e for e in db.scalars(select(Evidence).where(Evidence.case_id == run.case_id))
    }
    now = utc_now()

    tx_ids: dict[str, str] = {}
    for row in out.transactions:
        if row.evidence_id not in evidence:
            logger.warning("실행 %s: 다른 사건의 서류에서 나온 거래 행을 뺌", run.id)
            continue
        tx_id = str(uuid.uuid4())
        tx_ids[row.key] = tx_id
        db.add(
            Transaction(
                id=tx_id,
                case_id=run.case_id,
                evidence_id=row.evidence_id,
                analysis_run_id=run.id,
                source="STATEMENT",
                region_index=row.region_index,
                direction=row.direction,
                amount_krw=row.amount_krw,
                occurred_at=row.occurred_at,
                counterparty_masked=row.counterparty_masked,
                raw_text=row.raw_text,
                created_at=now,
            )
        )

    db.flush()
    for seq, finding in enumerate(out.findings, start=1):
        _add_finding(db, run, seq, finding, evidence, tx_ids)

    for doc in out.recommended[:MAX_RECOMMENDED]:
        db.add(
            ChecklistItemRow(
                id=str(uuid.uuid4()),
                case_id=run.case_id,
                analysis_run_id=run.id,
                code=None,
                category="AI_RECOMMENDED",
                label=doc.label,
                note=doc.note,
                accepted_doc_types_json=list(doc.accepted_doc_types),
                checked=False,
                created_at=now,
            )
        )


def _add_finding(
    db: Session,
    run: AnalysisRun,
    seq: int,
    finding: Finding,
    evidence: dict[str, Evidence],
    tx_ids: dict[str, str],
) -> None:
    finding_id = str(uuid.uuid4())
    sources: list[FindingSource] = []
    for source in finding.sources:
        row = FindingSource(
            id=str(uuid.uuid4()),
            finding_id=finding_id,
            source_kind=source.kind,
            quoted_text=source.quote,
        )
        if source.kind == "NARRATIVE":
            row.is_verified = quote_found(source.quote, run.masked_narrative)
        elif source.kind == "EVIDENCE":
            doc = evidence.get(source.evidence_id or "")
            if doc is None or source.page is None or source.region_index is None:
                logger.warning("실행 %s: 이 사건에 없는 서류 근거를 뺌", run.id)
                continue
            row.evidence_id = doc.id
            row.page = source.page
            row.region_index = source.region_index
            if doc.masked_text is not None:
                row.is_verified = quote_found(source.quote, doc.masked_text)
            else:
                # 글자 추출(T13) 전에는 대조할 원문이 없다. 가짜 분석의 고정 인용만 통과시킨다
                row.is_verified = run.agent == "scripted"
        else:
            tx_id = tx_ids.get(source.transaction_key or "")
            if tx_id is None:
                logger.warning("실행 %s: 이번 실행의 거래 행이 아닌 근거를 뺌", run.id)
                continue
            row.transaction_id = tx_id
            row.is_verified = True
        row.seq = len(sources) + 1
        sources.append(row)

    status, note, conflict = finding.status, finding.note, finding.conflict
    has_material = any(s.source_kind != "NARRATIVE" for s in sources)
    if status in ("MATCH", "CONFLICT") and not has_material:
        # 자료 근거가 하나도 남지 않은 일치·어긋남은 "확인 못 함"(agent-design 2.4)
        status, note, conflict = "UNKNOWN", UNKNOWN_NOTE, None

    db.add(
        ClaimFinding(
            id=finding_id,
            analysis_run_id=run.id,
            seq=seq,
            claim_text=finding.claim,
            status=status,
            note=note,
            conflict_json=(
                {"field": conflict.field, "statement": conflict.statement, "found": conflict.found}
                if conflict
                else None
            ),
        )
    )
    db.flush()
    db.add_all(sources)


def _source_out(
    source: FindingSource,
    evidence: dict[str, Evidence],
    transactions: dict[str, Transaction],
) -> FindingSourceOut | None:
    if source.source_kind == "NARRATIVE":
        return NarrativeSource(quote=source.quoted_text or "", verified=source.is_verified)
    if source.source_kind == "EVIDENCE":
        doc = evidence.get(source.evidence_id or "")
        if doc is None:
            return None
        return EvidenceSource(
            evidence_id=doc.id,
            doc_type=doc.doc_type,
            original_name=doc.original_name,
            page=source.page or 1,
            region_index=source.region_index or 0,
            quote=source.quoted_text or "",
            verified=source.is_verified,
        )
    tx = transactions.get(source.transaction_id or "")
    if tx is None:
        return None
    return TransactionSource(
        transaction_id=tx.id,
        evidence_id=tx.evidence_id,
        occurred_at=tx.occurred_at,
        direction=tx.direction,
        amount_krw=tx.amount_krw,
        counterparty=tx.counterparty_masked,
        verified=source.is_verified,
    )


def list_findings(db: Session, run: AnalysisRun) -> list[FindingOut]:
    findings = db.scalars(
        select(ClaimFinding)
        .where(ClaimFinding.analysis_run_id == run.id)
        .order_by(ClaimFinding.seq)
    ).all()
    if not findings:
        return []
    sources = db.scalars(
        select(FindingSource)
        .where(FindingSource.finding_id.in_([f.id for f in findings]))
        .order_by(FindingSource.finding_id, FindingSource.seq)
    ).all()
    # 같은 사건 것만 읽는다(사건 간 근거 교차 차단)
    evidence = {
        e.id: e for e in db.scalars(select(Evidence).where(Evidence.case_id == run.case_id))
    }
    transactions = {
        t.id: t
        for t in db.scalars(
            select(Transaction).where(
                Transaction.analysis_run_id == run.id, Transaction.case_id == run.case_id
            )
        )
    }
    by_finding: dict[str, list[FindingSourceOut]] = {f.id: [] for f in findings}
    for source in sources:
        out = _source_out(source, evidence, transactions)
        if out is not None:
            by_finding[source.finding_id].append(out)
    return [
        FindingOut(
            finding_id=f.id,
            claim=f.claim_text,
            status=f.status,
            note=f.note or "",
            conflict=FindingConflict(**f.conflict_json) if f.conflict_json else None,
            sources=by_finding[f.id],
        )
        for f in findings
    ]


def get_result(db: Session, case: Case, today: date) -> ResultResponse:
    run = latest_succeeded_run(db, case.id)
    if run is None:
        raise ApiError(404, "NOT_FOUND", "분석 결과가 없습니다.")
    findings = list_findings(db, run)
    checklist = get_checklist(db, case)
    unread = [
        UnreadEvidence(evidence_id=e.id, original_name=e.original_name, reason=UNREAD_REASON)
        for e in db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id, Evidence.extract_status == "FAILED")
            .order_by(Evidence.created_at)
        )
    ]
    counts = {s: 0 for s in STATUSES}
    for f in findings:
        counts[f.status] += 1
    return ResultResponse(
        run_id=run.id,
        based_on_input_version=run.based_on_input_version,
        is_stale=case.input_version != run.based_on_input_version,
        generated_at=run.finished_at or run.started_at,
        precomputed=run.precomputed,
        referral=None,
        ai_notice=AI_NOTICE,
        deadline=compute_deadline(case.public_notice_date, today),
        findings=findings,
        checklist=checklist,
        draft=None,
        unread_evidence=unread,
        summary=ResultSummary(
            finding_counts=counts,
            missing_documents=checklist.missing_count,
            # 초안(T09)이 채운다
            sentences_needing_check=0,
            unread_evidence=len(unread),
        ),
    )
