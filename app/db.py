"""DB 연결. 엔진과 세션 팩토리는 앱마다 만들어 `app.state`에 둔다(테스트는 임시 DB를 쓴다)."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def normalize_database_url(database_url: str) -> str:
    """호스팅(Neon 등)이 주는 `postgres://`·`postgresql://` 주소를 psycopg 3 드라이버로 바꾼다."""
    for prefix in ("postgres://", "postgresql://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url[len(prefix) :]
    return database_url


def make_engine(database_url: str) -> Engine:
    database_url = normalize_database_url(database_url)
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    # Neon은 한동안 안 쓰면 연결을 끊는다. 꺼내 쓰기 전에 살아 있는지 확인한다
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=not is_sqlite)
    if is_sqlite:
        # SQLite는 FK(ON DELETE CASCADE)를 연결마다 켜야 동작한다
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _record) -> None:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """테이블을 만든다. 마이그레이션 도구는 쓰지 않는다(T01 결정)."""
    import app.models  # noqa: F401  테이블 정의를 Base에 등록

    Base.metadata.create_all(engine)


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


# 라우터·의존성 인자 타입. 같은 요청 안에서는 같은 세션을 쓴다
DbSession = Annotated[Session, Depends(get_db)]
