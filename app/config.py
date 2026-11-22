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
    # 대조 에이전트 모델·effort(agent-design 5절). Opus 5.5 기본 effort는 medium이라 명시한다
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    # 분석 마감(계약 4.10: 서버는 150초에 스스로 실패 처리)
    analysis_timeout_seconds: float = 150
    # 가짜 분석 단계 사이 쉬는 시간(계약 7절: 4번 화면 진행 표시가 보이게). 테스트는 0
    scripted_stage_delay_seconds: float = 1.0
    # 서비스 전체 하루 AI 분석 한도(계약 1.1·4.1). 표시는 지금, 막는 것은 T11
    daily_analysis_limit: int = 300
    # 글자 추출(T13). 비우면 PATH에서 찾는다(Windows는 설치 경로를 넣는다)
    tesseract_cmd: str | None = None
    pdftoppm_cmd: str | None = None
    ocr_lang: str = "kor+eng"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
