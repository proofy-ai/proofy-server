"""앱 생성. 라우터는 `/api/v1` 아래에 붙인다(계약 1절)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, cases, checklist, draft, evidence, health, meta, result, samples
from app.config import Settings, get_settings
from app.db import init_db, make_engine, make_session_factory
from app.errors import register_error_handlers
from app.services.cleanup import Cleaner

logging.basicConfig(level=logging.INFO)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
        # 24시간 자동 삭제(T11-b): 켜질 때 한 번, 그 뒤 주기마다
        cleaner = Cleaner(session_factory, settings.cleanup_interval_seconds)
        cleaner.start()
        yield
        cleaner.stop()
        engine.dispose()

    app = FastAPI(title="Proofy API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["Content-Type", "X-Case-Token"],
    )
    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    api.include_router(health.router)
    api.include_router(meta.router)
    # /cases/sample을 /cases/{case_id}보다 먼저 붙인다
    api.include_router(samples.router)
    api.include_router(cases.router)
    api.include_router(evidence.router)
    api.include_router(checklist.router)
    api.include_router(analysis.router)
    api.include_router(result.router)
    api.include_router(draft.router)
    app.include_router(api)
    return app


app = create_app()
