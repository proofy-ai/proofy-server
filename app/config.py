"""환경변수 설정. 키·비밀값은 `.env` 또는 환경변수로만 받는다(CLAUDE.md 원칙 5)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./proofy.sqlite3"
    # 쉼표로 구분한 FE 주소 목록
    cors_origins: str = "http://localhost:5173"
    # scripted: Claude를 부르지 않는 가짜 분석(계약 7절), claude: 실제 분석
    agent_llm: Literal["scripted", "claude"] = "scripted"
    demo_mode: bool = True
    anthropic_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
