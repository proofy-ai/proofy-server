# T11 운영 보호

- 단계: 2단계 가짜 분석 · 예정: 11/22 오후 · 상태: T11-a 완료, T11-b 완료(PR 머지 대기) · 이슈: T11-a #64, T11-b #13 · PR: T11-a #65

## 범위

> 11/22: **T11-a 대체 결과**(아래 셋째 항목, `agentReview` 포함)를 먼저 하고, **T11-b 한도·자동 삭제**(나머지)는 T10 뒤에 한다(`README.md` 11/22 낮 변경).

- IP당 사건 생성 시간당 20회, 사건당 분석 시간당 5회 → 429 `RATE_LIMITED`
- 서비스 전체 분석 하루 300회 → 429 `DAILY_LIMIT`
- 샘플 사건 대체 결과: AI 실패·하루 한도 초과 때 미리 만든 결과로 `SUCCEEDED`, `precomputed: true`, step `FALLBACK`(계약 4.10)
- 생성 24시간 뒤 자동 삭제(만료 사건은 404, 주기 정리)
- 한도·비용은 사건과 분리한 `usage_events`에서 센다(사건 삭제로 줄지 않음, ERD v1.1 3.10). 하루 한도는 `ai_called = true`만, 한국 날짜 기준
- 한도 값은 환경변수(`RATE_LIMIT_CASES_PER_IP_HOUR`·`RATE_LIMIT_RUNS_PER_CASE_HOUR`·`DAILY_ANALYSIS_LIMIT`). `GET /health`의 `dailyUsage` 표시와 `DAILY_ANALYSIS_LIMIT` 설정은 이슈 #40에서 먼저 넣음(`app/services/usage.py`), T11은 한도로 막는 것
- IP 해시는 `HMAC-SHA256(IP_HASH_SECRET, IP)`, 24시간 정리 때 `usage_events.ip_hash`를 NULL로

## 제외

- 없음

## 완료 조건

- 한도·대체 결과가 계약대로 동작

## 구현 계획

### T11-a 대체 결과 (이슈 #64, 브랜치 `feat/64-fallback-result`)

**언제 대체 결과로 끝나나**
- 대상: `isSample`이고 `sample_input_version == input_version`(사연·서류를 안 바꿈). 분석 시작 때 정해 `RunContext.allow_fallback`으로 넘긴다
- ① AI 실패: 분석 스레드에서 `AgentError`(거절·시간 초과·일반 실패)나 예상 못 한 예외, 결과 저장 실패가 나면 실패 대신 대체 결과. `RunStopped`(사건 삭제 등)는 그대로 멈춤
- ② 하루 한도: `AGENT_LLM=claude`이고 오늘 `ai_called` 실행 수가 `DAILY_ANALYSIS_LIMIT` 이상이면 시작 때 판단. 대상이면 AI를 부르지 않고 바로 대체 결과(`ai_called=false`), 아니면 `429 DAILY_LIMIT`(계약 1.1). **이 429는 T11-a에 넣는다**(대체 결과와 한 검사라서). T11-b는 `RATE_LIMITED` 2종 + 자동 삭제만

**대체 결과 만들기**
- 새 함수 `runner.execute_fallback(ctx, rec, failed_out)`(AI 분석 입구는 runner 한 곳). 가짜 분석기(`ScriptedAnalyzer`)를 쉬는 시간 0으로 돌려 출력을 만든다. 시나리오 결과는 이미 가짜 분석기에 있는 고정값(대조·의견·질문·초안)을 그대로 쓴다 = 새 고정 데이터 없음
- 실패한 실행에서 코드가 만든 것(가린 사연, 읽은 글자, 거래 행)과 AI 비용 기록은 이어받고, AI가 만들다 만 대조·의견은 버린다
- 가짜 분석기의 step(조사 계획·거래내역 조회 등)은 **남기지 않는다**(AI가 한 것처럼 보이면 안 됨). 계약 4.10 문구 그대로 `FALLBACK` step 하나만: "미리 만든 결과 사용" / "지금은 AI 분석을 쓸 수 없어 샘플용으로 미리 만든 결과를 보여 드립니다."
- 저장: `analysis_runs.precomputed = true`, `usage_events.precomputed = true`. 결과 API `precomputed`는 이미 실행 값을 그대로 냄
- 시간 초과 경합: 폴링의 `expire_if_overdue`가 먼저 실패로 끝내면 대체 결과를 못 쓴다 → 대상 사건은 AI 마감을 10초 당겨(140초) 대체 결과 만들 시간을 남긴다

**바꿀 파일**
- `app/agent/runner.py`: `RunContext.allow_fallback`, `execute_fallback`, 조용한 기록기
- `app/services/analysis.py`: 대상 판단, 하루 한도 검사(429·바로 대체), 스레드 실패 경로에서 대체, `precomputed` 저장
- `app/services/usage.py`: 주석만(한도 검사가 여기 함수를 씀)
- 계약·ERD 변경 없음(4.10·4.11·1.1에 이미 있음)

**계약 테스트(승인 필요)**
- T11-a-1 AI 실패 대체: 샘플 그대로(GOODS) + Claude 분석기가 실패하도록 바꿔 끼움 → `SUCCEEDED`, 결과 `precomputed: true`, 마지막 step `FALLBACK`(계약 문구), 대조 3개·`agentReview`·초안 있음, step에 가짜 분석기의 조사 계획 줄 없음
- T11-a-2 바꾼 샘플은 대체 안 함: 사연을 고친 샘플 + 같은 실패 → `FAILED`, `error.code` 그대로
- T11-a-3 하루 한도: 한도를 1로, 오늘 `ai_called` 1건이 있을 때 샘플 그대로 → AI 안 부르고 `precomputed: true`(UNEXPECTED), 직접 만든 사건 → `429 DAILY_LIMIT`, 실행 행 안 생김

**정할 것(추천안)**
1. 하루 한도 429를 T11-a에 넣기 → 추천: 넣음(위)
2. 대체 결과에 가짜 분석기 step을 보일지 → 추천: 안 보임, `FALLBACK` 한 줄
3. 대상 사건 마감 10초 당기기 → 추천: 당김
4. T25 뒤 답한 샘플(답하면 `inputVersion` +1)은 대체 대상이 아님 → 계약 4.10 그대로(답이 반영 안 된 고정 결과를 보여 주면 질문이 다시 나와 혼란)

### T11-b 시간당 한도·자동 삭제 (이슈 #13, 브랜치 `feat/13-limits-cleanup`)

**이미 있는 것:** 사건 `expires_at`(생성 + 24시간)과 만료 사건 404(`services/auth.py`), `usage_events.ip_hash` 칸(비어 있음), 하루 한도(T11-a). **없는 것:** 시간당 한도 2종, `CASE_CREATE` 기록, 만료 사건을 DB에서 실제로 지우는 정리

**① 사건 생성 시간당 20회(같은 IP, 계약 4.3·4.3.1)**
- 사건 만들기·샘플 사건 만들기 때 `usage_events`에 `CASE_CREATE` 행(ip_hash)을 남기고, 최근 1시간 같은 ip_hash 행이 20개 이상이면 `429 RATE_LIMITED`(사건 안 만듦)
- IP: 라우터가 `request.client.host`를 서비스에 넘긴다. 배포는 이미 uvicorn `--proxy-headers`라 Render 앞단을 거친 실제 접속 IP
- 해시: `HMAC-SHA256(IP_HASH_SECRET, IP)`. 환경변수가 없으면 서버가 켜질 때 임의 값을 만든다(재시작하면 지난 1시간 기록과 이어지지 않지만 한도가 잠깐 풀릴 뿐이고, 배포 설정을 안 건드려도 됨)

**② 사건당 분석 시간당 5회(계약 4.10)**
- 분석 시작 때 409 검사 다음, 하루 한도 앞에서 이 사건의 최근 1시간 `ANALYSIS_RUN` 행이 5개 이상이면 `429 RATE_LIMITED`(실행 행 안 생김). 가짜 분석·대체 결과 실행도 센다(계약은 "분석 시간당 5회"로 AI 여부를 나누지 않음)

**③ 24시간 자동 삭제(계약 2절 ④, ERD 3.10)**
- `services/cleanup.py` `purge_expired(db, now)`: `expires_at`이 지난 사건 삭제(하위 표는 CASCADE), 24시간 지난 `usage_events.ip_hash`를 NULL로
- 서버가 켜질 때 한 번 + 10분마다(서버 안 스레드, 앱 lifespan에서 시작·종료). Render Starter는 잠들지 않는다
- 실행 중인 분석이 있는 사건은 24시간이 지났으면 이미 150초 마감으로 끝난 상태라 따로 막지 않는다

**바꿀 파일**
- `app/config.py`: `RATE_LIMIT_CASES_PER_IP_HOUR`(20)·`RATE_LIMIT_RUNS_PER_CASE_HOUR`(5)·`IP_HASH_SECRET`(없으면 임의)·`CLEANUP_INTERVAL_SECONDS`(600)
- `app/services/usage.py`: ip 해시, 최근 1시간 세기, `CASE_CREATE` 기록
- `app/services/cases.py`·`samples.py`: 만들기 전에 한도 검사 + 기록 / `app/api/cases.py`·`samples.py`: IP 넘기기
- `app/services/analysis.py`: 사건당 한도 검사
- `app/services/cleanup.py`(새 파일), `app/main.py`: lifespan에서 정리 스레드
- `.env.example`, `docs/deploy.md`(환경변수 표 + **자동 배포 안 됨 → 머지 후 Manual Deploy**로 고침, 11/22 확인)
- 계약·ERD 변경 없음(1.1·4.3·4.10·ERD 3.10에 이미 있음)

**계약 테스트(승인 필요, 429 응답 모양이라 계약 테스트)**
- T11-b-1 사건 생성 한도: 한도 2로 두고 같은 IP에서 사건 2개(일반 1 + 샘플 1) 만든 뒤 3번째 → `429 RATE_LIMITED`, 사건 수 그대로
- T11-b-2 분석 한도: 한도 1로 두고 한 사건 분석 1번 끝낸 뒤 다시 → `429 RATE_LIMITED`, 실행 행 그대로. 다른 사건은 분석 가능
- T11-b-3 자동 삭제: `expires_at`을 과거로 바꾼 사건과 아닌 사건 → `purge_expired` 뒤 만료 사건과 하위 자료(서류·실행)는 DB에서 사라지고 다른 사건은 남음, 24시간 지난 `ip_hash`는 NULL, `usage_events` 행 수는 그대로(한도·비용 기록 유지)

**정할 것(추천안)**
1. `IP_HASH_SECRET` 없으면 서버가 임의 값 → 추천: 그렇게(Render 설정 추가 불필요). 넣고 싶으면 Render 환경변수에 추가
2. 분석 한도에 가짜 분석·대체 결과도 셈 → 추천: 셈(계약 문구 그대로, 코드 단순)
3. 정리 주기 10분 → 추천: 10분(만료 404는 이미 즉시라 주기는 DB 정리용)
4. 알려진 한계: uvicorn이 모든 앞단의 `X-Forwarded-For`를 믿어서 마음먹으면 IP를 속일 수 있다 → 프로토타입이라 그대로 두고 하루 300회 한도가 최후 보호(소개서 한계에 적을 수 있음)

## 결정

- 11/22 T11-a(사용자 "구현 시작"): 정할 것 1~4 추천안대로, 계약 테스트 T11-a-1~3 승인
- 11/22 T11-b(사용자 "추천안대로"): 정할 것 1~4 추천안대로, 계약 테스트 T11-b-1~3 승인. 자동 삭제 기간은 24시간 유지(사용자 질문 "24시간 뒤 삭제가 맞나" → 개인정보·DB 용량·이미 약속한 문구 때문에 유지, 실서비스 보관 연장은 소개서 확장 계획)
- 11/22 T11-a 구현 중 보충: 대체 결과는 `AGENT_LLM=claude`일 때만 쓴다(가짜 분석 모드는 AI를 안 부르므로 실패는 그대로 실패, T07 시간 초과 테스트 유지). 마감 당김은 `min(10초, 마감의 1/10)`

## 결과

### T11-a (이슈 #64, 브랜치 `feat/64-fallback-result`)
- `app/agent/runner.py`: `RunContext.allow_fallback`, `execute_fallback`(가짜 분석기 고정값을 쉬지 않고 만들고 step은 `FALLBACK` 한 줄), 계약 문구 상수
- `app/services/analysis.py`: `is_unchanged_sample`, 하루 한도 검사(대상이면 AI 없이 대체, 아니면 `429 DAILY_LIMIT`), 분석 스레드의 실패 경로(AI 실패·예상 못 한 예외·결과 저장 실패)에서 대체, 대상 사건 AI 마감 당김, `analysis_runs`·`usage_events`의 `precomputed`
- 테스트: `tests/test_t11_fallback.py`(T11-a-1~3). `test_t16_compare.py`의 거절 테스트는 샘플 그대로면 대체 결과로 끝나므로 사연을 고친 사건으로 바꿈
- `uv run python -m pytest -q` 180 passed·2 skipped, `uv run ruff check .` 통과(11/22)
- 로컬 실서버 확인(11/22, 틀린 API 키로 실제 Anthropic 401 → 비용 0): `AGENT_LLM=claude` 서버에서 GOODS·UNEXPECTED 샘플이 `SUCCEEDED`·마지막 step `FALLBACK`·`precomputed: true`, 대조 3·4개, 의견 1·질문 2, 초안 3·5문장, `GET /draft` 200, 사건 `REVIEW_READY`(15.5초·6.2초). 고친 샘플은 `FAILED`·결과 404. `DAILY_ANALYSIS_LIMIT=0` 서버: 샘플 0.6초에 `FALLBACK`만·Anthropic 호출 0회, 고친 샘플 `429 DAILY_LIMIT`
- 미검증: 배포 서버, 시간 초과(140초)로 인한 대체(자동 테스트·실서버 모두 안 함)


### T11-b (이슈 #13, 브랜치 `feat/13-limits-cleanup`)
- `app/services/usage.py`: `hash_ip`(HMAC-SHA256, 비밀값 없으면 프로세스 임의 값), 최근 1시간 세기, `check_case_create_limit`·`record_case_create`(`CASE_CREATE` 행), `check_run_limit`
- `app/services/cases.py`: `Creator`(ip_hash, 한도)·`creator_for`, `stage_case`가 한도 검사 + 생성 기록(일반·샘플 사건 공통). 라우터는 `auth.client_ip`로 IP만 넘김
- `app/services/analysis.py`: 409 검사 다음, 하루 한도 앞에서 사건당 시간당 한도
- `app/services/cleanup.py`(새 파일): `purge_expired`(만료 사건 삭제, 24시간 지난 `ip_hash` NULL, 사용량 행은 유지), `Cleaner`(켜질 때 한 번 + 주기 스레드). `app/main.py` lifespan에서 시작·종료
- 환경변수 `RATE_LIMIT_CASES_PER_IP_HOUR`(20)·`RATE_LIMIT_RUNS_PER_CASE_HOUR`(5)·`IP_HASH_SECRET`·`CLEANUP_INTERVAL_SECONDS`(600), `.env.example`·`docs/deploy.md` 갱신(자동 배포 안 됨 → 머지 후 Manual Deploy, 429·자동 삭제 안내)
- 테스트: `tests/test_t11_limits.py`(T11-b-1~3). `uv run python -m pytest -q` 206 passed·2 skipped, `uv run ruff check .` 통과(11/22)
- 로컬 실서버(임시 SQLite, 한도 2): 샘플 2개 201, 3번째 `429 RATE_LIMITED`(문구 "한 시간에 사건을 2개까지 만들 수 있어요…"), 서버 시작 로그 오류 없음
- 미검증: 배포 서버(Postgres)에서 정리 스레드가 만료 사건을 실제로 지우는지(배포 DB의 24시간 지난 사건은 다음 시작 때 지워져야 함), Render 앞단을 거친 IP가 사용자별로 다르게 잡히는지
