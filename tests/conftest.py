from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    # .env를 읽지 않고 임시 DB를 쓴다(증빙 파일도 DB에 저장한다)
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm="scripted",
        demo_mode=True,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    # 처리 못 한 예외도 500 응답으로 받아 보도록 raise_server_exceptions=False
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
