# T01 프로젝트 뼈대

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: PR · 이슈: #3 · PR: #22

## 범위

- 전체 폴더 구조와 모듈 규칙을 정하고 `CLAUDE.md`에 적는다. 이후 작업은 정해진 자리를 채운다
- uv 프로젝트(`pyproject.toml`, `uv.lock`), Python 3.12 고정
- 공통 파일: 앱 생성, 설정(`.env`), DB 연결, 공통 오류 응답(계약 1.1), CORS(계약 1절), camelCase 응답 기본 모델
- `GET /api/v1/health`(계약 4.1)
- CI: GitHub Actions에서 린트(ruff) + 테스트(pytest)
- 이슈 템플릿(작업·버그)과 PR 템플릿(`.github/`). `shinhands2` 구조를 참고해 Proofy 규칙에 맞춤
- README와 `CLAUDE.md`에 실행·테스트 명령

## 제외

- 업무 API와 테이블(T02~)
- 각 작업 자리의 빈 파일은 미리 만들지 않는다(폴더와 `__init__.py`만)
- 자동 배포(T18), 타입 검사, 커버리지 기준, "CI 통과해야 머지" 강제

## 완료 조건

- `uv run uvicorn app.main:app --reload`로 서버가 뜨고 `/api/v1/health`가 계약 모양으로 응답
- `uv run ruff check .`, `uv run pytest` 통과
- PR에서 CI가 돈다

## 구현 계획

### 폴더 구조

```text
app/
  main.py          앱 생성, CORS, 오류 처리 등록, 라우터 등록, 시작 시 테이블 생성
  config.py        환경변수 설정(pydantic-settings)
  db.py            엔진, 세션, Base, 요청별 세션 의존성
  errors.py        ApiError와 오류 응답 처리(계약 1.1)
  api/             HTTP 라우터만. 요청을 받아 서비스를 부르고 스키마로 돌려준다
    health.py
  schemas/         요청·응답 모양. 계약과 1:1, camelCase
    common.py      CamelModel 기본 클래스
  models/          DB 테이블 (T03~)
  services/        코드가 만드는 것: 토큰, D-day, 서류 목록, 체크리스트, 증빙 저장,
                   샘플 사건, 한도, 자동 삭제, 상담 안내 검사 (T02~)
  agent/           AI 분석 (T07~)
    runner.py         분석 실행·단계 기록 (T07)
    scripted.py       가짜 분석기 (T08)
    extract/          글자 추출 (T13)
    masking.py        개인정보 마스킹 (T14)
    transactions.py   거래 행 추출 (T15)
    compare.py        대조 에이전트 (T16)
    drafting.py, verify.py  초안·후검증 (T17)
    llm.py            Claude 호출 (T16)
  samples/         체험 계정 시나리오 데이터·서류 (T06, T12)
tests/
  conftest.py      테스트용 앱·임시 DB·클라이언트
.github/workflows/ci.yml
pyproject.toml · uv.lock · .python-version · .env.example · README.md
```

T01에서 실제로 만드는 파일은 `main.py`, `config.py`, `db.py`, `errors.py`, `api/health.py`, `schemas/common.py`, 각 폴더의 `__init__.py`, `tests/`, CI, 설정 파일뿐이다. 나머지는 괄호 안 작업에서 만든다.

### 모듈 규칙 (`CLAUDE.md`에 적는다)

- 호출 방향은 `api → services → models` 한쪽뿐이다. 라우터에는 업무 로직을 넣지 않는다
- AI 분석은 `agent/runner.py` 한 곳으로만 들어간다
- **외부 AI 호출은 `agent/llm.py` 한 곳에서만 한다.** 마스킹을 거친 글자만 받게 만든다(원칙 4)
- 숫자·날짜·충족 여부는 `services/`가 만들고 `agent/`는 계산하지 않는다(원칙 2)

### 공통 동작

- 설정 값: `DATABASE_URL`(기본 `sqlite:///./proofy.sqlite3`), `UPLOAD_DIR`(기본 `uploads`), `CORS_ORIGINS`(기본 `http://localhost:5173`), `AGENT_LLM`(기본 `scripted`), `DEMO_MODE`(기본 `true`), `ANTHROPIC_API_KEY`(선택, T16부터)
- 오류 응답: 모든 4xx/5xx를 `{ "error": { "code", "message", "details" } }`로 바꾼다
  - 직접 던지는 `ApiError(status, code, message, details)`
  - 요청 형식 오류 → 400 `VALIDATION_ERROR`, `details.fields`에 `{필드: 사유}`
  - 없는 경로 → 404 `NOT_FOUND`
  - 처리하지 못한 예외 → 500 `INTERNAL`(내부 내용은 응답에 넣지 않고 로그로만)
- CORS: `CORS_ORIGINS`만 허용, 허용 헤더 `Content-Type`, `X-Case-Token`
- 응답 모델은 `CamelModel`을 상속해 camelCase로 나간다
- `/health`: `{ "status": "ok", "agent": <AGENT_LLM 값>, "demoMode": <DEMO_MODE> }`

### 도구

- 의존성: `fastapi`, `uvicorn[standard]`, `sqlalchemy`(2.x), `pydantic`(2.x), `pydantic-settings`
- 개발 의존성: `pytest`, `httpx`(테스트 클라이언트), `ruff`
- ruff: 기본 규칙 + import 정렬, 줄 길이 100
- CI: `ubuntu-latest`, `astral-sh/setup-uv` → `uv sync --locked` → `uv run ruff check .` → `uv run pytest`. `dev`·`main` 대상 PR과 `dev` push 때 실행. API 키 없음

### 테스트 (계약 관련이라 승인 필요)

| # | 내용 |
|---|---|
| T01-1 | `/api/v1/health`가 `status`, `agent`, `demoMode` 키로 응답 |
| T01-2 | 없는 경로·형식 오류·처리 못 한 예외가 모두 `{error:{code,message,details}}` 모양이고 코드가 404 `NOT_FOUND`·400 `VALIDATION_ERROR`·500 `INTERNAL` |

### 정할 것

- Python 3.12 고정: 로컬에는 3.14가 있지만 배포용 Docker와 맞추기 위해 3.12로 고정한다. uv가 3.12를 내려받는다
- 테이블 생성: 마이그레이션 도구(Alembic) 없이 시작할 때 만든다. 스키마가 바뀌면 로컬 DB 파일을 지우고 새로 만든다

## 결정

- 11/21 구현 계획·테스트 T01-1, T01-2 승인
- 11/21 실행 명령은 `uv run python -m uvicorn …`, `uv run python -m pytest`로 통일. 이 PC의 애플리케이션 제어 정책이 uv가 만든 `uvicorn.exe`·`pytest.exe`를 막는다(`ruff.exe`는 됨). `python -m` 형태는 CI·Docker에서도 같게 돈다
- 11/21 같은 정책이 SQLAlchemy 컴파일 확장(`_collections_cy` 등 `.pyd`)을 막는다. 이 PC에서만 `DISABLE_SQLALCHEMY_CEXT=1 uv sync --no-binary-package sqlalchemy --reinstall-package sqlalchemy`로 순수 파이썬 설치. `uv.lock`·CI는 그대로. README에 대처법 기록
- 11/21 계약 1.1에 없는 4xx(예: 405)는 `VALIDATION_ERROR`로 묶는다
- 11/21 마이그레이션 도구는 Flyway 대신 Alembic(SQLAlchemy 모델과 같이 관리, SQLite·Postgres 동시 지원). 도입은 배포 때(T18). 그 전까지는 시작 시 `create_all`, 스키마가 바뀌면 로컬 DB 파일 삭제
- 11/21 레포 기본 브랜치를 `main` → `dev`로 변경(사용자 요청, `gh repo edit --default-branch dev`). 템플릿과 `Closes #`가 `dev` 머지 기준으로 동작
- 11/21 이슈·PR 템플릿 추가(사용자 제안, PR #22에 포함). `shinhands2`의 Notion 동기화·릴리스 스크립트·여러 워크플로는 가져오지 않음
- 11/21 `app/samples/`는 빈 폴더라 git이 추적하지 않는다. T06에서 만든다

## 결과

- `uv run ruff check .` → All checks passed / `uv run ruff format --check .` → 통과
- `uv run python -m pytest -q` → 4 passed (T01-1 1개, T01-2 3개). 경고 1개: Starlette가 `httpx` 대신 `httpx2`를 권장(동작 영향 없음, 미조치)
- 서버 수동 확인(`uv run python -m uvicorn app.main:app --port 8765`): `/api/v1/health` → `{"status":"ok","agent":"scripted","demoMode":true}`, CORS 사전 요청에 `access-control-allow-headers`에 `X-Case-Token` 포함, 없는 경로 → `{"error":{"code":"NOT_FOUND",…}}`
- CI: PR #22에서 GitHub Actions `test` 통과(10초, run 44883055719)
