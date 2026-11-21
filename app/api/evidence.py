"""증빙 API(계약 4.7). 업무 로직은 `app/services/evidence.py`에 있다."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile

from app.db import DbSession
from app.schemas.common import DocType
from app.schemas.evidence import EvidenceEnvelope, EvidenceList
from app.services import evidence as evidence_service
from app.services.auth import AuthorizedCase

router = APIRouter(tags=["evidence"])


@router.post("/cases/{case_id}/evidence", status_code=201, response_model=EvidenceEnvelope)
def upload_evidence(
    case: AuthorizedCase,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[DocType, Form(alias="docType")],
) -> EvidenceEnvelope:
    evidence = evidence_service.add_evidence(db, case, doc_type, file.filename, file.file)
    return EvidenceEnvelope(evidence=evidence_service.to_evidence_out(evidence))


@router.get("/cases/{case_id}/evidence", response_model=EvidenceList)
def list_evidence(case: AuthorizedCase, db: DbSession) -> EvidenceList:
    items = evidence_service.list_evidence(db, case.id)
    return EvidenceList(items=[evidence_service.to_evidence_out(e) for e in items])


@router.delete("/cases/{case_id}/evidence/{evidence_id}", status_code=204)
def delete_evidence(evidence_id: str, case: AuthorizedCase, db: DbSession) -> Response:
    evidence_service.delete_evidence(db, case, evidence_id)
    return Response(status_code=204)
