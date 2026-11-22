"""소명서 초안 저장·조회·수정(계약 4.12, ERD 3.9).

- 확인 필요 여부는 분석기가 아니라 여기서 코드가 정한다(CLAUDE.md 원칙 1·3).
  1. 연결된 대조 항목 중 `CONFLICT`가 있으면 사유 `CONFLICT`
  2. 문장 속 금액·날짜가 어떤 `CONFLICT` 항목의 진술 값과 같으면 그 항목을 붙이고 1번 적용
  3. 연결된 항목이 없거나 모두 `STATEMENT_ONLY`·`UNKNOWN`이면 사유 `NO_SOURCE`
  4. 연결된 항목에 원문에서 못 찾은 인용이 있으면 사유 `QUOTE_NOT_FOUND`(T17)
  5. 분석기 후검증이 넘긴 사유(`NUMBER_MISMATCH`·`JUDGMENT_EXPRESSION`, T17 `agent/drafting.py`)
  6. 어느 문장에도 연결되지 않은 `CONFLICT` 항목은 `warnings`
  사유가 겹치면 계약 `NeedsCheckReason` 순서대로 앞의 것 하나. `SOURCE_UNREAD`는 쓰지 않는다
  (못 읽은 서류는 근거가 될 수 없다, T16 `agent/verify.py`).
- `findingIds`에는 같은 실행의 대조 항목만 들어간다. 분석기는 번호로만 가리킨다.
- 초안은 가장 최근 성공 실행 것만 보여 준다.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.numbers import amounts, month_days
from app.agent.output import DraftSentence
from app.errors import ApiError
from app.models import AnalysisRun, Case, ClaimFinding, Draft
from app.schemas.draft import DraftOut, DraftPut, DraftSentenceOut, DraftWarning
from app.services.clock import utc_now
from app.services.runs import latest_succeeded_run

logger = logging.getLogger("proofy.drafts")

SECTION_ORDER = ("DEPOSIT_REASON", "NO_INVOLVEMENT", "VICTIM_CONTEXT")
NO_MATERIAL = ("STATEMENT_ONLY", "UNKNOWN")
CONFLICT_NOT_IN_DRAFT = "자료와 어긋난 내용이 초안에 설명되지 않았습니다."
NOT_FOUND_MESSAGE = "초안이 없습니다. 분석을 먼저 해 주세요."

_SPACE = re.compile(r"\s+")
# 분석기가 넘길 수 있는 사유(계약 순서상 인용 못 찾음 뒤)
AGENT_REASONS = ("NUMBER_MISMATCH", "JUDGMENT_EXPRESSION")


@dataclass(frozen=True)
class FindingInfo:
    """저장한 대조 항목(분석기 출력 순서대로)."""

    finding_id: str
    status: str
    conflict: dict[str, Any] | None
    # 근거 인용 중 원문(마스킹본)에서 못 찾은 것이 있나(T17 `QUOTE_NOT_FOUND`)
    quote_missing: bool = False


def mentions_statement(text: str, conflict: dict[str, Any] | None) -> bool:
    """문장에 어긋난 항목의 진술 값이 들어 있나(규칙 2)."""
    if not conflict or not conflict.get("statement"):
        return False
    statement = conflict["statement"]
    if conflict.get("field") == "AMOUNT" and amounts(statement):
        return bool(amounts(statement) & amounts(text))
    if conflict.get("field") == "DATE" and month_days(statement):
        return bool(month_days(statement) & month_days(text))
    return _SPACE.sub("", statement) in _SPACE.sub("", text)


def needs_check(
    finding_ids: list[str],
    statuses: dict[str, str],
    quote_missing: set[str] | None = None,
    agent_reason: str | None = None,
) -> tuple[bool, str | None]:
    linked = [statuses[f] for f in finding_ids if f in statuses]
    if "CONFLICT" in linked:
        return True, "CONFLICT"
    if not linked or all(s in NO_MATERIAL for s in linked):
        return True, "NO_SOURCE"
    if quote_missing and any(f in quote_missing for f in finding_ids):
        return True, "QUOTE_NOT_FOUND"
    if agent_reason in AGENT_REASONS:
        return True, agent_reason
    return False, None


def _warnings(conflict_ids: list[str], sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    linked = {f for s in sentences for f in s["findingIds"]}
    return [
        {"code": "CONFLICT_NOT_IN_DRAFT", "findingId": f, "message": CONFLICT_NOT_IN_DRAFT}
        for f in conflict_ids
        if f not in linked
    ]


def replace_draft(
    db: Session, run: AnalysisRun, sentences: list[DraftSentence], findings: list[FindingInfo]
) -> None:
    """실행의 초안으로 사건의 초안을 바꾼다(커밋은 부르는 쪽). `version`은 이어서 +1."""
    statuses = {f.finding_id: f.status for f in findings}
    quote_missing = {f.finding_id for f in findings if f.quote_missing}
    ordered = sorted(sentences, key=lambda s: SECTION_ORDER.index(s.section))
    rows: list[dict[str, Any]] = []
    for sentence in ordered:
        text = sentence.text.strip()
        if not text:
            continue
        ids: list[str] = []
        for i in sentence.finding_indexes:
            if not 0 <= i < len(findings):
                logger.warning("실행 %s: 없는 대조 항목 번호 %s를 뺌", run.id, i)
                continue
            if findings[i].finding_id not in ids:
                ids.append(findings[i].finding_id)
        for f in findings:
            if f.status == "CONFLICT" and f.finding_id not in ids:
                if mentions_statement(text, f.conflict):
                    ids.append(f.finding_id)
        flag, reason = needs_check(ids, statuses, quote_missing, sentence.check_reason)
        rows.append(
            {
                "sentenceId": str(uuid.uuid4()),
                "section": sentence.section,
                "text": text,
                "origin": "AI",
                "findingIds": ids,
                "needsCheck": flag,
                "needsCheckReason": reason,
                "confirmed": False,
                "edited": False,
            }
        )
    conflict_ids = [f.finding_id for f in findings if f.status == "CONFLICT"]
    warnings = _warnings(conflict_ids, rows)

    now = utc_now()
    draft = db.scalar(select(Draft).where(Draft.case_id == run.case_id))
    if draft is None:
        db.add(
            Draft(
                id=str(uuid.uuid4()),
                case_id=run.case_id,
                based_on_run_id=run.id,
                version=1,
                sentences_json=rows,
                warnings_json=warnings,
                created_at=now,
                updated_at=now,
                edited_at=None,
            )
        )
        return
    # 옛 화면이 들고 있던 버전으로 새 초안을 덮어쓰지 못하게 버전은 되돌리지 않는다
    draft.based_on_run_id = run.id
    draft.version += 1
    draft.sentences_json = rows
    draft.warnings_json = warnings
    draft.created_at = now
    draft.updated_at = now
    draft.edited_at = None


def _full_text(sentences: list[DraftSentenceOut]) -> str:
    """같은 묶음은 공백으로, 묶음이 바뀌면 빈 줄로 잇는다. `null` 묶음은 앞 묶음에 붙는다."""
    out = ""
    current: str | None = None
    for i, s in enumerate(sentences):
        section = s.section or current
        if i > 0:
            out += "\n\n" if section != current else " "
        out += s.text
        current = section
    return out


def to_draft_out(draft: Draft) -> DraftOut:
    sentences = [DraftSentenceOut.model_validate(s) for s in draft.sentences_json]
    return DraftOut(
        version=draft.version,
        based_on_run_id=draft.based_on_run_id,
        sentences=sentences,
        warnings=[DraftWarning.model_validate(w) for w in draft.warnings_json],
        unconfirmed_count=sum(1 for s in sentences if s.needs_check and not s.confirmed),
        full_text=_full_text(sentences),
        updated_at=draft.updated_at,
    )


def current_draft(db: Session, case: Case, run: AnalysisRun | None = None) -> Draft | None:
    """가장 최근 성공 실행의 초안. 없으면 None."""
    run = run or latest_succeeded_run(db, case.id)
    if run is None:
        return None
    draft = db.scalar(select(Draft).where(Draft.case_id == case.id))
    if draft is None or draft.based_on_run_id != run.id:
        return None
    return draft


def _require(db: Session, case: Case) -> Draft:
    draft = current_draft(db, case)
    if draft is None:
        raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
    return draft


def get_draft(db: Session, case: Case) -> DraftOut:
    return to_draft_out(_require(db, case))


def has_user_edits(db: Session, case: Case) -> bool:
    """`PUT`으로 한 번이라도 저장한 초안이 있나(다시 분석 시 `DRAFT_HAS_EDITS`)."""
    draft = db.scalar(select(Draft).where(Draft.case_id == case.id))
    return draft is not None and draft.edited_at is not None


def save_draft(db: Session, case: Case, payload: DraftPut) -> DraftOut:
    draft = _require(db, case)
    if payload.expected_version != draft.version:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "다른 곳에서 초안이 바뀌었습니다. 최신 초안을 다시 불러와 주세요.",
            {"currentVersion": draft.version},
        )

    existing = {s["sentenceId"]: s for s in draft.sentences_json}
    errors: dict[str, str] = {}
    seen: set[str] = set()
    for i, item in enumerate(payload.sentences):
        if not item.text.strip():
            errors[f"sentences.{i}.text"] = (
                "빈 문장은 저장할 수 없습니다. 지우려면 목록에서 빼 주세요."
            )
        if item.sentence_id is None:
            continue
        if item.sentence_id not in existing:
            errors[f"sentences.{i}.sentenceId"] = "이 초안에 없는 문장입니다."
        elif item.sentence_id in seen:
            errors[f"sentences.{i}.sentenceId"] = "같은 문장이 두 번 들어 있습니다."
        seen.add(item.sentence_id)
    if errors:
        raise ApiError(400, "VALIDATION_ERROR", "입력값을 확인해 주세요.", {"fields": errors})

    rows: list[dict[str, Any]] = []
    for item in payload.sentences:
        text = item.text.strip()
        if item.sentence_id is None:
            rows.append(
                {
                    "sentenceId": str(uuid.uuid4()),
                    "section": None,
                    "text": text,
                    "origin": "USER",
                    "findingIds": [],
                    "needsCheck": False,
                    "needsCheckReason": None,
                    "confirmed": item.confirmed is True,
                    "edited": False,
                }
            )
            continue
        row = dict(existing[item.sentence_id])
        if text != row["text"]:
            # 고쳤다고 근거가 생기지는 않는다: findingIds·needsCheck 유지, 확인은 다시
            row["text"] = text
            row["edited"] = True
            row["confirmed"] = item.confirmed is True
        elif item.confirmed is not None:
            row["confirmed"] = item.confirmed
        rows.append(row)

    conflict_ids = list(
        db.scalars(
            select(ClaimFinding.id)
            .where(
                ClaimFinding.analysis_run_id == draft.based_on_run_id,
                ClaimFinding.status == "CONFLICT",
            )
            .order_by(ClaimFinding.seq)
        )
    )
    now = utc_now()
    draft.sentences_json = rows
    draft.warnings_json = _warnings(conflict_ids, rows)
    draft.version += 1
    draft.updated_at = now
    draft.edited_at = now
    db.commit()
    return to_draft_out(draft)
