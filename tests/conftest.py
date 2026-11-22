from collections.abc import Iterator

import anthropic
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch):
    """테스트에서 실제 Claude API를 부르지 않는다(비용·키). 가짜는 `tests/fake_claude.py`."""

    def blocked(*args, **kwargs):
        raise AssertionError("테스트에서 실제 Claude 클라이언트를 만들면 안 됩니다")

    monkeypatch.setattr(anthropic, "Anthropic", blocked)


@pytest.fixture
def settings(tmp_path) -> Settings:
    # .env를 읽지 않고 임시 DB를 쓴다(증빙 파일도 DB에 저장한다)
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm="scripted",
        demo_mode=True,
        # 가짜 분석의 단계 간 쉬는 시간 없이 바로 끝나게
        scripted_stage_delay_seconds=0,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    # 처리 못 한 예외도 500 응답으로 받아 보도록 raise_server_exceptions=False
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def claude_app(tmp_path) -> Iterator[TestClient]:
    """`AGENT_LLM=claude` 서버. 글자 추출 도구는 없는 경로로 둬 텍스트 PDF만 읽는다.

    Claude는 테스트마다 `fake_claude.install`로 가짜 SDK를 넣는다.
    T23부터 공용이고, 앞선 테스트 파일은 각자 정의한다.
    """
    missing = "proofy-no-such-tesseract"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        agent_llm="claude",
        scripted_stage_delay_seconds=0,
        tesseract_cmd=missing,
        pdftoppm_cmd=missing,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c
