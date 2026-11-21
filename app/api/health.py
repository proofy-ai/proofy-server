from fastapi import APIRouter, Request

from app.schemas.common import CamelModel

router = APIRouter()


class HealthResponse(CamelModel):
    status: str
    agent: str
    demo_mode: bool


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """계약 4.1. 시연 전에 분석 모드(`scripted`/`claude`)를 확인하는 용도."""
    settings = request.app.state.settings
    return HealthResponse(status="ok", agent=settings.agent_llm, demo_mode=settings.demo_mode)
