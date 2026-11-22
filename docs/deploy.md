# 🚀 배포 안내 (Render + Neon)

T18에서 정한 배포 방법이다(11/22). 처음 하는 사람도 따라 할 수 있게 순서대로 적는다.

```
[GitHub dev 브랜치] --머지 후 Manual Deploy--> [Render: Dockerfile로 이미지 만들고 실행] <--요청-- [FE (Cloudflare)]
                                              |
                                              +--저장·조회--> [Neon: Postgres DB]
```

- **Render**: 서버를 돌리는 곳. 레포의 `Dockerfile`로 이미지를 만든다(파이썬 + Tesseract 한국어 + poppler)
- **Neon**: DB. Render 무료 서버는 재시작하면 디스크를 지우므로 데이터와 증빙 파일은 모두 DB에 둔다
- **비밀값(DB 주소, API 키)은 Render 환경변수에만** 넣는다. 레포·대화·캡처에 남기지 않는다(원칙 5)

**지금 상태(11/22):** 공개 주소 https://proofy-server.onrender.com · Render **Starter**(15시대 Free에서 전환) · `AGENT_LLM=claude` · 머지 후 Manual Deploy

## 🗄️ 1. Neon — DB 만들기

1. https://neon.com 가입
2. 새 프로젝트: 이름 `proofy`, Postgres 버전은 기본값, **지역 AWS Asia Pacific (Singapore)**
3. 대시보드의 **Connect** → 접속 주소(`postgresql://…neon.tech/…?sslmode=require`)를 복사한다
   - **Connection pooling은 끈 주소(직접 연결)** 를 쓴다. 서버 프로세스가 1개라 풀러가 필요 없고, 풀러를 거치면 드라이버의 준비된 문장(prepared statement)과 부딪칠 수 있다
   - 주소 앞부분이 `postgresql://`여도 그대로 넣으면 된다(서버가 드라이버 주소로 바꾼다)

## 🖥️ 2. Render — 서버 만들기

1. https://render.com 에 **GitHub 계정으로** 가입
2. **New → Web Service** → GitHub 연결에서 `proofy-ai` 조직의 `proofy-server` 레포 접근을 허용한다
   - 조직 레포라 **조직 Owner 권한**이 있어야 허용할 수 있다. 없으면 Owner에게 요청
3. **설정**
   - **Name:** `proofy-server`(공개 주소가 `https://proofy-server-xxxx.onrender.com` 모양이 된다)
   - **Region:** **Singapore**(Neon과 같은 곳)
   - **Branch:** `dev`(제출 전에 `main`으로 바꾼다)
   - **Language / Runtime:** **Docker**
   - **Instance Type:** **Free**로 시작했고 11/22 **Starter**로 바꿨다(실제 분석 128초 → 57초)
   - **Health Check Path** (Advanced): `/api/v1/health`
   - **Auto-Deploy:** 동작 안 함(아래 4절 "PR을 머지했다"). 11/22 확인: `proofy-ai` 조직에 Render GitHub 앱이 없어 공개 레포 주소로 연결됨
4. **Environment Variables**
   - **`DATABASE_URL`** (비밀값): Neon에서 복사한 주소
   - **`CORS_ORIGINS`:** FE 주소(예: `https://proofy-fe.pages.dev`). 여러 개면 쉼표. FE 주소를 받기 전에는 `http://localhost:5173`
   - **`AGENT_LLM`:** `claude`(처음에는 `scripted`로 시작해 T16 뒤 바꿈)
   - **`ANTHROPIC_API_KEY`** (비밀값): `AGENT_LLM=claude`일 때
   - **`DEMO_MODE`:** `true`
   - **`DAILY_ANALYSIS_LIMIT`:** `300`
   - **`RATE_LIMIT_CASES_PER_IP_HOUR`:** 넣지 않음(기본 100, 11/22 20에서 올림). 같은 IP 사건 생성 시간당 한도. 리허설·심사장에서 같은 와이파이로 더 많이 만들면 올린다
   - **`RATE_LIMIT_RUNS_PER_CASE_HOUR`:** 넣지 않음(기본 5). 사건당 분석 시간당 한도
   - **`IP_HASH_SECRET`:** 넣지 않아도 됨. 비우면 서버가 켜질 때 임의 값(재시작하면 지난 1시간 한도 기록과 안 이어짐)

   `PORT`는 Render가 넣어 주고 서버가 그 값을 쓴다. `TESSERACT_CMD`·`PDFTOPPM_CMD`는 이미지에 설치돼 있어 비워 둔다.

5. **Create Web Service** → 빌드 로그가 흐른다(처음 몇 분). `Your service is live`가 나오면 끝
6. 확인: 브라우저에서 `https://<공개 주소>/api/v1/health` → `{"status":"ok", …}`

## 🔗 3. FE와 연결

- FE 담당에게 공개 주소를 준다 → FE 빌드 환경변수 `VITE_API_ORIGIN`
- FE의 고정 도메인(Cloudflare, 미리보기 주소 제외)을 받아 Render `CORS_ORIGINS`에 넣는다. 환경변수를 바꾸면 Render가 다시 배포한다

## 🧯 4. 운영 중에 알아 둘 것

- **PR을 dev에 머지했다**
  - 자동 배포가 안 된다(11/22 확인, 위 Auto-Deploy)
  - Render 서비스 화면 **Manual Deploy → Deploy latest commit** → Events에 그 커밋이 **Deploy live**인지 확인
- **사건이 24시간 뒤 사라졌다**
  - 정상(계약 2절 ④). 서버가 켜질 때와 10분마다 만료 사건을 DB에서 지운다(T11-b)
- **`429 RATE_LIMITED`가 난다**
  - 같은 IP 사건 생성 시간당 100회 또는 사건당 분석 시간당 5회를 넘었다
  - 시연 중이면 환경변수 값을 올리고 저장(서버 재시작)
- **무료(Free) 서버는 15분 동안 요청이 없으면 잠든다.** 첫 요청이 약 1분 걸림
  - 시연·심사 직전에 `/api/v1/health`를 한 번 열어 깨워 둔다. 지금은 Starter라 잠들지 않는다
- **DB 표 구조가 바뀌는 작업을 머지했다**(Alembic 없음, T18 결정 ②)
  - Neon **SQL Editor**에서 `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` 실행
  - Render에서 **Manual Deploy → Deploy latest commit**(서버가 켜지며 표를 새로 만든다)
  - 데이터는 합성이라 지워도 된다
- **배포가 실패했다**
  - Render 서비스 화면의 **Logs**·**Events**를 본다
  - 빌드 단계 실패면 Dockerfile·의존성, 실행 단계 실패면 환경변수(특히 `DATABASE_URL`)
- **제출 전**
  - Render **Settings → Branch**를 `main`으로 바꾸고 다시 배포

## 🐳 5. 로컬에서 같은 이미지 시험하기

```bash
docker build -t proofy-server:local .
docker run --rm -p 8080:8080 -e DATABASE_URL=sqlite:////tmp/proofy.sqlite3 proofy-server:local
```

Postgres까지 맞춰 보려면 `postgres:17` 컨테이너를 같은 Docker 네트워크에 띄우고 `DATABASE_URL=postgresql://postgres:<비밀번호>@<컨테이너 이름>:5432/<DB>`로 연결한다(11/22 T18 리허설 방식).
