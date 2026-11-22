"""분석 시작·진행(계약 4.9·4.10).

- 분석은 서버 안 스레드에서 돈다. 스레드는 자기 DB 세션을 쓰고, 단계·step을 남길 때마다 바로 커밋해
  폴링(`GET …/analysis-runs/{runId}`)에 보이게 한다.
- 사건당 동시 실행은 1개다. 확인과 실행 행 만들기를 사건별 잠금 안에서 한다(서버 프로세스 1개 전제).
- 마감(기본 150초)은 스레드가 단계마다 확인한다. 서버 재시작으로 스레드가 사라진 실행은 조회·시작 때
  마감이 지났으면 그 자리에서 시간 초과로 끝낸다.
- 분석 결과(대조 결과·거래 행·AI 권장 항목·초안)는 실행을 `SUCCEEDED`로 바꾸는 것과
  같은 커밋에 저장한다.
  그사이 시간 초과로 끝난 실행이면 결과도 버린다.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.agent import runner
from app.agent.extract import Extraction
from app.agent.masking import MaskedText
from app.agent.output import AnalysisOutput
from app.agent.runner import EvidenceRef, RunContext
from app.agent.steps import (
    STAGES,
    AgentError,
    AgentTimeout,
    RunStopped,
    Stage,
    StepStatus,
    StepType,
)
from app.config import Settings
from app.errors import ApiError
from app.models import AnalysisRun, Case, Evidence, EvidenceFile, UsageEvent
from app.schemas.analysis import AnalysisRunOut, AnalysisStart, RunError, StageOut, StepOut
from app.schemas.case import CasePatch
from app.services.cases import update_case
from app.services.clock import utc_now
from app.services.drafts import has_user_edits
from app.services.evidence import list_evidence
from app.services.questions import answer_pairs, check_answers, previous_review, save_answers
from app.services.requirements import requirements_for
from app.services.results import save_output
from app.services.runs import latest_run
from app.services.usage import count_ai_runs_on

logger = logging.getLogger("proofy.analysis")

MIN_NARRATIVE = 20
# 분석에 꼭 필요한 서류(계약 4.2 `requiredForAnalysis`)
ANALYSIS_DOC_TYPE = "TRANSACTION_RECORD"
PRECONDITION_MESSAGE = "사연을 20자 이상 입력하고 거래내역서를 올려 주세요."

_case_locks: dict[str, threading.Lock] = {}
_case_locks_guard = threading.Lock()


def _case_lock(case_id: str) -> threading.Lock:
    with _case_locks_guard:
        return _case_locks.setdefault(case_id, threading.Lock())


def _check_precondition(db: Session, case: Case) -> None:
    narrative_length = len((case.narrative or "").strip())
    missing: list[str] = []
    if narrative_length < MIN_NARRATIVE:
        missing.append("NARRATIVE")
    if not any(e.doc_type == ANALYSIS_DOC_TYPE for e in list_evidence(db, case.id)):
        missing.append(ANALYSIS_DOC_TYPE)
    if missing:
        raise ApiError(
            422,
            "ANALYSIS_PRECONDITION",
            PRECONDITION_MESSAGE,
            {"narrativeLength": narrative_length, "missing": missing},
        )


def start_analysis(
    db: Session,
    case: Case,
    payload: AnalysisStart,
    settings: Settings,
    session_factory: sessionmaker[Session],
    today: date,
) -> AnalysisRun:
    """검사 순서: 답 검사 400 → 사연 저장 → 답 저장 → 사전 조건 422 → 실행 중 409
    → 고친 초안 409 → 하루 한도 429 → 실행 시작.

    답이 틀리면 사연도 저장하지 않는다(T25 결정 1, 요청이 반만 반영되지 않게).
    하루 한도를 넘었어도 샘플 그대로인 사건은 429 대신 AI를 부르지 않고 미리 만든 결과로
    끝낸다(T11).
    """
    answers = check_answers(db, case, payload.answers or [])
    if payload.narrative is not None:
        # 저장된 값과 다를 때만 inputVersion +1(계약 4.5와 같은 규칙)
        update_case(db, case, CasePatch(narrative=payload.narrative), today)
    save_answers(db, case, answers)
    _check_precondition(db, case)

    with _case_lock(case.id):
        current = latest_run(db, case.id)
        if current is not None and current.status == "RUNNING":
            expire_if_overdue(db, current, settings.analysis_timeout_seconds)
            if current.status == "RUNNING":
                raise ApiError(
                    409,
                    "ANALYSIS_IN_PROGRESS",
                    "이미 분석 중입니다.",
                    {"runId": current.id},
                )
        if has_user_edits(db, case) and not payload.overwrite_edited_draft:
            raise ApiError(
                409,
                "DRAFT_HAS_EDITS",
                "다시 분석하면 직접 고친 초안이 새 초안으로 바뀝니다.",
            )
        uses_ai = settings.agent_llm == "claude"
        allow_fallback = uses_ai and is_unchanged_sample(case)
        over_limit = uses_ai and count_ai_runs_on(db, today) >= settings.daily_analysis_limit
        if over_limit and not allow_fallback:
            raise ApiError(
                429, "DAILY_LIMIT", "오늘 AI 분석 한도를 다 썼어요. 내일 다시 시도해 주세요."
            )

        now = utc_now()
        run = AnalysisRun(
            id=str(uuid.uuid4()),
            case_id=case.id,
            version=(current.version + 1) if current else 1,
            based_on_input_version=case.input_version,
            status="RUNNING",
            stage="EXTRACTING",
            steps_json=[],
            precomputed=False,
            agent=settings.agent_llm,
            started_at=now,
        )
        db.add(run)
        db.add(
            UsageEvent(
                id=str(uuid.uuid4()),
                kind="ANALYSIS_RUN",
                case_id=case.id,
                run_id=run.id,
                # 가짜 분석·한도 초과로 바로 미리 만든 결과를 쓰는 실행은 외부 AI를 부르지 않는다
                ai_called=uses_ai and not over_limit,
                # 미리 만든 결과로 끝나면 마무리 때 true로 바꾼다
                precomputed=False,
                referral=False,
                agent=settings.agent_llm,
                created_at=now,
            )
        )
        case.status = "ANALYZING"
        db.commit()

    ctx = RunContext(
        case_id=case.id,
        run_id=run.id,
        agent=settings.agent_llm,
        inflow_type=case.inflow.inflow_type,
        reported_amount_krw=case.inflow.reported_amount_krw,
        narrative=case.narrative or "",
        sample_scenario=case.sample_scenario,
        evidence=tuple(
            EvidenceRef(e.id, e.doc_type, e.original_name, e.extract_status)
            for e in list_evidence(db, case.id)
        ),
        deadline=time.monotonic()
        + _agent_timeout(settings.analysis_timeout_seconds, allow_fallback),
        stage_delay_seconds=settings.scripted_stage_delay_seconds,
        ocr_lang=settings.ocr_lang,
        tesseract_cmd=settings.tesseract_cmd,
        pdftoppm_cmd=settings.pdftoppm_cmd,
        reported_occurred_at=case.inflow.occurred_at,
        checklist_labels=tuple(r.label for r in requirements_for(case.inflow.inflow_type)),
        anthropic_api_key=settings.anthropic_api_key,
        anthropic_model=settings.anthropic_model,
        anthropic_effort=settings.anthropic_effort,
        allow_fallback=allow_fallback,
        answers=answer_pairs(db, case.id),
        # 새 실행은 아직 RUNNING이라 지난 성공 실행이 잡힌다
        previous=previous_review(db, case),
    )
    threading.Thread(
        target=_run_in_background,
        args=(session_factory, ctx, over_limit),
        name=f"analysis-{run.id[:8]}",
        daemon=True,
    ).start()
    return run


def is_unchanged_sample(case: Case) -> bool:
    """샘플 사건을 사연·서류·답변을 바꾸지 않은 그대로 분석하나(계약 4.10 "샘플 그대로")."""
    return case.is_sample and case.sample_input_version == case.input_version


# 미리 만든 결과를 쓸 수 있는 실행은 AI 마감을 조금 당겨, 폴링의 시간 초과 처리보다 먼저
# 대체 결과를 저장할 시간을 남긴다(T11)
FALLBACK_MARGIN_SECONDS = 10


def _agent_timeout(timeout_seconds: float, allow_fallback: bool) -> float:
    if not allow_fallback:
        return timeout_seconds
    return timeout_seconds - min(FALLBACK_MARGIN_SECONDS, timeout_seconds / 10)


def _run_in_background(
    session_factory: sessionmaker[Session], ctx: RunContext, skip_ai: bool = False
) -> None:
    """`skip_ai`면 하루 한도를 넘은 샘플 사건이라 AI 없이 바로 미리 만든 결과로 끝낸다(T11)."""
    recorder = DbRecorder(session_factory, ctx.run_id)
    store = DbEvidenceStore(session_factory, ctx.case_id)
    try:
        if skip_ai:
            _finish_with_fallback(ctx, recorder, None)
            return
        try:
            output = runner.execute(ctx, recorder, store)
        except RunStopped:
            raise
        except AgentError as exc:
            # 실패해도 외부 AI 비용은 들었으므로 runner가 붙여 준 출력으로 비용을 남긴다
            _finish_failed(ctx, recorder, exc, getattr(exc, "output", None))
            return
        except Exception:
            # 내부 내용은 로그에만 남기고 화면에는 공통 문구를 준다
            logger.exception("분석 %s 실패", ctx.run_id)
            _finish_failed(ctx, recorder, AgentError(), None)
            return
        try:
            recorder.finish(None, output)
        except RunStopped:
            raise
        except Exception:
            logger.exception("분석 %s 결과 저장 실패", ctx.run_id)
            _finish_failed(ctx, recorder, AgentError(), None, output)
    except RunStopped:
        logger.info("분석 %s: 밖에서 끝난 실행이라 멈춤", ctx.run_id)


def _finish_failed(
    ctx: RunContext,
    recorder: "DbRecorder",
    error: AgentError,
    output: AnalysisOutput | None,
    fallback_source: AnalysisOutput | None = None,
) -> None:
    """실패로 끝낸다. 샘플 그대로인 사건은 미리 만든 결과로 대신 끝낸다(계약 4.10)."""
    if ctx.allow_fallback:
        logger.warning("분석 %s: %s → 미리 만든 결과로 대체", ctx.run_id, error.code)
        try:
            _finish_with_fallback(ctx, recorder, fallback_source or output)
            return
        except RunStopped:
            raise
        except Exception:
            logger.exception("분석 %s 미리 만든 결과 실패", ctx.run_id)
    recorder.finish(error, output)


def _finish_with_fallback(
    ctx: RunContext, recorder: "DbRecorder", failed: AnalysisOutput | None
) -> None:
    output = runner.execute_fallback(ctx, recorder, failed)
    recorder.finish(None, output, precomputed=True)


def _iso_now() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _with_step(
    steps: list[dict[str, Any]],
    type: StepType,
    title: str,
    summary: str | None,
    status: StepStatus,
) -> list[dict[str, Any]]:
    """step을 하나 더한 새 리스트(JSON 컬럼은 새 값을 넣어야 변경이 저장된다)."""
    step = {
        "seq": len(steps) + 1,
        "type": type,
        "title": title,
        "summary": summary,
        "status": status,
        "at": _iso_now(),
    }
    return [*steps, step]


def _record_usage(db: Session, run: AnalysisRun, output: AnalysisOutput) -> None:
    """외부 AI를 부른 실행이면 모델·토큰·비용을 남긴다(T16). 실패한 실행도 남긴다(비용은 들었다)."""
    if output.model is None:
        return
    run.model = output.model
    run.prompt_version = output.prompt_version
    db.execute(
        update(UsageEvent)
        .where(UsageEvent.run_id == run.id, UsageEvent.kind == "ANALYSIS_RUN")
        .values(
            model=output.model,
            input_tokens=output.input_tokens,
            output_tokens=output.output_tokens,
            cost_micro_usd=output.cost_micro_usd,
        )
    )


def _finish_run(
    db: Session, run: AnalysisRun, error: AgentError | None, precomputed: bool = False
) -> bool:
    """실행을 끝낸다. 아직 `RUNNING`일 때만 바꾸고, 바꿨으면 True.

    상태 조건을 UPDATE 문에 넣어, 시간 초과 처리와 스레드의 마무리가 겹쳐도 한쪽만 반영되게 한다.
    바꾸지 못했으면 세션에 넣어 둔 결과 행도 버린다(롤백).
    """
    values: dict[str, Any] = {"finished_at": utc_now()}
    if error is None:
        values |= {"status": "SUCCEEDED", "stage": "FINISHED", "precomputed": precomputed}
        case_status = "REVIEW_READY"
    else:
        values |= {
            "status": "FAILED",
            "error_code": error.code,
            "error_message": error.message,
            "steps_json": _with_step(
                run.steps_json, "FAILED", "분석 실패", error.message, "FAILED"
            ),
        }
        case_status = "ERROR"
    result = db.execute(
        update(AnalysisRun)
        .where(AnalysisRun.id == run.id, AnalysisRun.status == "RUNNING")
        .values(**values)
    )
    changed = result.rowcount == 1
    if not changed:
        db.rollback()
        return False
    db.execute(update(Case).where(Case.id == run.case_id).values(status=case_status))
    db.commit()
    return True


def expire_if_overdue(db: Session, run: AnalysisRun, timeout_seconds: float) -> None:
    """마감이 지났는데 `RUNNING`이면 시간 초과로 끝낸다(스레드가 사라진 실행 정리)."""
    if run.status != "RUNNING":
        return
    if utc_now() - run.started_at <= timedelta(seconds=timeout_seconds):
        return
    _finish_run(db, run, AgentTimeout())
    db.refresh(run)


class DbRecorder:
    """분석기의 기록기(`app.agent.steps.Recorder`). 남길 때마다 짧은 세션을 열어 바로 커밋한다."""

    def __init__(self, session_factory: sessionmaker[Session], run_id: str) -> None:
        self._session_factory = session_factory
        self._run_id = run_id

    def _update(self, change: Callable[[AnalysisRun], None]) -> None:
        with self._session_factory() as db:
            run = db.get(AnalysisRun, self._run_id)
            # 시간 초과로 이미 끝났거나 사건이 지워졌다
            if run is None or run.status != "RUNNING":
                raise RunStopped()
            change(run)
            db.commit()

    def stage(self, stage: Stage) -> None:
        def change(run: AnalysisRun) -> None:
            run.stage = stage

        self._update(change)

    def step(
        self, type: StepType, title: str, summary: str | None, status: StepStatus = "DONE"
    ) -> None:
        def change(run: AnalysisRun) -> None:
            run.steps_json = _with_step(run.steps_json, type, title, summary, status)

        self._update(change)

    def finish(
        self,
        error: AgentError | None,
        output: AnalysisOutput | None = None,
        precomputed: bool = False,
    ) -> None:
        """`precomputed`면 샘플용으로 미리 만든 결과로 끝낸다(T11, 계약 4.10)."""
        with self._session_factory() as db:
            run = db.get(AnalysisRun, self._run_id)
            if run is None or run.status != "RUNNING":
                return
            if output is not None:
                _record_usage(db, run, output)
            if error is None and output is not None:
                save_output(db, run, output)
            if error is None and precomputed:
                db.execute(
                    update(UsageEvent)
                    .where(UsageEvent.run_id == run.id, UsageEvent.kind == "ANALYSIS_RUN")
                    .values(precomputed=True)
                )
            _finish_run(db, run, error, precomputed)


class DbEvidenceStore:
    """분석 스레드의 증빙 저장소(`app.agent.runner.EvidenceStore`).

    추출 결과는 실행 성공 여부와 상관없이 바로 저장한다(서류의 성질이라 다음 분석에서 다시 쓴다).
    이 사건의 서류만 다룬다. 분석 중에 지워진 서류는 건너뛴다.
    """

    def __init__(self, session_factory: sessionmaker[Session], case_id: str) -> None:
        self._session_factory = session_factory
        self._case_id = case_id

    def _evidence(self, db: Session, evidence_id: str) -> Evidence | None:
        evidence = db.get(Evidence, evidence_id)
        if evidence is None or evidence.case_id != self._case_id:
            return None
        return evidence

    def content(self, evidence_id: str) -> bytes | None:
        with self._session_factory() as db:
            if self._evidence(db, evidence_id) is None:
                return None
            file = db.get(EvidenceFile, evidence_id)
            return None if file is None else file.content

    def mark_processing(self, evidence_id: str) -> None:
        with self._session_factory() as db:
            evidence = self._evidence(db, evidence_id)
            if evidence is not None:
                evidence.extract_status = "PROCESSING"
                db.commit()

    def save_extraction(self, evidence_id: str, result: Extraction) -> None:
        with self._session_factory() as db:
            evidence = self._evidence(db, evidence_id)
            if evidence is None:
                return
            evidence.extract_status = result.status
            evidence.extract_method = result.method
            evidence.extracted_text = result.text if result.status == "READY" else None
            evidence.regions_json = result.regions if result.status == "READY" else None
            evidence.low_confidence_regions = result.low_confidence
            evidence.extract_error = result.error
            evidence.extracted_at = utc_now()
            db.commit()

    def save_masked(
        self, evidence_id: str, regions: list[dict[str, Any]], masked_text: MaskedText
    ) -> None:
        with self._session_factory() as db:
            evidence = self._evidence(db, evidence_id)
            if evidence is None or evidence.extract_status != "READY":
                return
            # JSON 칸은 새 목록을 넣어야 바뀐 것으로 저장된다
            evidence.regions_json = [dict(r) for r in regions]
            evidence.masked_text = str(masked_text)
            db.commit()

    def load_extraction(self, evidence_id: str) -> Extraction | None:
        with self._session_factory() as db:
            evidence = self._evidence(db, evidence_id)
            if evidence is None or evidence.extract_status != "READY":
                return None
            return Extraction(
                status="READY",
                method=evidence.extract_method,  # type: ignore[arg-type]
                regions=list(evidence.regions_json or []),
                low_confidence=evidence.low_confidence_regions,
            )


def get_run(db: Session, case: Case, run_id: str, timeout_seconds: float) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    # 다른 사건의 실행은 없는 것과 같게 본다
    if run is None or run.case_id != case.id:
        raise ApiError(404, "NOT_FOUND", "분석 기록을 찾을 수 없습니다.")
    expire_if_overdue(db, run, timeout_seconds)
    return run


def _stages(run: AnalysisRun) -> list[StageOut]:
    keys = [key for key, _ in STAGES]
    current = len(keys) if run.stage == "FINISHED" else keys.index(run.stage)
    out = []
    for i, (key, label) in enumerate(STAGES):
        if i < current:
            status = "DONE"
        elif i == current:
            status = "FAILED" if run.status == "FAILED" else "RUNNING"
        else:
            status = "PENDING"
        out.append(StageOut(key=key, label=label, status=status))
    return out


def to_run_out(run: AnalysisRun) -> AnalysisRunOut:
    error = None
    if run.error_code:
        error = RunError(code=run.error_code, message=run.error_message or "")
    return AnalysisRunOut(
        run_id=run.id,
        status=run.status,
        stage=run.stage,
        stages=_stages(run),
        steps=[StepOut(**step) for step in run.steps_json],
        error=error,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
