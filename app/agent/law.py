"""법령 조회(T23, `docs/agent-design.md` 2.4).

대조 에이전트의 `search_law`·`get_law_article` 도구가 쓴다.

- 원문은 `app/agent/law_data/`(법·시행령·별지 제4호). 시작할 때 한 번 **조 단위**로 나눈다.
  부칙은 뺀다. 별지 제4호는 통째로 한 조각이다.
- `ref` 모양: `LAW:7`, `LAW:2의2`, `DECREE:7`, `FORM4`.
- 검색은 낱말 검색이다(조항이 100개 남짓이라 임베딩 없이 충분).
- 인용 대조(`check_quote`)는 공백을 무시하고, 찾으면 인용이 있는 줄의 항·호까지 붙인
  화면 이름(label)을 준다.
  예: 법 제7조 ①항 2호 줄 → "법 제7조 제1항 제2호".

법령은 개인정보가 없는 공개 글이지만, 외부 AI에 보내는 글은 모두 `MaskedText`여야 하므로(원칙 4)
읽을 때 `mask_text`를 거친다. 대조도 그 글과 한다(AI가 본 글과 같은 글).
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.agent.masking import MaskedText, mask_text
from app.agent.output import LawRef, LawSource

DATA_DIR = Path(__file__).resolve().parent / "law_data"
FILES: dict[LawSource, str] = {
    "LAW": "law_20261002.txt",
    "DECREE": "decree_20261001.txt",
    "FORM4": "form4_20260929.txt",
}
PREFIX: dict[LawSource, str] = {"LAW": "법", "DECREE": "시행령"}
FORM4_REF = "FORM4"
FORM4_LABEL = "별지 제4호 이의제기신청서"

SEARCH_LIMIT = 5
SNIPPET_CHARS = 160

_HEADER = re.compile(r"^제(\d+)조(?:의(\d+))?\(([^)]*)\)\s*(.*)$")
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_HO = re.compile(r"^(\d+)(?:의(\d+))?\.\s")
# 개정 이력 표시는 조회 글에서 뺀다(토큰 절약, 인용 대상이 아님)
_NOTE = re.compile(r"<(?:개정|신설)[^>]*>|\[[^\]]*(?:개정|신설|삭제|시행일)[^\]]*\]")
_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_ARTICLE_IN_QUERY = re.compile(r"제?\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
_SPACE = re.compile(r"\s+")


def squash(text: str) -> str:
    return _SPACE.sub("", text)


@dataclass(frozen=True)
class Line:
    text: str
    # 그 줄이 속한 항(①이면 1)·호(2의2면 "2의2"). 없으면 None
    hang: int | None
    ho: str | None


@dataclass(frozen=True)
class Article:
    ref: str
    source: LawSource
    title: str
    # 화면 이름(조 단위). 예: "법 제7조"
    label: str
    lines: tuple[Line, ...]

    @property
    def text(self) -> MaskedText:
        return mask_text("\n".join(line.text for line in self.lines))


def _number(main: str, sub: str | None) -> str:
    return f"{main}의{sub}" if sub else main


def _cite(number: str, unit: str) -> str:
    """ "2의2", "조" → "제2조의2"(법령 인용 꼴)."""
    main, _, sub = number.partition("의")
    return f"제{main}{unit}" + (f"의{sub}" if sub else "")


def _clean(line: str) -> str:
    return _SPACE.sub(" ", _NOTE.sub("", line)).strip()


def _split_law(source: LawSource, raw: str) -> list[Article]:
    """법·시행령 원문을 조 단위로 나눈다. 본문 뒤 부칙(조 번호가 다시 1부터)은 뺀다."""
    articles: list[Article] = []
    current: dict | None = None
    last_main = 0

    def close() -> None:
        if current is not None:
            articles.append(
                Article(
                    ref=current["ref"],
                    source=source,
                    title=current["title"],
                    label=current["label"],
                    lines=tuple(current["lines"]),
                )
            )

    for raw_line in raw.splitlines():
        if "href=" in raw_line:  # 받은 HTML의 남은 조각 = 부칙 시작
            if articles or current:
                break
            continue
        line = _clean(raw_line)
        if not line:
            continue
        header = _HEADER.match(line)
        if header:
            main = int(header.group(1))
            if main < last_main:  # 부칙
                break
            last_main = main
            close()
            number = _number(header.group(1), header.group(2))
            current = {
                "ref": f"{source}:{number}",
                "title": header.group(3),
                "label": f"{PREFIX[source]} {_cite(number, '조')}",
                "lines": [],
                "hang": None,
                "ho": None,
            }
            rest = header.group(4)
            hang = _CIRCLED.index(rest[0]) + 1 if rest[:1] and rest[0] in _CIRCLED else None
            current["hang"] = hang
            current["lines"].append(Line(line, hang, None))
            continue
        if current is None:  # 제1조 앞의 머리말(법령 이름·시행일·담당 부서)
            continue
        if line[0] in _CIRCLED:
            current["hang"] = _CIRCLED.index(line[0]) + 1
            current["ho"] = None
        else:
            ho = _HO.match(line)
            if ho:
                current["ho"] = _number(ho.group(1), ho.group(2))
        current["lines"].append(Line(line, current["hang"], current["ho"]))
    close()
    return articles


def _split_form(raw: str) -> Article:
    lines = tuple(Line(_clean(x), None, None) for x in raw.splitlines() if _clean(x))
    return Article(FORM4_REF, "FORM4", "이의제기신청서", FORM4_LABEL, lines)


@cache
def articles() -> dict[str, Article]:
    out: dict[str, Article] = {}
    for source in ("LAW", "DECREE"):
        raw = (DATA_DIR / FILES[source]).read_text(encoding="utf-8")
        for a in _split_law(source, raw):
            out.setdefault(a.ref, a)
    form = _split_form((DATA_DIR / FILES["FORM4"]).read_text(encoding="utf-8"))
    out[form.ref] = form
    return out


def article(ref: str) -> Article | None:
    return articles().get(ref.strip()) if isinstance(ref, str) else None


def _snippet(a: Article, words: list[str]) -> str:
    text = "\n".join(line.text for line in a.lines)
    starts = [text.find(w) for w in words if text.find(w) >= 0]
    start = max(min(starts) - 40, 0) if starts else 0
    snippet = text[start : start + SNIPPET_CHARS].replace("\n", " ")
    return ("…" if start else "") + snippet + ("…" if start + SNIPPET_CHARS < len(text) else "")


def search(query: str, limit: int = SEARCH_LIMIT) -> list[dict[str, MaskedText | str]]:
    """낱말이 많이 맞는 조항. 제목에 맞으면 더 친다.

    "제7조"처럼 조 번호를 쓰면 그 조를 앞에 둔다.
    """
    words = list(dict.fromkeys(_WORD.findall(query or "")))
    wanted = {_number(m, s) for m, s in _ARTICLE_IN_QUERY.findall(query or "")}
    want_decree = "시행령" in (query or "")
    scored: list[tuple[int, int, Article]] = []
    for order, a in enumerate(articles().values()):
        body, title = squash(" ".join(x.text for x in a.lines)), squash(a.title)
        score = sum(body.count(w) + 3 * title.count(w) for w in words)
        number = a.ref.split(":", 1)[1] if ":" in a.ref else None
        if number in wanted and (a.source == "DECREE") == want_decree:
            score += 100
        if score > 0:
            scored.append((-score, order, a))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [
        {
            "ref": a.ref,
            "label": mask_text(a.label),
            "title": mask_text(a.title),
            "snippet": mask_text(_snippet(a, words)),
        }
        for _, _, a in scored[:limit]
    ]


def check_quote(ref: str, quote: str) -> tuple[bool, str | None]:
    """인용이 그 조항 원문에 공백을 무시하고 있나와 화면 이름.

    찾으면 인용이 시작되는 줄의 항·호까지 붙인 이름, 못 찾으면 조 단위 이름.
    없는 조항이면 (False, None).
    """
    a = article(ref)
    if a is None:
        return False, None
    needle = squash(quote or "")
    if not needle:
        return False, a.label
    squashed = [squash(str(mask_text(line.text))) for line in a.lines]
    whole = "".join(squashed)
    pos = whole.find(needle)
    if pos < 0:
        return False, a.label
    offset = 0
    for line, part in zip(a.lines, squashed, strict=True):
        if pos < offset + len(part):
            label = a.label
            if line.hang is not None:
                label += f" 제{line.hang}항"
            if line.ho is not None:
                label += f" {_cite(line.ho, '호')}"
            return True, label
        offset += len(part)
    return True, a.label


def law_ref(ref: str, quote: str, seen: set[str] | None = None) -> LawRef | None:
    """AI(또는 가짜 분석)가 단 근거 조항을 서버가 확인한 모양으로. 없는 조항이면 None.

    `seen`을 주면 그 실행에서 도구가 실제로 돌려준 조항만 `verified`가 될 수 있다(T24).
    """
    a = article(ref)
    if a is None:
        return None
    found, label = check_quote(a.ref, quote)
    verified = found and (seen is None or a.ref in seen)
    return LawRef(a.ref, a.source, (label if verified else a.label) or a.label, quote, verified)
