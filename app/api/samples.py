"""샘플 체험 API(계약 4.3.1). 업무 로직은 `app/services/samples.py`에 있다."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.db import DbSession
from app.schemas.case import CaseCreated
from app.schemas.sample import SampleCaseCreate, SamplesResponse
from app.services import cases as case_service
from app.services import samples as sample_service
from app.services.deadline import today_kst

router = APIRouter(tags=["samples"])


@router.post("/cases/sample", status_code=201, response_model=CaseCreated)
def create_sample_case(payload: SampleCaseCreate, db: DbSession) -> CaseCreated:
    today = today_kst()
    case, token = sample_service.create_sample_case(db, payload.scenario, today)
    return CaseCreated(
        case_id=case.id, case_token=token, case=case_service.to_case_out(db, case, today)
    )


@router.get("/samples", response_model=SamplesResponse)
def list_samples() -> SamplesResponse:
    return sample_service.list_samples()


@router.get("/samples/{scenario_key}/{file_name}")
def download_sample(scenario_key: str, file_name: str) -> FileResponse:
    path, mime = sample_service.sample_file(scenario_key, file_name)
    # FE가 미리보기로 띄울 수 있게 inline(브라우저에서 바로 열림)
    return FileResponse(
        path, media_type=mime, filename=file_name, content_disposition_type="inline"
    )
