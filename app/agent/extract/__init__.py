"""서류 글자 추출(T13). 파일 하나 → `Extraction`.

- 글자가 든 PDF는 OCR 없이 뽑는다(`pdf_text`). 글자가 거의 없는 PDF와 그림은 Tesseract OCR(`ocr`).
- 못 읽어도 예외를 올리지 않고 `FAILED` 결과를 돌려준다. 그 서류만 "직접 확인"으로 넘기고
  분석은 계속한다.
  단, 마감 확인(`check`)이 올린 예외는 그대로 올린다(분석 시간 초과).
- 엔진은 `OcrEngine` 인터페이스라 배포에서 OCR이 막히면 바꿀 수 있다.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent.extract.ocr import OcrEngine, OcrError, count_low_confidence, detect_format
from app.agent.extract.pdf_text import PdfUnreadable, extract_pdf_text
from app.agent.steps import AgentError, RunStopped

log = logging.getLogger("proofy.extract")

ExtractStatus = Literal["READY", "FAILED"]
ExtractMethod = Literal["PDF_TEXT", "OCR"]


@dataclass(frozen=True)
class Extraction:
    status: ExtractStatus
    method: ExtractMethod | None = None
    # 줄 단위 영역 `{index, page, text, bbox, confidence}`(ERD 3.3 `regions_json`).
    # 가린 글 `maskedText`는 runner가 사건 이름 목록으로 붙인다(T14, `app.agent.masking`)
    regions: list[dict[str, Any]] = field(default_factory=list)
    # 흐리게 읽은 줄 수(계약 `lowConfidenceRegions`). 글자가 든 PDF는 0
    low_confidence: int | None = None
    # 못 읽은 이유(200자 이내, 화면 "직접 확인" 안내용)
    error: str | None = None
    # 쪽 상한 때문에 뒷쪽을 읽지 않았는지
    truncated: bool = False

    @property
    def text(self) -> str:
        return "\n".join(r["text"] for r in self.regions)


def _failed(reason: str) -> Extraction:
    return Extraction(status="FAILED", error=reason[:200])


def extract_document(
    content: bytes, engine: OcrEngine, check: Callable[[], None] | None = None
) -> Extraction:
    try:
        kind = detect_format(content)
    except OcrError as exc:
        return _failed(str(exc))

    if kind == "pdf":
        try:
            found = extract_pdf_text(content)
        except PdfUnreadable as exc:
            return _failed(str(exc))
        if found is not None:
            pages, truncated = found
            regions = [r for p in pages for r in p["regions"]]
            return Extraction("READY", "PDF_TEXT", regions, 0, truncated=truncated)

    try:
        pages = engine.recognize(content, check)
    except OcrError as exc:
        return _failed(str(exc))
    except (AgentError, RunStopped):
        raise
    except Exception:
        log.exception("글자 추출 중 예상하지 못한 오류")
        return _failed("글자를 읽는 중 오류")
    regions = [r for p in pages for r in p["regions"]]
    if not regions:
        return _failed("글자를 찾지 못함")
    truncated = bool(getattr(engine, "truncated", False))
    return Extraction("READY", "OCR", regions, count_low_confidence(pages), truncated=truncated)
