"""답변 받기와 지난 분석 성찰(T25, 계약 v0.8 4.9·4.11, agent-design-v2 4.6).

- 답은 가장 최근 성공 실행의 질문에만 받는다. 앞뒤 공백을 뺀 1~500자. 하나라도 틀리면
  `400 VALIDATION_ERROR`(`details.fields.answers`)이고 아무것도 저장하지 않는다.
- 같은 질문에 다시 답하면 마지막 답만 남는다(같은 요청 안에서도 뒤의 것). 답이 하나라도 있으면
  `input_version` +1(샘플 "그대로" 조건이 깨진다, 계약 4.10).
- 답 원문은 DB에만 두고 AI에는 runner가 가린 뒤에 보낸다(원칙 4).
- 지난 분석 성찰은 새 표 없이 지난 성공 실행의 대조 항목·계획 점검 step·확인 필요 수로 만든다.
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.runner import AnswerPair, PreviousFinding, PreviousRun
from app.errors import ApiError
from app.models import AnalysisOpinion, AnalysisQuestion, Case, ClaimFinding
from app.schemas.analysis import AnswerIn
from app.services.clock import utc_now
from app.services.drafts import current_draft
from app.services.review import answered_questions
from app.services.runs import latest_succeeded_run

MAX_ANSWER = 500
# 한 실행의 질문은 3개까지라 넉넉한 상한
MAX_ANSWERS = 10
# 지난 분석에서 다시 볼 항목(일치는 넘기지 않음)
REVISIT_STATUSES = ("CONFLICT", "UNKNOWN", "STATEMENT_ONLY")


def _invalid(reason: str) -> ApiError:
    details = {"fields": {"answers": reason}}
    return ApiError(400, "VALIDATION_ERROR", "입력값을 확인해 주세요.", details)


def check_answers(db: Session, case: Case, answers: Sequence[AnswerIn]) -> dict[str, str]:
    """답을 검사해 `{questionId: 답}`을 돌려준다(저장 안 함).

    사연 저장보다 먼저 부른다(T25 결정 1).
    """
    if len(answers) > MAX_ANSWERS:
        raise _invalid(f"답은 한 번에 {MAX_ANSWERS}개까지 보낼 수 있습니다.")
    cleaned: dict[str, str] = {}
    for item in answers:
        text = item.answer.strip()
        if not 1 <= len(text) <= MAX_ANSWER:
            raise _invalid(f"답은 1~{MAX_ANSWER}자로 써 주세요.")
        cleaned.pop(item.question_id, None)  # 같은 질문은 뒤의 답이 남고 순서도 뒤로
        cleaned[item.question_id] = text
    if not cleaned:
        return cleaned
    run = latest_succeeded_run(db, case.id)
    allowed = set()
    if run is not None:
        allowed = set(
            db.scalars(
                select(AnalysisQuestion.id).where(
                    AnalysisQuestion.analysis_run_id == run.id,
                    AnalysisQuestion.case_id == case.id,
                )
            )
        )
    if not set(cleaned) <= allowed:
        raise _invalid("지금 결과에 없는 질문입니다. 결과를 새로 불러와 주세요.")
    return cleaned


def save_answers(db: Session, case: Case, answers: dict[str, str]) -> None:
    """검사를 마친 답을 저장한다. 답이 있으면 `input_version` +1."""
    if not answers:
        return
    now = utc_now()
    questions = {
        q.id: q
        for q in db.scalars(select(AnalysisQuestion).where(AnalysisQuestion.id.in_(answers)))
    }
    for question_id, text in answers.items():
        question = questions[question_id]
        question.answer = text
        question.answered_at = now
    case.input_version += 1
    case.updated_at = now
    db.commit()


def answer_pairs(db: Session, case_id: str) -> tuple[AnswerPair, ...]:
    """이 사건에서 지금까지 답한 질문·답 원문(답한 순서). runner가 가린다."""
    return tuple(AnswerPair(q.text, q.answer or "") for q in answered_questions(db, case_id))


def previous_review(db: Session, case: Case) -> PreviousRun | None:
    """가장 최근 성공 실행의 성찰 자료. 성공 실행이 없으면 None(첫 분석)."""
    run = latest_succeeded_run(db, case.id)
    if run is None:
        return None
    findings = tuple(
        PreviousFinding(f.claim_text, f.status, f.note or "")
        for f in db.scalars(
            select(ClaimFinding)
            .where(
                ClaimFinding.analysis_run_id == run.id,
                ClaimFinding.status.in_(REVISIT_STATUSES),
            )
            .order_by(ClaimFinding.seq)
        )
    )
    plan_check = next(
        (
            s.get("summary")
            for s in reversed(run.steps_json or [])
            if s.get("type") == "VERIFY" and s.get("title") == "계획 점검"
        ),
        None,
    )
    draft = current_draft(db, case, run)
    sentences = draft.sentences_json if draft is not None else []
    opinions = db.scalar(
        select(func.count())
        .select_from(AnalysisOpinion)
        .where(AnalysisOpinion.analysis_run_id == run.id, AnalysisOpinion.needs_check.is_(True))
    )
    return PreviousRun(
        findings=findings,
        plan_check=plan_check,
        sentences_needing_check=sum(1 for s in sentences if s.get("needsCheck")),
        opinions_needing_check=opinions or 0,
    )
