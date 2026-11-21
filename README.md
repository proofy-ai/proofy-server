# Proofy Server

지급정지된 계좌의 명의인(청년)이 은행에 낼 이의제기 서류를 준비하도록 돕는 웹앱의 백엔드와 AI 에이전트입니다.
2026 대한민국 청년 CAREER FAIR AI 해커톤 출품작이며, **시연용 프로토타입**입니다. 합성 데이터만 받습니다.

- API 계약: [`docs/contract.md`](docs/contract.md)
- 작업 계획과 진행 상태: [`docs/tasks/README.md`](docs/tasks/README.md)

## 실행

[uv](https://docs.astral.sh/uv/)가 필요합니다. Python 3.12는 uv가 알아서 받습니다.

```bash
uv sync                       # 의존성 설치
cp .env.example .env          # 설정 (필요하면 값 수정)
uv run python -m uvicorn app.main:app --reload --port 8080
```

- 상태 확인: http://localhost:8080/api/v1/health
- API 문서(OpenAPI): http://localhost:8080/docs

## 테스트와 린트

```bash
uv run python -m pytest
uv run ruff check .
```

테스트는 API 키 없이 가짜 분석 모드(`AGENT_LLM=scripted`)로 돕니다. PR마다 GitHub Actions가 같은 명령을 실행합니다.

## 체험 계정 합성 서류

`app/samples/`의 서류(거래내역서 PDF, 대화·협박 문자·사업자등록증명 PNG)는 모두 지어낸 인물·번호·기관으로 만든 **합성 데이터**이고, 서류마다 그렇게 표시되어 있습니다. 스크립트로 만들어 결과 파일을 커밋했습니다. 거래 행과 인용 문구는 가짜 분석기(`app/agent/scripted.py`)의 값과 같습니다.

```bash
uv run python -m scripts.make_samples                       # Windows 기본 글꼴 경로
uv run python -m scripts.make_samples --font NotoSansKR.ttf # 다른 경로
```

글꼴은 [Noto Sans KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR)(SIL Open Font License 1.1)이며 레포에는 넣지 않았습니다. PDF에는 쓴 글자만 들어갑니다.

## Windows에서 실행이 막힐 때

스마트 앱 컨트롤 같은 애플리케이션 제어 정책이 켜진 PC에서는 다음 두 가지가 막힐 수 있습니다.

- `uv run pytest`, `uv run uvicorn`처럼 가상환경에 생긴 실행 파일: 위처럼 `uv run python -m …`으로 실행합니다
- SQLAlchemy의 컴파일된 확장(`ImportError: DLL load failed … _collections_cy`): 컴파일 확장 없이 다시 설치합니다

```bash
DISABLE_SQLALCHEMY_CEXT=1 uv sync --no-binary-package sqlalchemy --reinstall-package sqlalchemy
```

## 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./proofy.sqlite3` | 배포는 Postgres |
| `CORS_ORIGINS` | `http://localhost:5173` | 쉼표로 구분한 FE 주소 |
| `AGENT_LLM` | `scripted` | `scripted`(가짜 분석) 또는 `claude` |
| `DEMO_MODE` | `true` | 시연용 안내 표시 여부(계약 4.1) |
| `ANTHROPIC_API_KEY` | 없음 | `AGENT_LLM=claude`일 때만. 레포에 넣지 않습니다 |

DB 테이블은 서버가 시작할 때 만듭니다. 스키마가 바뀌면 로컬 DB 파일(`proofy.sqlite3`)을 지우고 다시 실행합니다.
