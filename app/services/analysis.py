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
from app.models import AnalysisRun, Case, UsageEvent
from app.schemas.analysis import AnalysisRunOut, AnalysisStart, RunError, StageOut, StepOut
from app.schemas.case import CasePatch
from app.services.cases import update_case
from app.services.clock import utc_now
from app.services.drafts import has_user_edits
from app.services.evidence import list_evidence
from app.services.results import save_output
from app.services.runs import latest_run

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
    """검사 순서: 사연 저장 → 사전 조건 422 → 실행 중 409 → 고친 초안 409 → 실행 시작."""
    if payload.narrative is not None:
        # 저장된 값과 다를 때만 inputVersion +1(계약 4.5와 같은 규칙)
        update_case(db, case, CasePatch(narrative=payload.narrative), today)
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
                # 가짜 분석은 외부 AI를 부르지 않는다. 실제 호출 여부는 T11·T16에서 다듬는다
                ai_called=settings.agent_llm == "claude",
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
            EvidenceRef(e.id, e.doc_type, e.original_name) for e in list_evidence(db, case.id)
        ),
        deadline=time.monotonic() + settings.analysis_timeout_seconds,
        stage_delay_seconds=settings.scripted_stage_delay_seconds,
    )
    threading.Thread(
        target=_run_in_background,
        args=(session_factory, ctx),
        name=f"analysis-{run.id[:8]}",
        daemon=True,
    ).start()
    return run


def _run_in_background(session_factory: sessionmaker[Session], ctx: RunContext) -> None:
    recorder = DbRecorder(session_factory, ctx.run_id)
    try:
        output = runner.execute(ctx, recorder)
    except RunStopped:
        logger.info("분석 %s: 밖에서 끝난 실행이라 멈춤", ctx.run_id)
        return
    except AgentError as exc:
        recorder.finish(exc)
        return
    except Exception:
        # 내부 내용은 로그에만 남기고 화면에는 공통 문구를 준다
        logger.exception("분석 %s 실패", ctx.run_id)
        recorder.finish(AgentError())
        return
    try:
        recorder.finish(None, output)
    except Exception:
        logger.exception("분석 %s 결과 저장 실패", ctx.run_id)
        recorder.finish(AgentError())


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


def _finish_run(db: Session, run: AnalysisRun, error: AgentError | None) -> bool:
    """실행을 끝낸다. 아직 `RUNNING`일 때만 바꾸고, 바꿨으면 True.

    상태 조건을 UPDATE 문에 넣어, 시간 초과 처리와 스레드의 마무리가 겹쳐도 한쪽만 반영되게 한다.
    바꾸지 못했으면 세션에 넣어 둔 결과 행도 버린다(롤백).
    """
    values: dict[str, Any] = {"finished_at": utc_now()}
    if error is None:
        values |= {"status": "SUCCEEDED", "stage": "FINISHED"}
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

    def finish(self, error: AgentError | None, output: AnalysisOutput | None = None) -> None:
        with self._session_factory() as db:
            run = db.get(AnalysisRun, self._run_id)
            if run is None or run.status != "RUNNING":
                return
            if error is None and output is not None:
                save_output(db, run, output)
            _finish_run(db, run, error)


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
