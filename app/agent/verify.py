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

from app.agent.extract import Extraction
from app.agent.output import (
    MAX_RECOMMENDED,
    Conflict,
    Finding,
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


def _clip(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def check_output(
    raw: dict[str, Any],
    extractions: dict[str, Extraction],
    seen_transactions: Iterable[str],
    doc_types: Iterable[str],
) -> Checked:
    """AI 출력(`compare.OUTPUT_SCHEMA` 모양)을 걸러 분석 출력 모양으로 바꾼다."""
    seen = set(seen_transactions)
    valid_doc_types = set(doc_types)
    out = Checked()
    for i, item in enumerate((raw.get("findings") or [])[:MAX_FINDINGS], start=1):
        if not isinstance(item, dict):
            continue
        finding = _finding(i, item, extractions, seen, out.dropped)
        if finding is not None:
            out.findings.append(finding)
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
