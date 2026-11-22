"""대조 결과 후검증(T16, `docs/agent-design.md` 2.4). AI 출력을 코드가 저장 전에 거른다.

- 거래 근거: 이번 실행에서 도구가 실제로 돌려준 거래 ID만 인정한다. 아니면 그 근거를 뺀다.
- 서류 근거: 이 사건 서류의 실제 줄(`evidenceId`·`regionIndex`)만 인정한다. 쪽 번호는 AI가 아니라
  그 줄에서 코드가 채운다.
- 글자 수 상한으로 자른다(긴 출력 유도 방지).

인용 원문 대조(`verified`)와 "근거 없는 일치 → 확인 못 함"은 저장할 때
`app/services/results.py`가 한다. 근거 없는 문장은 지우지 않는다(원칙 3).

방식 참고: corebank-objection-agent `objection_agent/worker.py` `_check_claim_sources`·`_keep_seen`·
`_clamp`(288~378행). 코드는 새로 작성.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.agent import law
from app.agent.extract import Extraction
from app.agent.output import (
    MAX_OPINIONS,
    MAX_QUESTIONS,
    MAX_RECOMMENDED,
    Conflict,
    Finding,
    LawRef,
    Opinion,
    Question,
    RecommendedDoc,
    Source,
)

MAX_FINDINGS = 10
MAX_SOURCES = 5
CLAIM_CHARS = 200
NOTE_CHARS = 300
QUOTE_CHARS = 200
CONFLICT_CHARS = 100
LABEL_CHARS = 60
OPINION_CHARS = 400
QUESTION_CHARS = 200
WHY_CHARS = 200
MAX_LAW_REFS = 3

STATUSES = ("MATCH", "CONFLICT", "STATEMENT_ONLY", "UNKNOWN")
CONFLICT_FIELDS = ("AMOUNT", "DATE", "COUNTERPARTY", "OTHER")

DEFAULT_NOTES = {
    "MATCH": "자료와 같은 내용입니다.",
    "CONFLICT": "자료와 다른 내용이 있습니다. 직접 확인해 주세요.",
    "STATEMENT_ONLY": "사연에만 있고 이를 보여 주는 자료가 없습니다.",
    "UNKNOWN": "자료로 확인하지 못했습니다. 직접 확인해 주세요.",
}


@dataclass
class Checked:
    findings: list[Finding] = field(default_factory=list)
    recommended: list[RecommendedDoc] = field(default_factory=list)
    # 뺀 근거·고친 항목 설명(step `VERIFY`에 남긴다)
    dropped: list[str] = field(default_factory=list)
    # 의견·질문(T24). 근거 번호는 `findings`(걸러진 뒤) 순서로 다시 맞춘 것
    opinions: list[Opinion] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    # 확인한 계획 항목 번호(T24, 계획 대비 점검)
    plan_covered: set[int] = field(default_factory=set)


def _clip(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def check_output(
    raw: dict[str, Any],
    extractions: dict[str, Extraction],
    seen_transactions: Iterable[str],
    doc_types: Iterable[str],
    seen_law_refs: Iterable[str] = (),
    plan_size: int = 0,
) -> Checked:
    """AI 출력(`compare.OUTPUT_SCHEMA` 모양)을 걸러 분석 출력 모양으로 바꾼다."""
    seen = set(seen_transactions)
    valid_doc_types = set(doc_types)
    out = Checked()
    # AI가 쓴 번호(0부터) → 걸러진 뒤 번호. 빈 주장이 빠지면 뒤 번호가 밀린다
    index_map: dict[int, int] = {}
    for i, item in enumerate((raw.get("findings") or [])[:MAX_FINDINGS]):
        if not isinstance(item, dict):
            continue
        finding = _finding(i + 1, item, extractions, seen, out.dropped)
        if finding is not None:
            index_map[i] = len(out.findings)
            out.findings.append(finding)
            plan_item = item.get("planItem")
            if isinstance(plan_item, int) and 0 <= plan_item < plan_size:
                out.plan_covered.add(plan_item)
    laws = set(seen_law_refs)
    for item in (raw.get("opinions") or [])[:MAX_OPINIONS]:
        opinion = _opinion(item, index_map, laws)
        if opinion is not None:
            out.opinions.append(opinion)
    for item in (raw.get("questions") or [])[:MAX_QUESTIONS]:
        question = _question(item, index_map, laws)
        if question is not None:
            out.questions.append(question)
    for item in raw.get("recommendedDocs") or []:
        if len(out.recommended) >= MAX_RECOMMENDED:
            break
        doc = _recommended(item, valid_doc_types)
        if doc is not None:
            out.recommended.append(doc)
    return out


def _finding(
    n: int,
    item: dict[str, Any],
    extractions: dict[str, Extraction],
    seen: set[str],
    dropped: list[str],
) -> Finding | None:
    claim = _clip(item.get("claim"), CLAIM_CHARS)
    if not claim:
        return None
    status = item.get("status") if item.get("status") in STATUSES else "UNKNOWN"
    note = _clip(item.get("note"), NOTE_CHARS)

    conflict = None
    raw_conflict = item.get("conflict")
    if status == "CONFLICT":
        if isinstance(raw_conflict, dict) and raw_conflict.get("field") in CONFLICT_FIELDS:
            conflict = Conflict(
                raw_conflict["field"],
                _clip(raw_conflict.get("statement"), CONFLICT_CHARS),
                _clip(raw_conflict.get("found"), CONFLICT_CHARS),
            )
        else:
            # 무엇이 어긋나는지 없는 어긋남은 "확인 못 함"으로 둔다(판정처럼 읽히지 않게)
            dropped.append(f"{n}번 항목: 어긋난 내용이 없어 '확인 못 함'으로 바꿈")
            status, note = "UNKNOWN", ""

    sources: list[Source] = []
    for raw_source in (item.get("sources") or [])[:MAX_SOURCES]:
        if not isinstance(raw_source, dict):
            continue
        source = _source(raw_source, extractions, seen)
        if source is None:
            dropped.append(f"{n}번 항목: 이 사건에서 확인되지 않는 근거를 뺌")
            continue
        sources.append(source)

    return Finding(
        claim=claim,
        status=status,
        note=note or DEFAULT_NOTES[status],
        conflict=conflict,
        sources=tuple(sources),
    )


def _source(
    raw: dict[str, Any], extractions: dict[str, Extraction], seen: set[str]
) -> Source | None:
    kind = raw.get("kind")
    quote = _clip(raw.get("quote"), QUOTE_CHARS) or None
    if kind == "NARRATIVE":
        return Source("NARRATIVE", quote=quote) if quote else None
    if kind == "EVIDENCE":
        evidence_id = raw.get("evidenceId")
        index = raw.get("regionIndex")
        ex = extractions.get(evidence_id) if isinstance(evidence_id, str) else None
        if ex is None or ex.status != "READY" or not isinstance(index, int):
            return None
        region = next((r for r in ex.regions if r.get("index") == index), None)
        if region is None:
            return None
        return Source(
            "EVIDENCE",
            quote=quote,
            evidence_id=evidence_id,
            page=region.get("page"),
            region_index=index,
        )
    if kind == "TRANSACTION":
        key = raw.get("transactionId")
        if not isinstance(key, str) or key not in seen:
            return None
        return Source("TRANSACTION", transaction_key=key)
    return None


def _indexes(raw: Any, index_map: dict[int, int]) -> tuple[int, ...]:
    """없는 번호는 버린다(원칙 3)."""
    values = raw if isinstance(raw, list) else []
    return tuple(
        dict.fromkeys(index_map[i] for i in values if isinstance(i, int) and i in index_map)
    )


def _law_refs(raw: Any, laws: set[str]) -> tuple[tuple[LawRef, ...], bool]:
    """근거 조항을 서버가 원문과 대조한 모양으로. 두 번째 값은 확인 못 한 조항이 있었나.

    이번 실행에서 도구가 돌려준 조항이고 인용이 그 원문에 있어야 `verified`.
    없는 조항(ref)은 칩을 만들 수 없어 빼고 확인 못 함으로 센다.
    """
    refs: list[LawRef] = []
    missing = False
    for item in (raw if isinstance(raw, list) else [])[:MAX_LAW_REFS]:
        if not isinstance(item, dict):
            continue
        quote = _clip(item.get("quote"), QUOTE_CHARS)
        ref = law.law_ref(str(item.get("ref") or ""), quote, laws) if quote else None
        if ref is None:
            missing = True
            continue
        missing = missing or not ref.verified
        refs.append(ref)
    return tuple(refs), missing


def _opinion(item: Any, index_map: dict[int, int], laws: set[str]) -> Opinion | None:
    if not isinstance(item, dict):
        return None
    text = _clip(item.get("text"), OPINION_CHARS)
    if not text:
        return None
    refs, missing = _law_refs(item.get("lawRefs"), laws)
    return Opinion(
        text=text,
        finding_indexes=_indexes(item.get("findingIndexes"), index_map),
        law_refs=refs,
        # 결과 예측·숫자 검사는 초안 단계(`drafting.check_opinion`)가 하고 고쳐 쓰기에 넣는다
        check_reason="LAW_QUOTE_NOT_FOUND" if missing else None,
    )


def _question(item: Any, index_map: dict[int, int], laws: set[str]) -> Question | None:
    if not isinstance(item, dict):
        return None
    text = _clip(item.get("text"), QUESTION_CHARS)
    if not text:
        return None
    refs, _ = _law_refs(item.get("lawRefs"), laws)
    return Question(
        text=text,
        why=_clip(item.get("why"), WHY_CHARS) or "소명에 필요한 사실이에요.",
        finding_indexes=_indexes(item.get("findingIndexes"), index_map),
        law_refs=refs,
    )


def _recommended(item: Any, valid_doc_types: set[str]) -> RecommendedDoc | None:
    if not isinstance(item, dict):
        return None
    label = _clip(item.get("label"), LABEL_CHARS)
    if not label:
        return None
    types: list[str] = []
    for t in item.get("acceptedDocTypes") or []:
        if t in valid_doc_types and t not in types:
            types.append(t)
    return RecommendedDoc(
        label=label,
        note=_clip(item.get("reason"), NOTE_CHARS) or "사연을 뒷받침할 자료입니다.",
        accepted_doc_types=tuple(types) or ("OTHER",),
    )
