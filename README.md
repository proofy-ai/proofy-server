# Proofy Server

> 지급정지된 계좌의 명의인(청년)이 은행에 낼 **이의제기 서류를 준비하도록 돕는** 웹앱의 백엔드와 AI 에이전트

2026 대한민국 청년 CAREER FAIR AI 해커톤 출품작입니다. **시연용 프로토타입**이라 합성 데이터만 받습니다.

---

## 🎯 프로젝트 소개

보이스피싱 피해금이 내 계좌로 들어오면, 나도 모르게 계좌 전체가 지급정지됩니다. 풀려면 명의인이 직접 은행에 이의제기를 하고 "사기에 쓰인 계좌가 아니다"를 서류로 소명해야 합니다. 하지만 사회초년생은 어떤 서류가 필요한지, 소명서를 어떻게 써야 하는지 알기 어렵고, 기한(공고일 기준 2개월)도 놓치기 쉽습니다.

Proofy는 사용자의 사연과 올린 서류를 AI가 직접 읽고 맞대어 보고, 법령을 찾아 근거를 대며, 부족한 사실은 되묻습니다. 그 결과로 **소명서 초안과 부족한 서류 목록**을 만들어 줍니다. 접수와 심사는 은행이 하고, **AI는 해제 여부를 판정하지 않습니다.**

### 핵심 가치

- 🧭 **기한을 놓치지 않게**: 공고일로 이의제기 마감일과 D-day를 계산해 모든 화면에 보여 줍니다
- 🔍 **AI가 직접 조사**: 사연과 거래내역·대화내역·문자를 대조해 "자료와 맞음 / 어긋남 / 진술만 있음"으로 정리합니다
- ⚖️ **법령을 찾아 읽고 되묻기**: 통신사기피해환급법 조항을 찾아 읽고, 부족한 사실은 채팅으로 묻습니다
- ✍️ **바로 쓸 수 있는 초안**: 입금 경위 · 가담하지 않았다는 설명 · 피해 경위 세 묶음의 소명서 초안을 문장마다 근거와 함께 줍니다
- 🛡️ **지어낸 것은 코드가 걸러 냄**: 숫자·날짜는 코드가 만들고, AI가 쓴 인용·근거는 원문과 대조해 표시합니다

---

## 🚀 바로 체험하기

- **웹앱:** https://proofy-app.pages.dev
- **API 서버:** https://proofy-server.onrender.com/api/v1/health
- **FE 레포:** https://github.com/proofy-ai/proofy-fe

첫 화면(로그인)에서 **체험 계정 test01·test02** 중 하나를 고르고 "로그인"을 누르면, 합성 서류가 채워진 사건이 바로 만들어집니다. 비밀번호는 없습니다. 사건은 브라우저마다 따로 만들어져 다른 사람과 섞이지 않고, 같은 브라우저에서 다시 들어오면 그 사건을 이어서 씁니다(다시 시작하면 새로 만듦).

서류 화면에서 "분석 시작" → 분석 진행 화면 → 프루피 채팅에서 AI 질문에 답하기(체험 계정은 예시 답이 채워져 있음) → 다시 분석 → 결과 화면 순서로 진행됩니다.

- **test01 · 물품 거래:** 청년 1인 온라인 판매 사업자가 물건값으로 받은 돈이 피해금인 경우
  - 대화 속 합의 금액(12만 원)과 실제 입금액(15만 원)이 달라 AI가 어긋남을 찾고 이유를 묻습니다
- **test02 · 모르는 입금(통장 묶기):** 모르는 사람이 10만 원을 보낸 뒤 허위 신고하고 "20만 원 보내면 신고 취하해 줄게" 문자를 보낸 경우
  - 사연의 입금일(11/11)과 거래내역(11/12)이 달라 AI가 어긋남을 찾고 이유를 묻습니다
  - 협박 문자를 근거로 정리하고, 진술만 있는 "은행에 바로 알렸다"는 추가 자료를 권합니다

---

## ✨ 주요 기능

### 1. 사건 만들기와 기한 계산
- 📅 지급정지 통지일·공고일로 이의제기 마감일과 D-day 계산(공고일을 모르면 "확인 필요")
- 🗂️ 입금 유형(급여 · 물품 거래 · 모르는 입금)별 필요한 서류 체크리스트
- 🧪 체험 계정: 합성 서류가 채워진 샘플 사건을 버튼 하나로 생성

### 2. 서류 올리기와 글자 읽기
- 📄 거래내역서 PDF는 글자를 바로 읽고, 사진·스캔은 Tesseract OCR로 읽음
- 🙈 이름·계좌·전화번호·사업자번호를 가린 뒤에만 AI에 보냄
- 📊 거래내역서에서 거래 행(날짜·금액·상대)을 규칙으로 뽑음

### 3. AI 분석
- 🗺️ **조사 계획:** 확인할 주장과 볼 자료를 먼저 정하고 화면에 보여 줌
- 🔧 **도구로 조사:** 거래내역 조회 · 서류 글 조회 · 법령 검색 · 조항 읽기를 AI가 스스로 골라 부름(부를 때마다 이유를 밝힘)
- 💬 **질문:** 부족한 사실을 묻는 질문 0~3개(분석이 끝나면 프루피 채팅으로 하나씩 물음)
- 🔁 **답하고 다시 분석:** 사용자가 답하면 지난 분석을 돌아보고 계획을 고쳐 다시 정리
- 📡 **진행 과정 공개:** 분석 중에 단계별 진행과 AI가 한 일을 한 줄씩 보여 줌

### 4. 결과와 초안
- ✅ 주장별 대조표: 자료와 일치 / 어긋남 / 진술만 / 확인 못 함
- 📝 소명서 초안: 세 묶음, 문장마다 근거 연결, 근거 없는 문장은 지우지 않고 "확인 필요" 표시
- ✏️ 초안 편집과 저장(버전 충돌 확인), 문장별 "직접 확인했어요"
- 🖨️ 신청서 완성: 별지 제4호 이의제기신청서에 초안을 채워 PDF로 저장(FE)

### 5. 안전장치
- 🚨 통장 대여·송금 대행으로 읽히는 사연은 소명서 대신 법률 상담 안내(대한법률구조공단 132, 금융감독원 1332)
- ⏱️ 시간당·하루 분석 한도, 샘플 사건은 AI가 실패해도 미리 만든 결과로 시연이 멈추지 않음
- 🗑️ 모든 사건은 만든 지 24시간 뒤 자동 삭제

---

## 🤖 AI 에이전트는 이렇게 일합니다

```text
① 글자 읽기    [코드]  OCR → 개인정보 가리기 → 거래 행 정리
② 대조        [AI]    조사 계획 → 도구로 조회·법령 확인(이유 필수) → 대조·질문
              [코드]  조회한 거래만 인정, 인용을 원문과 대조, 계획대로 다 했는지 점검
③ 초안        [AI]    검증을 통과한 사실과 답변만으로 초안 작성
④ 검증        [코드 → AI 1회 → 코드]  숫자·판정 표현 검사 → 고칠 수 있는 것만 AI가 고쳐 쓰기 → 재검사
⑤ 질문에 답   → 답과 "지난 분석에서 어긋난 것·못 확인한 것"을 넘겨 처음부터 다시
```

- **모델:** Claude(`claude-opus-5-5`), Messages API 위에 직접 짠 도구 루프(프레임워크 없음)
- **쓴 기법:** 계획(CoT), 생각 → 도구 → 관찰 반복(ReAct), 검증 결과를 돌려받아 고쳐 쓰기와 지난 분석 돌아보기(Reflexion)
- **쓰지 않은 기법:** ToT·멀티 에이전트(150초 마감·비용에 맞지 않고, 갈래를 늘리기보다 검증이 효과적)

자세한 설계는 [`docs/agent-design-v2.md`](docs/agent-design-v2.md)에 있습니다.

---

## 🛡️ 지키는 원칙

1. **AI는 판정하지 않는다:** 자료 대조와 질문까지만 합니다. "해제될 것", "가능성이 높다" 같은 결과 예측은 하지 않고, 출력 스키마에 판정 칸 자체가 없습니다
2. **숫자·날짜·기한은 코드가 만든다:** D-day, 금액, 체크리스트 충족 여부를 AI에 계산시키지 않습니다
3. **근거 없는 문장은 지우지 않고 표시한다:** 인용은 원문과 대조하고, 이번에 조회한 거래만 근거로 인정하며, 다른 사건의 자료는 근거가 될 수 없습니다
4. **실제 개인정보를 외부 AI에 보내지 않는다:** 원본 이미지는 보내지 않고, 가린 글자만 보냅니다. 신분증은 받지 않습니다

---

## 🧱 기술 스택

- **언어·서버:** Python 3.12, FastAPI, Pydantic, SQLAlchemy
- **AI:** Anthropic Claude API(도구 사용, 구조화 출력)
- **글자 읽기:** pypdf(텍스트 PDF), Tesseract OCR 한국어 + poppler(이미지·스캔)
- **DB:** 로컬 SQLite, 배포 Postgres(Neon)
- **배포:** Docker, Render(서버), Cloudflare Pages(FE)
- **품질:** pytest(계약 테스트 포함), ruff, GitHub Actions

### 코드 구조

```text
app/
  api/        HTTP 라우터(업무 로직 없음)
  schemas/    요청·응답 모양(API 계약과 1:1)
  models/     DB 테이블
  services/   코드가 만드는 것: D-day, 체크리스트, 증빙 저장, 한도, 자동 삭제, 상담 안내 후보
  agent/      AI 분석: 실행·단계, 글자 추출, 가리기, 거래 행, 대조, 초안, 검증, 법령, LLM 호출
  samples/    체험 계정 합성 서류
tests/        계약 테스트와 기능 테스트
docs/         문서(아래)
```

폴더마다 맡은 일과 분석 한 번이 거치는 파일은 [`docs/architecture.md`](docs/architecture.md)에 정리했습니다.

---

## 📚 문서

어떤 문서를 언제 읽으면 되는지는 [`docs/README.md`](docs/README.md)에 정리했습니다.

- [`docs/screen-flow.md`](docs/screen-flow.md): 화면과 사용자 흐름
- [`docs/agent-design-v2.md`](docs/agent-design-v2.md): AI 에이전트 설계
- [`docs/architecture.md`](docs/architecture.md): 코드 구조(폴더별 역할)
- [`docs/contract.md`](docs/contract.md): FE–BE API 계약(정본)
- [`docs/erd.md`](docs/erd.md): 데이터 모델(정본)
- [`docs/deploy.md`](docs/deploy.md): 배포 방법
- [`docs/tasks/README.md`](docs/tasks/README.md): 작업 계획과 진행 상태

---

## 🛠️ 로컬에서 실행하기

[uv](https://docs.astral.sh/uv/)가 필요합니다. Python 3.12는 uv가 알아서 받습니다.

```bash
uv sync                       # 의존성 설치
cp .env.example .env          # 설정 (필요하면 값 수정)
uv run python -m uvicorn app.main:app --reload --port 8080
```

- 상태 확인: http://localhost:8080/api/v1/health
- API 문서(OpenAPI): http://localhost:8080/docs
- 기본값은 가짜 분석 모드(`AGENT_LLM=scripted`)라 API 키 없이 전체 흐름이 돕니다

### 테스트와 린트

```bash
uv run python -m pytest
uv run ruff check .
```

테스트는 API 키 없이 가짜 분석 모드로 돕니다. PR마다 GitHub Actions가 같은 명령을 실행합니다.

### 환경변수

`.env.example`을 복사해 씁니다. 키는 `.env`나 환경변수에만 넣고 레포에 올리지 않습니다.

- **`DATABASE_URL`** (기본 `sqlite:///./proofy.sqlite3`): 배포는 Postgres
- **`CORS_ORIGINS`** (기본 `http://localhost:5173`): 쉼표로 구분한 FE 주소
- **`AGENT_LLM`** (기본 `scripted`): `scripted`는 가짜 분석, `claude`는 실제 분석
- **`ANTHROPIC_API_KEY`**: `AGENT_LLM=claude`일 때만 필요
- **`DEMO_MODE`** (기본 `true`): 시연용 안내 표시
- **한도:** `DAILY_ANALYSIS_LIMIT`(하루 분석, 300), `RATE_LIMIT_CASES_PER_IP_HOUR`(IP당 사건 생성, 시간당 100), `RATE_LIMIT_RUNS_PER_CASE_HOUR`(사건당 분석, 시간당 5)
- **자동 삭제:** `CLEANUP_INTERVAL_SECONDS`(만료 사건 정리 주기, 600초), `IP_HASH_SECRET`(IP 해시 비밀값, 비우면 임의 값)
- **글자 인식:** `TESSERACT_CMD`·`PDFTOPPM_CMD`(비우면 PATH에서 찾음), `OCR_LANG`(기본 `kor+eng`, 한글 데이터 `tesseract-ocr-kor` 필요)

알아 둘 것

- 글자 추출은 `AGENT_LLM=claude`일 때만 돕니다. 인식 프로그램이 없으면 그 서류만 "읽지 못함"으로 두고 분석은 계속합니다. 한 파일을 확인하려면 `uv run python -m app.agent.extract 파일`
- DB 테이블은 서버가 시작할 때 만듭니다. 스키마가 바뀌면 로컬 DB 파일(`proofy.sqlite3`)을 지우고 다시 실행합니다

### 체험 계정 합성 서류 다시 만들기

`app/samples/`의 서류(거래내역서 PDF, 대화·협박 문자·사업자등록증명 PNG)는 모두 지어낸 인물·번호·기관으로 만든 **합성 데이터**이고, 서류마다 그렇게 표시되어 있습니다. 스크립트로 만들어 결과 파일을 커밋했습니다.

```bash
uv run python -m scripts.make_samples                       # Windows 기본 글꼴 경로
uv run python -m scripts.make_samples --font NotoSansKR.ttf # 다른 경로
```

- 글꼴은 [Noto Sans KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR)(SIL Open Font License 1.1)이며 레포에는 넣지 않았습니다
- 거래 행과 인용 문구는 가짜 분석기(`app/agent/scripted.py`)의 값과 같습니다

### Windows에서 실행이 막힐 때

스마트 앱 컨트롤 같은 애플리케이션 제어 정책이 켜진 PC에서는 다음 두 가지가 막힐 수 있습니다.

- **가상환경 실행 파일**(`uv run pytest`, `uv run uvicorn`): 위처럼 `uv run python -m …`으로 실행합니다
- **SQLAlchemy 컴파일 확장**(`ImportError: DLL load failed … _collections_cy`): 컴파일 확장 없이 다시 설치합니다

```bash
DISABLE_SQLALCHEMY_CEXT=1 uv sync --no-binary-package sqlalchemy --reinstall-package sqlalchemy
```
