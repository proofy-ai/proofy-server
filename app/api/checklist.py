"""사건 체크리스트 API(계약 4.8). 업무 로직은 `app/services/checklist.py`에 있다."""

from fastapi import APIRouter

from app.db import DbSession
from app.schemas.checklist import ChecklistItemEnvelope, ChecklistPatch, ChecklistResponse
from app.services import checklist as checklist_service
from app.services.auth import AuthorizedCase

router = APIRouter(tags=["checklist"])


@router.get("/cases/{case_id}/checklist", response_model=ChecklistResponse)
def get_checklist(case: AuthorizedCase, db: DbSession) -> ChecklistResponse:
    return checklist_service.get_checklist(db, case)


@router.patch("/cases/{case_id}/checklist/{item_id}", response_model=ChecklistItemEnvelope)
def patch_checklist_item(
    item_id: str, patch: ChecklistPatch, case: AuthorizedCase, db: DbSession
) -> ChecklistItemEnvelope:
    item = checklist_service.set_checked(db, case, item_id, patch.checked)
    return ChecklistItemEnvelope(item=item)
