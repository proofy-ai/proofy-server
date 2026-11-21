"""글자가 든 PDF에서 OCR 없이 글자를 뽑는다(T13, 새로 작성).

쪽마다 `pypdf`로 글을 뽑아 줄마다 영역 하나를 만든다. 위치(`bbox`)와 신뢰도는 없다(T13 결정 ③).
글자가 거의 없으면(스캔본) `None`을 돌려주고, 부르는 쪽이 OCR로 넘긴다.
"""

import io
import logging

from pypdf import PdfReader

from app.agent.extract.ocr import REGION_TEXT_LIMIT, REGIONS_PER_PAGE_LIMIT, Page

log = logging.getLogger("proofy.extract")

# 공백을 뺀 글자가 이보다 적으면 글자가 든 PDF로 보지 않는다
MIN_TEXT_CHARS = 20
MAX_PAGES = 20


class PdfUnreadable(Exception):
    """PDF를 열지 못했다(깨진 파일, 암호)."""


def extract_pdf_text(content: bytes) -> tuple[list[Page], bool] | None:
    """(쪽 목록, 뒷쪽을 잘랐는지). 글자가 거의 없으면 None."""
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise PdfUnreadable("암호가 걸린 PDF")
        all_pages = list(reader.pages)
    except PdfUnreadable:
        raise
    except Exception as exc:
        log.warning("PDF 열기 실패: %s", type(exc).__name__)
        raise PdfUnreadable("PDF를 열지 못함") from exc

    pages: list[Page] = []
    index = 0
    chars = 0
    for number, page in enumerate(all_pages[:MAX_PAGES], start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            log.warning("PDF %d쪽 글자 추출 실패", number)
            text = ""
        regions = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            chars += len("".join(line.split()))
            regions.append(
                {
                    "index": index,
                    "page": number,
                    "text": line[:REGION_TEXT_LIMIT],
                    "bbox": None,
                    "confidence": None,
                }
            )
            index += 1
            if len(regions) >= REGIONS_PER_PAGE_LIMIT:
                break
        box = page.mediabox
        pages.append(
            {
                "page": number,
                "width": round(float(box.width)),
                "height": round(float(box.height)),
                "regions": regions,
            }
        )
    if chars < MIN_TEXT_CHARS:
        return None
    return pages, len(all_pages) > MAX_PAGES
