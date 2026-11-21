"""DB 연결. 엔진과 세션 팩토리는 앱마다 만들어 `app.state`에 둔다(테스트는 임시 DB를 쓴다)."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


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
