"""AI 의견·질문 저장과 결과의 `agentReview`(계약 v0.8 4.11, ERD 3.11·3.12, T24).

- 저장: 분석기 출력의 근거 번호(대조 항목 순서)를 **이번 실행의** 대조 항목 ID로 바꾼다.
  없는 번호는 버린다(원칙 3). 조항 인용 대조(`verified`)는 분석기가 법령 원문으로 이미 했다.
- 조회: 의견은 가장 최근 성공 실행 것. 질문은 그 실행의 질문 중 아직 답이 없는 것.
  답한 질문(`answered`)은 사건 단위로 답한 순서(T25).
- 의견·질문·답한 기록이 모두 없으면 `null`(T24 결정 1). v0.8 전에 만든 결과도 `null`이 된다.
"""

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.output import MAX_OPINIONS, MAX_QUESTIONS, AnalysisOutput, LawRef
from app.models import AnalysisOpinion, AnalysisQuestion, AnalysisRun
from app.schemas.result import (
    AGENT_REVIEW_NOTICE,
    AgentOpinion,
    AgentQuestion,
    AgentReview,
    AnsweredQuestion,
    LawRefOut,
)
from app.services.clock import utc_now

logger = logging.getLogger("proofy.review")


def _finding_ids(run: AnalysisRun, indexes: Iterable[int], finding_ids: list[str]) -> list[str]:
    ids: list[str] = []
    for i in indexes:
        if not 0 <= i < len(finding_ids):
            logger.warning("실행 %s: 의견·질문의 없는 대조 항목 번호 %s를 뺌", run.id, i)
            continue
        if finding_ids[i] not in ids:
            ids.append(finding_ids[i])
    return ids


def _law_refs(refs: Iterable[LawRef]) -> list[dict[str, Any]]:
    return [
        {
            "ref": r.ref,
            "source": r.source,
            "label": r.label,
            "quote": r.quote,
            "verified": r.verified,
        }
        for r in refs
    ]


def save_review(db: Session, run: AnalysisRun, out: AnalysisOutput, finding_ids: list[str]) -> None:
    """의견·질문을 세션에 넣는다(커밋은 부르는 쪽).

    `finding_ids`는 `out.findings` 순서의 저장 ID.
    """
    for seq, opinion in enumerate(out.opinions[:MAX_OPINIONS], start=1):
        db.add(
            AnalysisOpinion(
                id=str(uuid.uuid4()),
                analysis_run_id=run.id,
                seq=seq,
                text=opinion.text,
                finding_ids_json=_finding_ids(run, opinion.finding_indexes, finding_ids),
                law_refs_json=_law_refs(opinion.law_refs),
                needs_check=opinion.check_reason is not None,
                check_reason=opinion.check_reason,
            )
        )
    now = utc_now()
    for seq, question in enumerate(out.questions[:MAX_QUESTIONS], start=1):
        db.add(
            AnalysisQuestion(
                id=str(uuid.uuid4()),
                case_id=run.case_id,
                analysis_run_id=run.id,
                seq=seq,
                text=question.text,
                why=question.why,
                finding_ids_json=_finding_ids(run, question.finding_indexes, finding_ids),
                law_refs_json=_law_refs(question.law_refs),
                created_at=now,
            )
        )


def _law_refs_out(raw: list[dict[str, Any]]) -> list[LawRefOut]:
    return [
        LawRefOut(source=r["source"], label=r["label"], quote=r["quote"], verified=r["verified"])
        for r in raw
    ]


def answered_questions(db: Session, case_id: str) -> list[AnalysisQuestion]:
    """이 사건에서 답한 질문, 답한 순서."""
    return list(
        db.scalars(
            select(AnalysisQuestion)
            .where(AnalysisQuestion.case_id == case_id, AnalysisQuestion.answer.is_not(None))
            .order_by(AnalysisQuestion.answered_at, AnalysisQuestion.seq)
        )
    )


def agent_review(db: Session, run: AnalysisRun) -> AgentReview | None:
    opinions = db.scalars(
        select(AnalysisOpinion)
        .where(AnalysisOpinion.analysis_run_id == run.id)
        .order_by(AnalysisOpinion.seq)
    ).all()
    questions = db.scalars(
        select(AnalysisQuestion)
        .where(AnalysisQuestion.analysis_run_id == run.id, AnalysisQuestion.answer.is_(None))
        .order_by(AnalysisQuestion.seq)
    ).all()
    answered = answered_questions(db, run.case_id)
    if not opinions and not questions and not answered:
        return None
    return AgentReview(
        notice=AGENT_REVIEW_NOTICE,
        opinions=[
            AgentOpinion(
                opinion_id=o.id,
                text=o.text,
                finding_ids=list(o.finding_ids_json or []),
                law_refs=_law_refs_out(o.law_refs_json or []),
                needs_check=o.needs_check,
            )
            for o in opinions
        ],
        questions=[
            AgentQuestion(
                question_id=q.id,
                text=q.text,
                why=q.why,
                finding_ids=list(q.finding_ids_json or []),
                law_refs=_law_refs_out(q.law_refs_json or []),
            )
            for q in questions
        ],
        answered=[
            AnsweredQuestion(
                question_id=q.id,
                text=q.text,
                answer=q.answer or "",
                answered_at=q.answered_at or q.created_at,
            )
            for q in answered
        ],
    )
