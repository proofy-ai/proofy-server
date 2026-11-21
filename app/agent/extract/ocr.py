"""그림·스캔 PDF 글자 인식. 로컬 Tesseract CLI로 읽고, PDF는 poppler `pdftoppm`으로 쪽 이미지로
바꿔 읽는다.

읽기 전에 방향, 기울기, 조명, 잡음, 해상도를 바로잡고(`preprocess`), 영역 상자는 원본 좌표로
되돌린다. 원본 이미지는 외부 AI에 보내지 않는다(원칙 4). 읽은 글자는 서버 안에서 마스킹한 뒤에만
AI로 간다(T14).

결과 모양: `[{page, width, height, regions: [{index, page, text, bbox: [x, y, w, h], confidence}]}]`
영역은 줄 단위다. `index`는 서류 전체에서 0부터 이어지는 번호다(`evidence.regions_json`, ERD 3.3).
`confidence`는 엔진이 낸 글자 인식 확률(0~1)이다. 0.85 미만은 "흐리게 읽은 줄"로 센다.

출처: corebank-objection-agent `objection_agent/ocr.py` 1~293행 중 `detect_format`, `OcrError`,
`OcrEngine`, `TesseractEngine`, `parse_tsv`, `_child_env`, `_binary`, `count_low_confidence`.
바꾼 점: corebank 서버 계약 주석 제거, 프로그램 경로를 설정으로(Windows), 영역에 `page` 추가,
줄 길이 100.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from app.agent.extract import preprocess

Page = dict[str, Any]
log = logging.getLogger("proofy.extract")

LOW_CONFIDENCE = 0.85
# 방향 감지 신뢰도. 이 이상이면 바로 돌리고, 사이면 원본과 돌린 것을 둘 다 읽는다
OSD_SURE = 4.0
OSD_MAYBE = 1.0
# 상한: 쪽 수, 엔진 이름 길이, 영역 글 길이, 쪽당 영역 수(메모리·DB 보호)
MAX_PAGES_LIMIT = 50
ENGINE_NAME_LIMIT = 40
REGION_TEXT_LIMIT = 2000
REGIONS_PER_PAGE_LIMIT = 2000
# 자식 프로세스(poppler, tesseract)에 넘기는 환경. API 키를 물려주지 않는다.
# SYSTEMROOT는 Windows에서 자식 프로세스가 뜨는 데 필요하다
_CHILD_ENV_KEYS = ("PATH", "TESSDATA_PREFIX", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")


class OcrError(RuntimeError):
    """서류 하나를 읽지 못했다. 그 서류만 실패로 남기고 분석을 이어 간다."""


class OcrEngine(Protocol):
    @property
    def name(self) -> str: ...

    def recognize(self, content: bytes, check: Callable[[], None] | None = None) -> list[Page]: ...


def detect_format(content: bytes) -> str:
    """선언된 형식이 아니라 매직 바이트로 형식을 정한다(업로드 검증과 같은 기준)."""
    if content.startswith(b"%PDF"):
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    raise OcrError("지원하지 않는 서류 형식")


class TesseractEngine:
    def __init__(
        self,
        lang: str = "kor+eng",
        dpi: int = 200,
        max_pages: int = 10,
        timeout_seconds: float = 60.0,
        psm: int = 4,
        preprocess: bool = True,
        tesseract_cmd: str | None = None,
        pdftoppm_cmd: str | None = None,
    ):
        self._lang = lang
        self._preprocess = preprocess
        self.truncated = False  # 마지막 recognize에서 쪽 상한 때문에 뒷쪽을 읽지 않았는지
        # 4는 「크기가 다른 글이 한 단으로 이어진 문서」. 서식 서류에서 3(자동)보다 줄을 덜 빠뜨린다
        self._psm = psm
        self._dpi = dpi
        self._max_pages = max(1, min(max_pages, MAX_PAGES_LIMIT))
        self._timeout = timeout_seconds
        self._tesseract_cmd = tesseract_cmd
        self._pdftoppm_cmd = pdftoppm_cmd
        self._name: str | None = None

    def available(self) -> bool:
        try:
            _binary("tesseract", self._tesseract_cmd)
        except OcrError:
            return False
        return True

    @property
    def name(self) -> str:
        if self._name is None:
            version = "tesseract"
            try:
                out = self._run([_binary("tesseract", self._tesseract_cmd), "--version"])
                version = out.splitlines()[0].strip() or version
            except OcrError:
                pass
            self._name = f"{version} {self._lang}"[:ENGINE_NAME_LIMIT]
        return self._name

    def recognize(self, content: bytes, check: Callable[[], None] | None = None) -> list[Page]:
        """check는 쪽마다 부르는 마감 확인이다. 마감을 넘겼으면 예외를 올려 읽기를 멈춘다."""
        kind = detect_format(content)
        self.truncated = False
        with tempfile.TemporaryDirectory(prefix="ocr-") as tmp:
            work = Path(tmp)
            if kind == "pdf":
                sources = [p.read_bytes() for p in self._pdf_pages(content, work)]
            else:
                sources = [content]
            pages: list[Page] = []
            next_index = 0
            for number, source in enumerate(sources, start=1):
                if check is not None:
                    check()
                page = self._read_page(source, number, next_index, work)
                next_index += len(page["regions"])
                pages.append(page)
        return pages

    def _read_page(self, source: bytes, number: int, start_index: int, work: Path) -> Page:
        if not self._preprocess:
            return self._ocr(source, number, start_index, work)
        try:
            gray, transform = preprocess.load_gray(source)
            gray = preprocess.upscale(gray, transform)
        except preprocess.ImageRejected as exc:
            raise OcrError(str(exc)) from exc
        except Exception as exc:  # 깨진 이미지는 그 서류만 실패로 남긴다
            raise OcrError("이미지를 열지 못함") from exc
        gray = preprocess.flatten(gray)

        # 방향 감지가 확실하면 돌리고, 애매하면 원본과 돌린 것을 둘 다 읽어 결과가 나은 쪽을 쓴다
        rotation, confidence = self._orientation(gray, work)
        candidates = [(gray, transform)]
        if rotation:
            turned_transform = transform.copy()
            turned = preprocess.rotate(gray, -rotation, turned_transform)
            if confidence >= OSD_SURE:
                candidates = [(turned, turned_transform)]
            elif confidence >= OSD_MAYBE:
                candidates.append((turned, turned_transform))

        best: tuple[float, Page] | None = None
        for image, base in candidates:
            applied = base.copy()
            cleaned = preprocess.denoise(preprocess.deskew(image, applied))
            page = self._ocr(preprocess.to_png(cleaned), number, start_index, work)
            for region in page["regions"]:
                region["bbox"] = applied.to_original(region["bbox"])
            page["width"], page["height"] = applied.original_size
            score = sum(r["confidence"] * len(r["text"]) for r in page["regions"])
            if best is None or score > best[0]:
                best = (score, page)
        assert best is not None  # 후보는 항상 하나 이상이다
        return best[1]

    def _ocr(self, image: bytes, number: int, start_index: int, work: Path) -> Page:
        # 한 번 돌려 txt와 tsv를 함께 받는다.
        # tsv는 한글 음절을 단어로 쪼개는 일이 있어 줄 글은 txt에서 가져온다
        source = work / f"in-{number}.img"
        source.write_bytes(image)
        base = work / f"out-{number}"
        self._run(
            [
                _binary("tesseract", self._tesseract_cmd),
                str(source),
                str(base),
                "-l",
                self._lang,
                "--psm",
                str(self._psm),
                "txt",
                "tsv",
            ]
        )
        tsv = base.with_suffix(".tsv").read_text("utf-8", "replace")
        text = base.with_suffix(".txt").read_text("utf-8", "replace")
        return parse_tsv(tsv, number, start_index, text)

    def _orientation(self, image: Image.Image, work: Path) -> tuple[int, float]:
        """Tesseract 방향 감지. (돌려야 할 각도, 신뢰도).

        글자가 적거나 osd 데이터가 없으면 (0, 0).
        """
        path = work / "osd.png"
        path.write_bytes(preprocess.to_png(image))
        try:
            tesseract = _binary("tesseract", self._tesseract_cmd)
            out = self._run([tesseract, str(path), "-", "--psm", "0", "-l", "osd"])
        except OcrError:
            return 0, 0.0
        rotate = re.search(r"Rotate:\s*(\d+)", out)
        confidence = re.search(r"Orientation confidence:\s*([\d.]+)", out)
        if not rotate or not confidence:
            return 0, 0.0
        return int(rotate.group(1)) % 360, float(confidence.group(1))

    def _pdf_pages(self, content: bytes, work: Path) -> list[Path]:
        source = work / "document.pdf"
        source.write_bytes(content)
        prefix = work / "page"
        # 상한보다 한 쪽 더 만들어 보고, 생기면 뒷쪽이 있다는 표시만 남기고 읽지 않는다
        self._run(
            [
                _binary("pdftoppm", self._pdftoppm_cmd),
                "-r",
                str(self._dpi),
                "-png",
                "-l",
                str(self._max_pages + 1),
                str(source),
                str(prefix),
            ]
        )
        # pdftoppm은 쪽 수에 따라 page-1.png 또는 page-01.png로 이름을 붙인다
        images = sorted(work.glob("page-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
        if not images:
            raise OcrError("PDF에서 쪽 이미지를 만들지 못함")
        self.truncated = len(images) > self._max_pages
        return images[: self._max_pages]

    def _run(self, args: list[str]) -> str:
        try:
            # 인자는 목록으로만 넘기고 셸을 쓰지 않는다. 파일 경로는 이 모듈이 만든 임시 경로다
            result = subprocess.run(
                args, capture_output=True, timeout=self._timeout, check=False, env=_child_env()
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrError(f"{Path(args[0]).name} 시간 초과") from exc
        if result.returncode != 0:
            # stderr에는 임시 경로가 들어 있어 화면에 남기지 않는다. 원문은 서버 로그에만 남긴다
            log.warning(
                "%s 실패 code=%s %s", Path(args[0]).name, result.returncode, result.stderr[-500:]
            )
            raise OcrError(f"{Path(args[0]).name} 실패(코드 {result.returncode})")
        return result.stdout.decode("utf-8", "replace")


def _child_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _CHILD_ENV_KEYS if k in os.environ}
    # 한 호스트에서 여럿이 돌 때 tesseract가 코어를 독차지하지 않게 한다
    env["OMP_THREAD_LIMIT"] = "1"
    return env


def _binary(name: str, configured: str | None = None) -> str:
    """설정한 경로가 있으면 그것, 없으면 PATH에서 찾는다."""
    path = shutil.which(configured) if configured else shutil.which(name)
    if path is None:
        raise OcrError(f"{name}가 설치돼 있지 않음")
    return path


def parse_tsv(tsv: str, page_number: int, start_index: int = 0, text: str | None = None) -> Page:
    """Tesseract TSV를 줄 단위 영역으로 묶는다.

    단어(level 5)를 (block, par, line)으로 모아 상자를 합치고 신뢰도를 평균한다.
    text는 같은 실행의 txt 출력이다. 공백을 뺀 글자가 같은 줄이 있으면 그 줄의 띄어쓰기를 쓰고,
    없으면 단어를 공백으로 잇는다.
    """
    spaced: dict[str, list[str]] = {}
    for line in (text or "").splitlines():
        if line.strip():
            spaced.setdefault(_compact(line), []).append(line.strip())
    width = height = 0
    lines: dict[tuple[int, int, int], list[tuple[str, int, int, int, int, float]]] = {}
    rows = tsv.splitlines()
    for row in rows[1:]:
        cols = row.split("\t")
        if len(cols) < 12:
            continue
        level = int(cols[0])
        left, top, w, h = (int(c) for c in cols[6:10])
        if level == 1:
            width, height = w, h
            continue
        if level != 5:
            continue
        word = cols[11].strip()
        conf = float(cols[10])
        if not word or conf < 0:
            continue
        key = (int(cols[2]), int(cols[3]), int(cols[4]))
        lines.setdefault(key, []).append((word, left, top, w, h, conf))

    regions = []
    for words in lines.values():
        x0 = min(w[1] for w in words)
        y0 = min(w[2] for w in words)
        x1 = max(w[1] + w[3] for w in words)
        y1 = max(w[2] + w[4] for w in words)
        joined = " ".join(w[0] for w in words)
        candidates = spaced.get(_compact(joined))
        regions.append(
            {
                "index": start_index + len(regions),
                "page": page_number,
                "text": (candidates.pop(0) if candidates else joined)[:REGION_TEXT_LIMIT],
                "bbox": [x0, y0, x1 - x0, y1 - y0],
                "confidence": round(sum(w[5] for w in words) / len(words) / 100, 3),
            }
        )
    return {
        "page": page_number,
        "width": width,
        "height": height,
        "regions": regions[:REGIONS_PER_PAGE_LIMIT],
    }


def _compact(value: str) -> str:
    return "".join(value.split())


def count_low_confidence(pages: list[Page]) -> int:
    return sum(
        1
        for p in pages
        for r in p.get("regions") or []
        if (r.get("confidence") or 0) < LOW_CONFIDENCE
    )
