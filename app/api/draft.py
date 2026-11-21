"""소명서 초안 API(계약 4.12). 업무 로직은 `app/services/drafts.py`에 있다."""

from fastapi import APIRouter

from app.db import DbSession
from app.schemas.draft import DraftPut, DraftResponse
from app.services import drafts as draft_service
from app.services.auth import AuthorizedCase

router = APIRouter(tags=["draft"])


@router.get("/cases/{case_id}/draft", response_model=DraftResponse)
def get_draft(case: AuthorizedCase, db: DbSession) -> DraftResponse:
    return DraftResponse(draft=draft_service.get_draft(db, case))


@router.put("/cases/{case_id}/draft", response_model=DraftResponse)
def put_draft(payload: DraftPut, case: AuthorizedCase, db: DbSession) -> DraftResponse:
    return DraftResponse(draft=draft_service.save_draft(db, case, payload))
