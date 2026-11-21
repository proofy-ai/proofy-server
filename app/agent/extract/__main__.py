"""확인용: 서류 글자 추출 결과를 출력한다(T12 서류 확인, 배포 뒤 OCR 점검).

    uv run python -m app.agent.extract 파일 [파일 …]

Tesseract·pdftoppm 경로와 언어는 서버와 같은 설정(`TESSERACT_CMD`·`PDFTOPPM_CMD`·`OCR_LANG`)을 쓴다.
"""

import sys
from pathlib import Path

from app.agent.extract import extract_document
from app.agent.extract.ocr import TesseractEngine
from app.config import get_settings


def main(paths: list[str]) -> int:
    settings = get_settings()
    engine = TesseractEngine(
        lang=settings.ocr_lang,
        tesseract_cmd=settings.tesseract_cmd,
        pdftoppm_cmd=settings.pdftoppm_cmd,
    )
    for path in paths:
        result = extract_document(Path(path).read_bytes(), engine)
        print(f"== {path}: {result.status} {result.method or ''}".rstrip())
        if result.error:
            print(f"   사유: {result.error}")
            continue
        print(f"   {len(result.regions)}줄, 흐린 줄 {result.low_confidence}")
        for r in result.regions:
            conf = "" if r["confidence"] is None else f" ({r['confidence']:.2f})"
            print(f"   [{r['index']}] p{r['page']} {r['text']}{conf}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
