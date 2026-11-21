"""샘플 체험(계약 4.3.1)."""

from typing import Literal

from app.schemas.common import CamelModel, DocType

SampleScenario = Literal["GOODS", "UNEXPECTED", "SALARY"]


class SampleCaseCreate(CamelModel):
    scenario: SampleScenario


class SampleFile(CamelModel):
    name: str
    doc_type: DocType
    # API 주소를 뺀 경로. FE가 API 주소를 앞에 붙인다
    url: str


class SampleSet(CamelModel):
    scenario: SampleScenario
    files: list[SampleFile]


class SamplesResponse(CamelModel):
    items: list[SampleSet]
