"""체험 계정(샘플 사건, 계약 4.3.1·6절).

- 통지일·공고일만 오늘 기준 상대 날짜다. 입금일과 사연·서류 속 날짜는 고정이다(서류가 고정 파일이라
  입금일까지 바꾸면 사연·서류와 어긋난다, 계약 v0.6.3).
- 서류 파일은 `app/samples/`에 있고, 사건마다 복사본을 증빙으로 넣는다. 파일은 합성 서류로
  `scripts/make_samples.py`가 만든다(T12). 내용은 가짜 분석기 값과 같다.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Case
from app.schemas.case import CaseCreate, InflowIn
from app.schemas.common import DocType, InflowType
from app.schemas.sample import SampleFile, SampleSet, SamplesResponse
from app.services.cases import stage_case
from app.services.evidence import detect_mime, stage_evidence

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "samples"

NOTICE_RECEIVED_DAYS_AGO = 6
PUBLIC_NOTICE_DAYS_AGO = 4


@dataclass(frozen=True)
class SampleDocument:
    file_name: str
    display_name: str
    doc_type: DocType


@dataclass(frozen=True)
class Scenario:
    key: str
    inflow_type: InflowType
    amount_krw: int
    # 사용자가 말한 입금일(사연과 같음). 고정
    occurred_at: date
    narrative: str
    documents: tuple[SampleDocument, ...]


SCENARIOS: dict[str, Scenario] = {
    # test01: 청년 1인 온라인 판매 사업자. 대화 속 합의 금액(12만 원)과 입금액(15만 원)이 다르다
    "GOODS": Scenario(
        key="goods",
        inflow_type="GOODS",
        amount_krw=150_000,
        occurred_at=date(2026, 11, 8),
        narrative=(
            "온라인 쇼핑몰을 운영하는 개인사업자입니다. 거래처 소매점에 가죽 지갑 3개를 15만 원에 "
            "납품하기로 하고 11월 8일 대금을 계좌로 받았습니다. 물건은 다음 날 택배로 보냈습니다."
        ),
        documents=(
            SampleDocument("transaction_record.pdf", "거래내역서_샘플.pdf", "TRANSACTION_RECORD"),
            SampleDocument("chat.png", "대화내역_샘플.png", "CHAT"),
            SampleDocument("business_reg.png", "사업자등록증명_샘플.png", "BUSINESS_REG"),
        ),
    ),
    # test02: 모르는 입금(통장 묶기). 사연의 입금일(11/11)과 거래내역(11/12)이 다르다
    "UNEXPECTED": Scenario(
        key="unexpected",
        inflow_type="UNEXPECTED",
        amount_krw=100_000,
        occurred_at=date(2026, 11, 11),
        narrative=(
            "모르는 사람이 11월 11일 제 계좌로 10만 원을 보냈습니다. 며칠 뒤 계좌가 지급정지됐다는 "
            "통지를 받았고, 문자로 '20만 원 보내면 신고 취하해 줄게'라는 연락이 왔습니다. "
            "저는 보낸 사람을 모르고, 받은 돈은 쓰지 않고 그대로 두었습니다. "
            "바로 은행에 알렸습니다."
        ),
        documents=(
            SampleDocument("transaction_record.pdf", "거래내역서_샘플.pdf", "TRANSACTION_RECORD"),
            SampleDocument("threat_message.png", "협박문자_샘플.png", "CHAT"),
        ),
    ),
}


def _scenario(name: str) -> Scenario:
    scenario = SCENARIOS.get(name)
    if scenario is None:
        # SALARY는 P1(계약 4.3.1)
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "아직 준비되지 않은 샘플입니다.",
            {"fields": {"scenario": "GOODS 또는 UNEXPECTED만 쓸 수 있습니다."}},
        )
    return scenario


def create_sample_case(db: Session, name: str, today: date) -> tuple[Case, str]:
    """서류가 채워진 샘플 사건을 만들고 (사건, 토큰 원문)을 돌려준다."""
    scenario = _scenario(name)
    payload = CaseCreate(
        notice_received_date=today - timedelta(days=NOTICE_RECEIVED_DAYS_AGO),
        public_notice_date=today - timedelta(days=PUBLIC_NOTICE_DAYS_AGO),
        inflow=InflowIn(
            type=scenario.inflow_type,
            amount_krw=scenario.amount_krw,
            occurred_at=scenario.occurred_at,
        ),
        has_prior_freeze=False,
    )
    case, token = stage_case(db, payload, narrative=scenario.narrative)
    case.is_sample = True
    case.sample_scenario = name
    for doc in scenario.documents:
        data = (SAMPLE_DIR / scenario.key / doc.file_name).read_bytes()
        mime = detect_mime(data)
        if mime is None:
            raise RuntimeError(f"샘플 파일 형식을 알 수 없음: {scenario.key}/{doc.file_name}")
        stage_evidence(db, case.id, doc.doc_type, doc.display_name, mime, data, is_sample=True)
    # 만든 직후 값. 지금 값과 같으면 "샘플 그대로"(AI 실패 시 미리 만든 결과, T11)
    case.sample_input_version = case.input_version
    db.commit()
    return case, token


def list_samples() -> SamplesResponse:
    return SamplesResponse(
        items=[
            SampleSet(
                scenario=name,
                files=[
                    SampleFile(
                        name=doc.display_name,
                        doc_type=doc.doc_type,
                        url=f"/api/v1/samples/{scenario.key}/{doc.file_name}",
                    )
                    for doc in scenario.documents
                ],
            )
            for name, scenario in SCENARIOS.items()
        ]
    )


def sample_file(scenario_key: str, file_name: str) -> tuple[Path, str]:
    """(파일 경로, 형식). 시나리오에 정의된 파일만 내준다(경로 조작 불가)."""
    for scenario in SCENARIOS.values():
        if scenario.key != scenario_key:
            continue
        for doc in scenario.documents:
            if doc.file_name == file_name:
                path = SAMPLE_DIR / scenario.key / doc.file_name
                mime = detect_mime(path.read_bytes()[:16]) or "application/octet-stream"
                return path, mime
    raise ApiError(404, "NOT_FOUND", "샘플 파일을 찾을 수 없습니다.")
