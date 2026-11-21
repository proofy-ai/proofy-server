"""사건 체크리스트(계약 4.8). 충족 여부는 올린 서류의 `docType`으로 코드가 계산한다(원칙 2)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Case, ChecklistItemRow
from app.schemas.checklist import ChecklistItem, ChecklistResponse, ChecklistStatus
from app.services.clock import utc_now
from app.services.requirements import Requirement, requirements_for


@dataclass(frozen=True)
class UploadedEvidence:
    evidence_id: str
    doc_type: str


def compute_status(
    requirement: Requirement, evidence: Sequence[UploadedEvidence]
) -> tuple[ChecklistStatus, list[str]]:
    """(상태, 충족한 증빙 ID). `acceptedDocTypes` 중 하나라도 올렸으면 충족이다."""
    if requirement.fixed_status is not None:
        return requirement.fixed_status, []
    satisfied_by = [e.evidence_id for e in evidence if e.doc_type in requirement.accepted_doc_types]
    return ("SATISFIED" if satisfied_by else "MISSING"), satisfied_by


def uploaded_evidence(db: Session, case: Case) -> list[UploadedEvidence]:
    """사건에 올린 서류. 증빙 테이블은 T05에서 생기므로 지금은 빈 목록이다."""
    return []


def sync_items(db: Session, case: Case) -> dict[str, ChecklistItemRow]:
    """현재 입금 유형의 상수 항목과 사건별 행을 맞춘다.

    없는 `code`는 만들고, 유형이 바뀌어 목록에서 빠진 `code`는 지운다. 남은 행은 그대로라
    같은 `code`의 체크 표시가 이어진다(`docs/erd.md` 3.8).
    """
    requirements = requirements_for(case.inflow.inflow_type)
    wanted = {r.code: r for r in requirements}
    rows = db.scalars(
        select(ChecklistItemRow).where(
            ChecklistItemRow.case_id == case.id, ChecklistItemRow.code.is_not(None)
        )
    ).all()

    by_code: dict[str, ChecklistItemRow] = {}
    changed = False
    for row in rows:
        if row.code in wanted:
            by_code[row.code] = row
        else:
            db.delete(row)
            changed = True
    for code, requirement in wanted.items():
        if code not in by_code:
            row = ChecklistItemRow(
                id=str(uuid.uuid4()),
                case_id=case.id,
                code=code,
                category=requirement.category,
                checked=False,
                created_at=utc_now(),
            )
            db.add(row)
            by_code[code] = row
            changed = True
    if changed:
        db.commit()
    return by_code


def _to_item(
    row: ChecklistItemRow, requirement: Requirement, evidence: Sequence[UploadedEvidence]
) -> ChecklistItem:
    status, satisfied_by = compute_status(requirement, evidence)
    return ChecklistItem(
        item_id=row.id,
        code=requirement.code,
        label=requirement.label,
        category=requirement.category,
        status=status,
        accepted_doc_types=list(requirement.accepted_doc_types),
        required_for_analysis=requirement.required_for_analysis,
        satisfied_by=satisfied_by,
        checked=row.checked,
        note=requirement.note,
        source_ref=requirement.source_ref,
    )


def get_checklist(db: Session, case: Case) -> ChecklistResponse:
    rows = sync_items(db, case)
    evidence = uploaded_evidence(db, case)
    # AI 권장 항목(가장 최근 성공 실행 것만, 계약 4.8)은 T08에서 더한다
    items = [_to_item(rows[r.code], r, evidence) for r in requirements_for(case.inflow.inflow_type)]
    missing = sum(1 for i in items if i.status == "MISSING" and not i.checked)
    return ChecklistResponse(items=items, missing_count=missing)


def set_checked(db: Session, case: Case, item_id: str, checked: bool) -> ChecklistItem:
    """ "따로 준비함" 표시. 분석 입력이 아니라 `inputVersion`은 그대로다."""
    rows = sync_items(db, case)
    row = next((r for r in rows.values() if r.id == item_id), None)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "체크리스트 항목을 찾을 수 없습니다.")
    if row.checked != checked:
        row.checked = checked
        db.commit()
    requirement = next(r for r in requirements_for(case.inflow.inflow_type) if r.code == row.code)
    return _to_item(row, requirement, uploaded_evidence(db, case))
