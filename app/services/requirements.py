"""유형별 서류 목록. **코드 상수**이고 정본은 `docs/contract.md` 4.2(출처 포함)다.

계약 4.2에 문구가 없는 항목의 `note`는 `None`이다. 사건 상황에 맞춘 안내는 분석 후
AI 권장 항목이 맡는다(계약 v0.6.2).
"""

from dataclasses import dataclass

from app.schemas.checklist import ChecklistCategory, ChecklistStatus, RequirementItem, SourceRef
from app.schemas.common import DocType, InflowType

LAW_DECREE_7 = SourceRef(
    label="통신사기피해환급법 시행령 제7조",
    url="https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=290281",
)
HANKOOK_2026_05_03 = SourceRef(
    label="한국일보 2026.5.3",
    url="https://www.hankookilbo.com/news/article/A2026050313580002729",
)
FSC_2024_02_01 = SourceRef(
    label="금융위원회 보도참고 2024.2.1",
    url="https://www.fsc.go.kr/no010101/81640",
)
YGLAW_GUIDE = SourceRef(
    label="법률사무소 안내 글(공식 자료 아님)",
    url="https://www.yglaw.co.kr/bbs/board.php?bo_table=lawinfo&wr_id=27",
)


@dataclass(frozen=True)
class Requirement:
    code: str
    label: str
    category: ChecklistCategory
    accepted_doc_types: tuple[DocType, ...]
    required_for_analysis: bool = False
    note: str | None = None
    source_ref: SourceRef | None = None
    # 올릴 수 없는 항목의 상태(올릴 수 있는 항목은 None, 올린 서류로 계산)
    fixed_status: ChecklistStatus | None = None

    @property
    def uploadable(self) -> bool:
        return self.fixed_status is None

    def to_schema(self) -> RequirementItem:
        return RequirementItem(
            code=self.code,
            label=self.label,
            category=self.category,
            accepted_doc_types=list(self.accepted_doc_types),
            uploadable=self.uploadable,
            required_for_analysis=self.required_for_analysis,
            note=self.note,
            source_ref=self.source_ref,
        )


OBJECTION_FORM = Requirement(
    code="OBJECTION_FORM",
    label="이의제기신청서(별지 제4호서식)",
    category="OFFICIAL_REQUIRED",
    accepted_doc_types=(),
    note="은행 창구·양식으로 작성합니다. 소명서 초안의 사유를 옮겨 적을 수 있습니다.",
    source_ref=LAW_DECREE_7,
    fixed_status="GUIDE_ONLY",
)
ID_COPY = Requirement(
    code="ID_COPY",
    label="신분증 사본",
    category="OFFICIAL_REQUIRED",
    accepted_doc_types=(),
    note="이 서비스는 신분증을 받지 않습니다. 은행에 낼 때 직접 첨부하세요.",
    source_ref=LAW_DECREE_7,
    fixed_status="NOT_COLLECTED",
)
NOTICE = Requirement(
    code="NOTICE",
    label="지급정지 통지서",
    category="OPTIONAL",
    accepted_doc_types=("NOTICE",),
    note="통지일·공고일을 확인하는 데 씁니다.",
)
DEPOSIT_RECORD = Requirement(
    code="DEPOSIT_RECORD",
    label="문제된 입금이 보이는 거래내역서",
    category="ANALYSIS_INPUT",
    accepted_doc_types=("TRANSACTION_RECORD",),
    required_for_analysis=True,
)

_BY_TYPE: dict[str, tuple[Requirement, ...]] = {
    "SALARY": (
        Requirement(
            code="SALARY_DEPOSIT",
            label="급여 입금내역",
            category="TYPE_GUIDE",
            accepted_doc_types=("TRANSACTION_RECORD",),
            required_for_analysis=True,
            note="문제된 입금이 보이는 거래내역서(은행 앱 캡처 또는 PDF)",
            source_ref=HANKOOK_2026_05_03,
        ),
        Requirement(
            code="EMPLOYMENT_PROOF",
            label="건강보험자격득실확인서 또는 재직증명서 중 하나",
            category="TYPE_GUIDE",
            accepted_doc_types=("INSURANCE_ELIGIBILITY", "EMPLOYMENT_CERT"),
            source_ref=HANKOOK_2026_05_03,
        ),
    ),
    # 물품 거래는 사업자(개인사업자 포함)의 판매 대금을 전제로 한다(계약 4.2)
    "GOODS": (
        Requirement(
            code="BUSINESS_REG",
            label="사업자등록",
            category="TYPE_GUIDE",
            accepted_doc_types=("BUSINESS_REG",),
            source_ref=HANKOOK_2026_05_03,
        ),
        Requirement(
            code="COUNTERPARTY_CHAT",
            label="거래상대방과의 대화내역",
            category="TYPE_GUIDE",
            accepted_doc_types=("CHAT",),
            source_ref=HANKOOK_2026_05_03,
        ),
        Requirement(
            code="TRADE_DOCUMENT",
            label="계약서, 세금계산서, 거래명세서 중 하나",
            category="TYPE_GUIDE",
            accepted_doc_types=("CONTRACT", "TAX_INVOICE", "TRANSACTION_STATEMENT"),
            source_ref=HANKOOK_2026_05_03,
        ),
        DEPOSIT_RECORD,
    ),
    # 모르는 입금(통장 묶기). 사기범이 입금 후 허위 신고로 계좌를 묶고 해제 대가를 요구하는 경우
    "UNEXPECTED": (
        Requirement(
            code="THREAT_MESSAGE",
            label="해제 대가를 요구하는 협박 문자·메시지",
            category="TYPE_GUIDE",
            accepted_doc_types=("CHAT",),
            note=(
                "협박 문자가 없으면 이의제기가 받아들여지기 어렵다는 보도가 있습니다. "
                "받은 메시지는 지우지 말고 캡처해 두세요."
            ),
            source_ref=FSC_2024_02_01,
        ),
        Requirement(
            code="UNKNOWN_DEPOSIT_RECORD",
            label="모르는 입금이 보이는 거래내역서",
            category="ANALYSIS_INPUT",
            accepted_doc_types=("TRANSACTION_RECORD",),
            required_for_analysis=True,
        ),
        # 새 DocType 없이 OTHER로 받는다(계약 v0.5)
        Requirement(
            code="INCIDENT_REPORT",
            label="경찰·은행에 신고한 기록(사건사고사실확인원, 신고 접수증 등)",
            category="OPTIONAL",
            accepted_doc_types=("OTHER",),
            note=(
                "내가 피해를 입었다는 것을 보여 주는 기록입니다. "
                "신고했다면 접수증이나 사건사고사실확인원을 받아 두세요."
            ),
            source_ref=YGLAW_GUIDE,
        ),
    ),
    # 화면에 없는 값. 분석 시작 조건 때문에 거래내역서만 더한다(계약 v0.6.2)
    "OTHER": (DEPOSIT_RECORD,),
}

_CATEGORY_ORDER: dict[str, int] = {
    "OFFICIAL_REQUIRED": 0,
    "TYPE_GUIDE": 1,
    "ANALYSIS_INPUT": 2,
    "OPTIONAL": 3,
}


def requirements_for(inflow_type: InflowType) -> list[Requirement]:
    """공통 항목 + 유형별 항목. 묶음 순서대로, 묶음 안은 공통 항목 먼저, 그다음 계약 표 순서."""
    items = [OBJECTION_FORM, ID_COPY, NOTICE, *_BY_TYPE[inflow_type]]
    return sorted(items, key=lambda r: _CATEGORY_ORDER[r.category])
