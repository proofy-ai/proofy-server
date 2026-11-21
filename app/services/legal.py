"""법령 안내(계약 4.2.1). **코드 상수**이고 문구의 정본은 이 파일이다.

`quote`는 `docs/legal/`의 현행 원문 스냅샷(11/22 받음)에서 그대로 발췌한다. 떨어진 두 곳은
` … `로 잇는다. 테스트가 조각마다 원문에 있는지 확인한다(원칙 3, 지어낸 인용 금지).

사건을 보고 판정하지 않는다(원칙 1). 입금 유형은 항목을 고르고 "보통 쓰는 사유" 표시만 바꾼다.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.schemas.checklist import SourceRef
from app.schemas.common import InflowType
from app.schemas.legal import LegalGuideItem, LegalGuideStage

QUOTE_JOIN = " … "

DISCLAIMER = (
    "이 안내는 법 조항을 쉬운 말로 옮긴 것입니다. "
    "내 경우가 어느 사유에 해당하는지는 은행이 판단합니다."
)

LAW_URL = "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=290245"
DECREE_URL = "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=290281"
LAW_EFFECTIVE = date(2026, 10, 2)
DECREE_EFFECTIVE = date(2026, 10, 1)

# 원문 스냅샷 파일(`docs/legal/`). 테스트가 quote 대조에 쓴다
SnapshotDoc = Literal["law", "decree", "form"]
SNAPSHOT_FILES: dict[SnapshotDoc, str] = {
    "law": "law_20261002.txt",
    "decree": "decree_20261001.txt",
    "form": "form4_20260929.txt",
}

ALL_TYPES: tuple[InflowType, ...] = ("SALARY", "GOODS", "UNEXPECTED", "OTHER")


@dataclass(frozen=True)
class LegalGuide:
    code: str
    stage: LegalGuideStage
    title: str
    plain: str
    quote: str
    doc: SnapshotDoc
    source_label: str
    inflow_types: tuple[InflowType, ...] = ALL_TYPES
    # 이 유형에서 "보통" 쓰는 이의제기 사유. 판정이 아니다
    common_for: tuple[InflowType, ...] = ()

    @property
    def quote_parts(self) -> list[str]:
        return self.quote.split(QUOTE_JOIN)

    def to_schema(self, inflow_type: InflowType) -> LegalGuideItem:
        is_law = self.doc == "law"
        return LegalGuideItem(
            code=self.code,
            stage=self.stage,
            title=self.title,
            plain=self.plain,
            quote=self.quote,
            common_for_type=inflow_type in self.common_for,
            source_ref=SourceRef(label=self.source_label, url=LAW_URL if is_law else DECREE_URL),
            effective_date=LAW_EFFECTIVE if is_law else DECREE_EFFECTIVE,
        )


GUIDES: tuple[LegalGuide, ...] = (
    LegalGuide(
        code="WHAT_HAPPENED",
        stage="SITUATION",
        title="무슨 일이 일어났나요",
        plain=(
            "누군가 이 계좌로 사기 피해금이 들어왔다고 신고하는 등의 일이 있으면, 은행은 사기에 "
            "쓰인 계좌로 의심될 때 바로 계좌 전체의 돈을 못 빼게 막습니다(지급정지). "
            "내 이름으로 된 전자금융거래가 제한될 수도 있습니다."
        ),
        quote=(
            "금융회사등은 다음 각 호의 어느 하나에 해당하는 경우 거래내역 등의 확인을 통하여 "
            "전기통신금융사기의 사기이용계좌등으로 의심할 만한 사정이 있다고 인정되면 즉시 해당 "
            "사기이용계좌등의 전부에 대하여 지급정지 조치를 하여야 한다."
        ),
        doc="law",
        source_label="통신사기피해환급법 제4조제1항",
    ),
    LegalGuide(
        code="DEADLINE",
        stage="SITUATION",
        title="이의제기 기한: 공고일부터 2개월",
        plain=(
            "기한은 통지받은 날이 아니라 금융감독원 공고일을 기준으로 2개월입니다. "
            "이 기간이 지나면 묶인 돈에 대한 권리가 사라집니다."
        ),
        quote=(
            "제5조제2항에 따른 공고일을 기준으로 2개월이 경과하기 전까지 금융회사등에 지급정지, "
            "전자금융거래등의 제한 및 채권소멸절차에 대하여 이의를 제기할 수 있다."
            + QUOTE_JOIN
            + "최초의 채권소멸절차 개시의 공고일부터 2개월이 경과하면 소멸한다."
        ),
        doc="law",
        source_label="통신사기피해환급법 제7조제1항, 제9조제1항",
    ),
    LegalGuide(
        code="REASON_1",
        stage="SITUATION",
        title="사유 1. 사기에 쓰인 계좌가 아님",
        plain="이 계좌가 사기에 쓰인 계좌가 아니라는 것을 설명하는 경우입니다.",
        quote="해당 계좌등이 사기이용계좌등이 아니라는 사실을 소명하는 경우",
        doc="law",
        source_label="통신사기피해환급법 제7조제1항제1호",
    ),
    LegalGuide(
        code="REASON_2",
        stage="SITUATION",
        title="사유 2. 정당하게 받은 돈",
        plain=(
            "묶인 돈이 물건·서비스를 주고 받은 대가이거나 급여처럼 정당하게 받은 돈이라는 것을 "
            "객관적인 자료로 보여 주는 경우입니다. 계좌가 사기에 쓰이는 줄 알았거나, 크게 "
            "부주의해서 몰랐다고 인정되면 이 사유는 받아들여지지 않습니다."
        ),
        quote=(
            "제9조에 따라 소멸될 채권의 전부 또는 일부를 명의인이 재화 또는 용역의 공급에 대한 "
            "대가로 받았거나 그 밖에 정당한 권원에 의하여 취득한 것임을 객관적인 자료로 소명하는 "
            "경우. 다만, 해당 계좌등이 전기통신금융사기에 이용된 사실을 사기이용계좌등으로 이용된 "
            "경위, 거래행태, 거래내역 등의 확인을 통하여 명의인이 알았거나 중대한 과실로 알지 "
            "못하였다고 인정되는 경우에는 그러하지 아니하다."
        ),
        doc="law",
        source_label="통신사기피해환급법 제7조제1항제2호",
        common_for=("SALARY", "GOODS"),
    ),
    LegalGuide(
        code="REASON_3",
        stage="SITUATION",
        title="사유 3. 피해금을 빼돌리는 데 쓰인 계좌가 아님",
        plain=(
            "이 계좌가 피해자의 돈을 빼돌리는 데 쓰이지 않았다는 것을 객관적인 자료로 보여 주는 "
            "경우입니다. 이 사유가 받아들여지면 계좌의 돈 가운데 피해금을 뺀 나머지가 풀립니다."
        ),
        quote=(
            "해당 계좌등이 피해자산 편취를 위하여 이용된 계좌등이 아니라는 사실을 객관적인 자료로 "
            "소명하는 경우"
            + QUOTE_JOIN
            + "같은 항 제3호에 따른 이의제기가 있는 경우에는 해당 사기이용계좌등에 "
            "예치된 금액등 중 전기통신금융사기 피해자산을 제외한 금액등으로 한정한다."
        ),
        doc="law",
        source_label="통신사기피해환급법 제7조제1항제3호, 제8조제1항제2호",
        common_for=("UNEXPECTED",),
    ),
    LegalGuide(
        code="DONT_PAY_THREAT",
        stage="SITUATION",
        title="\"돈을 보내면 풀어 주겠다\"는 연락에 응하지 마세요",
        plain=(
            "피해구제를 신청한 사람이 신청을 모두 취소하면 지급정지가 끝나는 것은 맞습니다. "
            "하지만 \"돈을 보내면 신고를 취소해 주겠다\"는 연락에 응해 돈을 보내지 마세요. "
            "그 연락은 지우지 말고 캡처해 두고, 은행과 경찰(112)에 알리세요."
        ),
        quote="피해구제를 신청한 모든 피해자가 그 신청을 취소하는 경우",
        doc="decree",
        source_label="통신사기피해환급법 시행령 제8조제1항제1호",
        inflow_types=("UNEXPECTED",),
    ),
    LegalGuide(
        code="HOW_TO_SUBMIT",
        stage="SUBMIT",
        title="어디에 무엇을 내나요",
        plain=(
            "계좌가 있는 은행에 이의제기신청서와 함께 ① 사기에 쓰인 계좌가 아니라는 것을 보여 "
            "주는 자료 ② 신분증 사본을 냅니다."
        ),
        quote=(
            "별지 제4호서식의 이의제기신청서에 다음 각 호의 서류를 첨부하여 사기이용계좌등을 "
            "관리하는 금융회사등에 제출해야 한다."
            + QUOTE_JOIN
            + "사기이용계좌등이 아니라는 사실을 증명하는 자료"
            + QUOTE_JOIN
            + "사기이용계좌등 명의인의 신분증 사본"
        ),
        doc="decree",
        source_label="통신사기피해환급법 시행령 제7조",
    ),
    LegalGuide(
        code="REASON_FIELD",
        stage="SUBMIT",
        title="신청서의 \"이의제기 사유\" 칸",
        plain=(
            "이의제기신청서에는 \"이의제기 사유\" 칸이 있고, 구체적으로 적어야 합니다. "
            "Proofy가 만든 소명서 초안을 확인한 뒤 이 칸에 옮겨 적을 수 있습니다."
        ),
        quote="이의제기 사유(구체적으로 기재합니다)",
        doc="form",
        source_label="통신사기피해환급법 시행령 별지 제4호서식",
    ),
    LegalGuide(
        code="HOLD_TWO_MONTHS",
        stage="SUBMIT",
        title="이의제기해도 바로 풀리지 않을 수 있어요",
        plain=(
            "이의제기를 해도, 피해자가 이의제기 사실을 통보받은 날부터 2개월 동안은 계좌가 묶여 "
            "있을 수 있습니다. 객관적인 자료로 충분히 보여 주면 그 전에 풀릴 수도 있습니다."
        ),
        quote=(
            "제7조제2항에 따라 명의인의 이의제기 사실을 피해자가 통보받은 날부터 2개월이 경과하기 "
            "전. 다만, 명의인이 제7조제1항 각 호의 어느 하나에 해당함을 객관적인 자료로 충분히 "
            "소명하고 이에 상당한 이유가 있다고 인정되는 경우에는 지급정지를 해제할 수 있다."
        ),
        doc="law",
        source_label="통신사기피해환급법 제8조제2항제2호",
    ),
)


def legal_guides_for(inflow_type: InflowType) -> list[LegalGuide]:
    return [g for g in GUIDES if inflow_type in g.inflow_types]
