"""분석 실행의 유일한 입구(CLAUDE.md 코드 구조).

분석기를 골라 ①②③ 단계를 순서대로 부른다. DB를 직접 만지지 않고, 넘겨받은 기록기로만 단계·step을
남기며, 결과는 `AnalysisOutput`으로 돌려준다(저장은 서비스 계층).
마감(150초)은 단계 사이마다 확인한다.

① 단계의 글자 추출(T13)은 분석기와 상관없는 코드 작업이라 여기서 한다. `AGENT_LLM=claude`일 때만
실제로 읽는다(가짜 분석은 정해 둔 결과라 읽지 않음, T13 결정 ①). 파일 읽기와 추출 결과 저장은
넘겨받은 증빙 저장소(`EvidenceStore`)로만 한다.

① 단계 분석기 전에 읽은 서류 줄과 사연을 가린다(T14, `app.agent.masking`). 가짜 분석에서도 사연은
가린다. AI는 가린 글만 본다(원칙 4). 그다음 거래내역서 줄에서 거래 행을 코드 규칙으로 뽑는다(T15).
"""

import time
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Protocol

from app.agent.extract import Extraction, extract_document
from app.agent.extract.ocr import TesseractEngine
from app.agent.masking import (
    MaskedText,
    collect_names,
    collect_narrative_names,
    mask_regions,
    mask_text,
)
from app.agent.output import AnalysisOutput
from app.agent.steps import STAGES, AgentError, AgentTimeout, Recorder
from app.agent.transactions import parse_rows


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    doc_type: str
    original_name: str
    # 분석 시작 때의 추출 상태. `READY`면 다시 읽지 않는다
    extract_status: str = "UPLOADED"


@dataclass(frozen=True)
class RunContext:
    case_id: str
    run_id: str
    agent: str
    inflow_type: str
    reported_amount_krw: int
    narrative: str
    sample_scenario: str | None
    evidence: tuple[EvidenceRef, ...]
    # time.monotonic() 기준 마감 시각
    deadline: float
    # 가짜 분석의 단계 사이 쉬는 시간(SCRIPTED_STAGE_DELAY_SECONDS)
    stage_delay_seconds: float = 0
    # 글자 추출 설정(TESSERACT_CMD·PDFTOPPM_CMD·OCR_LANG)
    ocr_lang: str = "kor+eng"
    tesseract_cmd: str | None = None
    pdftoppm_cmd: str | None = None
    # 사용자가 말한 입금 날짜(없을 수 있음)
    reported_occurred_at: date | None = None
    # 이 유형의 고정 체크리스트 라벨. AI가 같은 서류를 다시 권하지 않게 보여 준다(T08·T16)
    checklist_labels: tuple[str, ...] = ()
    # 대조 에이전트 설정(T16). `agent == "claude"`일 때만 쓴다
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "low"

    def check_deadline(self) -> None:
        if time.monotonic() > self.deadline:
            raise AgentTimeout()


class EvidenceStore(Protocol):
    """서류 파일 읽기와 추출 결과 저장. 구현은 서비스 계층(DB에 바로 저장)에 있다."""

    def content(self, evidence_id: str) -> bytes | None: ...

    def mark_processing(self, evidence_id: str) -> None: ...

    def save_extraction(self, evidence_id: str, result: Extraction) -> None: ...

    def load_extraction(self, evidence_id: str) -> Extraction | None: ...

    def save_masked(
        self, evidence_id: str, regions: list[dict[str, Any]], masked_text: MaskedText
    ) -> None: ...


class Analyzer(Protocol):
    def extract(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None: ...

    def compare(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None: ...

    def draft(self, ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None: ...


def select_analyzer(agent: str) -> Analyzer:
    """`AGENT_LLM` 값으로 분석기를 고른다. 실행마다 새로 만든다."""
    # 두 분석기가 이 모듈의 RunContext를 쓰므로 여기서 불러온다
    if agent == "claude":
        from app.agent.compare import ClaudeAnalyzer

        return ClaudeAnalyzer()
    from app.agent.scripted import ScriptedAnalyzer

    return ScriptedAnalyzer()


def _extract_evidence(
    ctx: RunContext, rec: Recorder, store: EvidenceStore, out: AnalysisOutput
) -> None:
    """서류마다 글자를 읽어 바로 저장한다. 못 읽은 서류는 `FAILED`로 두고 계속한다."""
    engine = TesseractEngine(
        lang=ctx.ocr_lang, tesseract_cmd=ctx.tesseract_cmd, pdftoppm_cmd=ctx.pdftoppm_cmd
    )
    for e in ctx.evidence:
        ctx.check_deadline()
        title = f"{e.original_name} 읽기"
        if e.extract_status == "READY":
            previous = store.load_extraction(e.evidence_id)
            if previous is not None:
                out.extractions[e.evidence_id] = previous
                rec.step("OCR", title, f"전에 읽은 글자 {len(previous.regions)}줄을 씁니다.")
                continue
        content = store.content(e.evidence_id)
        if content is None:  # 분석 중에 지워진 서류
            continue
        store.mark_processing(e.evidence_id)
        result = extract_document(content, engine, ctx.check_deadline)
        store.save_extraction(e.evidence_id, result)
        out.extractions[e.evidence_id] = result
        status = "DONE" if result.status == "READY" else "FAILED"
        rec.step("OCR", title, _extract_summary(result), status)


def _mask_inputs(ctx: RunContext, out: AnalysisOutput, store: EvidenceStore | None) -> None:
    """읽은 서류 줄과 사연을 가린다(T14). 서류가 바뀌면 이름 목록도 바뀌므로 실행마다 사건 전체를
    다시 가린다. AI(T16)는 여기서 만든 `maskedText`·`masked_narrative`만 본다."""
    lines = [r["text"] for ex in out.extractions.values() for r in ex.regions]
    names = collect_names(lines) | collect_narrative_names(ctx.narrative)
    for evidence_id, ex in list(out.extractions.items()):
        if ex.status != "READY":
            continue
        regions, masked = mask_regions(ex.regions, names)
        out.extractions[evidence_id] = replace(ex, regions=regions)
        if store is not None:
            store.save_masked(evidence_id, regions, masked)
    out.masked_narrative = mask_text(ctx.narrative, names)


def _extract_transactions(ctx: RunContext, rec: Recorder, out: AnalysisOutput) -> None:
    """읽은 거래내역서 줄에서 거래 행을 코드 규칙으로 뽑는다(T15). 저장은 서비스 계층이 한다."""
    for e in ctx.evidence:
        ex = out.extractions.get(e.evidence_id)
        if e.doc_type != "TRANSACTION_RECORD" or ex is None or ex.status != "READY":
            continue
        rows = parse_rows(ex.regions, e.evidence_id, start_key=len(out.transactions) + 1)
        out.transactions.extend(rows)
        title = f"{e.original_name} 거래내역 행 정리"
        if rows:
            ins = sum(r.direction == "IN" for r in rows)
            summary = f"거래 {len(rows)}건(입금 {ins}, 출금 {len(rows) - ins})을 찾았습니다."
            rec.step("OCR", title, summary)
        else:
            summary = "거래 행을 찾지 못했습니다. 결과에서 직접 확인해 주세요."
            rec.step("OCR", title, summary, "FAILED")


def _extract_summary(result: Extraction) -> str:
    if result.status == "FAILED":
        return f"글자를 읽지 못했습니다({result.error}). 결과 화면에서 직접 확인으로 안내합니다."
    if result.method == "PDF_TEXT":
        summary = f"글자가 든 PDF라 OCR 없이 {len(result.regions)}줄을 읽었습니다."
    else:
        summary = f"OCR로 {len(result.regions)}줄을 읽었습니다."
        if result.low_confidence:
            summary += f" 흐리게 읽은 줄 {result.low_confidence}개."
    if result.truncated:
        summary += " 쪽이 많아 앞쪽만 읽었습니다."
    return summary


def execute(ctx: RunContext, rec: Recorder, store: EvidenceStore | None = None) -> AnalysisOutput:
    analyzer = select_analyzer(ctx.agent)
    out = AnalysisOutput()
    steps = {
        "EXTRACTING": analyzer.extract,
        "COMPARING": analyzer.compare,
        "DRAFTING": analyzer.draft,
    }
    try:
        for stage, _label in STAGES:
            ctx.check_deadline()
            rec.stage(stage)
            if stage == "EXTRACTING":
                if ctx.agent == "claude" and store is not None:
                    _extract_evidence(ctx, rec, store, out)
                _mask_inputs(ctx, out, store)
                _extract_transactions(ctx, rec, out)
            steps[stage](ctx, rec, out)
        ctx.check_deadline()
    except AgentError as exc:
        # 실패한 실행도 외부 AI 비용(`out.model`·토큰)을 남길 수 있게 출력을 붙인다
        exc.output = out  # type: ignore[attr-defined]
        raise
    return out
