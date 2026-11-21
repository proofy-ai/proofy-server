# T18 Docker·배포

- 단계: 4단계 배포·마무리 · 예정: 11/22 새벽(T14 앞으로 당김) · 상태: 진행 중 · 이슈: #20 · PR: 없음

## 범위

- Dockerfile(Tesseract 한국어, poppler 포함)
- 배포 환경 결정과 배포, Postgres, 환경변수(키는 환경변수로만)
- FE 배포 주소 CORS 등록
- ~~Alembic 도입~~ → 미룸(11/22 결정 ②, T22로 분리)
- 배포 DB에 증빙 파일이 들어가므로(`evidence_files`) 용량 확인. 서버 디스크에 영구 저장을 기대하지 않는다
- CORS: FE Cloudflare 고정 도메인만(미리보기 주소 제외), 개발·운영 서버 주소를 FE에 공유
- 서버 포트: 로컬과 같은 8080을 기본으로 하고, 호스팅이 `PORT` 환경변수를 주면 그 값을 쓴다
- 환경변수: `IP_HASH_SECRET`, 한도 3종(T11), `CORS_ORIGINS`, `ANTHROPIC_API_KEY`

## 제외

- 없음

## 완료 조건

- 공개 주소에서 `/health` 응답, 체험 계정으로 처음부터 끝까지 동작

## 구현 계획

11/22 사용자와 논의: 배포를 저녁에서 **지금(T14 전)으로 앞당긴다.** 배포해야만 드러나는 문제(조직 권한, Postgres, 무료 서버 OCR 속도, CORS, 잠듦)를 하루 일찍 찾기 위해서다. 가짜 분석(`scripted`)으로 먼저 띄우고, T14~T16은 머지할 때마다 자동 배포로 실서버에서 확인한다.

### 순서

| # | 누가 | 내용 | 파일·장소 |
|---|---|---|---|
| 1 | Claude | **Dockerfile**: python 3.12-slim + `tesseract-ocr` `tesseract-ocr-kor` `poppler-utils`(11/22 OCR 확인 이미지와 같은 구성) + `uv sync --locked --no-dev`. 실행 `python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers`(작업자 1개: 분석 스레드·사건 잠금이 프로세스 1개 전제). `.dockerignore`로 `etc/`·`.env`·`.venv`·`*.sqlite3`·`tests/` 제외 | `Dockerfile`, `.dockerignore` |
| 2 | Claude | **Postgres 연결**: `psycopg[binary]` 추가. Neon이 주는 `postgresql://…` 주소를 그대로 넣어도 되게 `postgresql+psycopg://`로 바꿔 씀. `pool_pre_ping`(Neon은 쉬면 연결을 끊음) | `app/db.py`, `pyproject.toml` |
| 3 | Claude | **로컬 리허설**: 이 PC Docker에서 Postgres 컨테이너 + 우리 이미지를 띄워 실제 흐름 확인(health, 체험 계정 두 개, 서류 내려받기·올리기, 가짜 분석, 결과·초안 저장, `AGENT_LLM=claude`로 실제 글자 추출, 사건 삭제). 스크립트는 스크래치(레포에 안 남김) | — |
| 4 | Claude | **배포 안내서**: Neon·Render 화면에서 누를 곳, 환경변수 표, 문제 생길 때 확인할 곳 | `docs/deploy.md` |
| 5 | 사용자 | **계정 준비**(1~4와 동시에): Neon 가입 → 프로젝트(AWS 싱가포르) → 접속 주소 확보. Render 가입(GitHub 로그인) → `proofy-ai` 조직 레포 접근 허용(**조직 Owner 권한 필요**) | Neon·Render 화면 |
| 6 | 같이 | Render 웹 서비스 만들기(레포, 브랜치 `dev`, Docker, 싱가포르, Free, 상태 확인 경로 `/api/v1/health`) → 환경변수 입력 → 첫 배포 | Render 화면 |
| 7 | Claude | **공개 주소 확인**: 3번과 같은 흐름을 공개 주소로. 잠깐 `AGENT_LLM=claude`로 바꿔 **무료 서버의 OCR 시간 측정** 후 `scripted`로 되돌림 | — |
| 8 | 사용자 | FE 담당에게 공개 주소 전달(`VITE_API_ORIGIN`), FE Cloudflare 주소를 받아 Render `CORS_ORIGINS`에 입력 | — |

### 테스트

- 계약 테스트 없음(응답 모양 변경 없음)
- DB 주소 바꾸기(`postgres://`·`postgresql://` → `postgresql+psycopg://`, SQLite는 그대로) 단위 테스트
- Postgres 동작은 3·7번 리허설로 확인(결과를 "결과"에 기록)

### 정할 것

1. **호스팅: Render 무료 + Neon 무료, 둘 다 싱가포르**(추천, 11/22 논의). 무료 Render는 15분 요청이 없으면 잠들고 깨는 데 약 1분 → 시연 직전 미리 열어 두기. 7번 측정에서 OCR이 너무 느리면 그때 유료($7) 검토
2. **Alembic은 미룬다**(추천). 동결 전까지 표가 바뀌면 배포 DB 표를 지우고 서버가 다시 만들게 한다(데이터는 합성이고 24시간 뒤 지워짐). Alembic 도입은 새 작업으로 빼서 동결 뒤 시간이 남을 때만. CLAUDE.md·ERD의 "T18에서 Alembic" 문장을 함께 고친다
3. **배포 브랜치: 동결 전 `dev`, 제출 전 `main`으로 전환**(추천)
4. **Render 설정은 화면에서 직접**(추천). 설정 파일(`render.yaml`)로도 가능하지만 처음 하는 배포라 화면이 더 이해하기 쉽고, 안내서에 기록을 남긴다
5. **시간 상한:** 2시간(계정 준비 포함)

## 결정

- 11/22 사용자: 배포를 T14 앞으로 당긴다(선택지 A. B 절충안, C 원래 계획과 비교). Dockerfile은 남은 작업(T14~T17)으로 바뀔 것이 거의 없고(파이썬 의존성은 `uv.lock`, 키는 환경변수), 일찍 하는 이유는 배포에서만 드러나는 위험(조직 권한, 무료 서버 OCR 속도, Postgres, CORS)을 하루 일찍 찾기 위해서다. 대가는 실제 Claude 첫 실행이 약 15:00로 밀리는 것
- 11/22 사용자 "A로 하자": 정할 것 1~5 추천안대로. ① Render 무료 + Neon 무료, 싱가포르(TiDB는 행 6MiB 기본 상한 때문에 10MB 서류 저장이 막힐 수 있어 제외) ② Alembic 미룸. 동결 전까지 표가 바뀌면 배포 DB 표를 지우고 다시 만든다. 도입은 T22로 분리 ③ 배포 브랜치 `dev`, 제출 전 `main` ④ Render 설정은 화면에서, 기록은 `docs/deploy.md` ⑤ 2시간

## 결과

- 코드(PR 1): `Dockerfile`(python 3.12-slim + tesseract-ocr-kor + poppler, `uv sync --locked --no-dev`, 비루트 사용자, `PORT`·프록시 헤더), `.dockerignore`, `psycopg[binary]`, `app/db.py` 주소 바꾸기·`pool_pre_ping`, `docs/deploy.md` 안내서, 단위 테스트 `tests/test_t18_deploy.py`
- **로컬 리허설(11/22, Docker `postgres:17` + 이미지, `PORT=10000`):** 점검 스크립트(스크래치) 20개 항목 모두 통과 — health, CORS 사전 요청, 샘플 5개 내려받기(attachment), 두 시나리오 샘플 사건·분석·결과·초안 저장, 직접 만든 사건에 서류 올리기, 삭제. `AGENT_LLM=claude`로 실제 추출: GOODS 7.0초(PDF 12줄, 대화 18줄, 사업자 15줄), UNEXPECTED 3.2초, Postgres `regions_json`에 한글 정상(대화 12번 줄 "3개 12만원에 할게요"). 메모리 약 103MB(무료 512MB 안)
- `uv run python -m pytest -q` 114 passed·2 skipped, ruff 통과
- 남은 것: Render·Neon 연결(사용자), 공개 주소 점검과 무료 서버 OCR 시간 측정, FE 주소 CORS

