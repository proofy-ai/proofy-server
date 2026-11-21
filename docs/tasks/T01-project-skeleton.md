# T01 프로젝트 뼈대

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 대기 · 이슈: 미등록 · PR: 없음

## 범위

- uv 프로젝트(`pyproject.toml`, `uv.lock`), Python 3.12 고정
- FastAPI 앱, `/api/v1` 접두어, camelCase 응답 기본 설정
- 설정(`.env`, `.env.example`): DB 주소, 업로드 폴더, CORS 주소, `AGENT_LLM`, `DEMO_MODE`
- 공통 오류 응답 모양(계약 1.1), CORS(계약 1절)
- DB 연결(SQLite, 시작 시 테이블 생성). 테이블은 각 작업에서 추가
- `GET /health`(계약 4.1)
- pytest 설정, README와 `CLAUDE.md`에 실행 명령

## 제외

- 사건·증빙 등 업무 API(T03~)

## 완료 조건

- `uv run uvicorn …`으로 서버가 뜨고 `/health`가 계약 모양으로 응답
- `uv run pytest`가 돈다

## 구현 계획

(작업 시작 때 작성하고 확인받는다)

## 결정

## 결과

