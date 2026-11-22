# T11 운영 보호

- 단계: 2단계 가짜 분석 · 예정: 11/22 오후 · 상태: T11-a PR, T11-b 대기 · 이슈: T11-a #64, T11-b #13 · PR: T11-a 열림

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

## 결정

- 11/22 T11-a(사용자 "구현 시작"): 정할 것 1~4 추천안대로, 계약 테스트 T11-a-1~3 승인
- 11/22 T11-a 구현 중 보충: 대체 결과는 `AGENT_LLM=claude`일 때만 쓴다(가짜 분석 모드는 AI를 안 부르므로 실패는 그대로 실패, T07 시간 초과 테스트 유지). 마감 당김은 `min(10초, 마감의 1/10)`

## 결과

### T11-a (이슈 #64, 브랜치 `feat/64-fallback-result`)
- `app/agent/runner.py`: `RunContext.allow_fallback`, `execute_fallback`(가짜 분석기 고정값을 쉬지 않고 만들고 step은 `FALLBACK` 한 줄), 계약 문구 상수
- `app/services/analysis.py`: `is_unchanged_sample`, 하루 한도 검사(대상이면 AI 없이 대체, 아니면 `429 DAILY_LIMIT`), 분석 스레드의 실패 경로(AI 실패·예상 못 한 예외·결과 저장 실패)에서 대체, 대상 사건 AI 마감 당김, `analysis_runs`·`usage_events`의 `precomputed`
- 테스트: `tests/test_t11_fallback.py`(T11-a-1~3). `test_t16_compare.py`의 거절 테스트는 샘플 그대로면 대체 결과로 끝나므로 사연을 고친 사건으로 바꿈
- `uv run python -m pytest -q` 180 passed·2 skipped, `uv run ruff check .` 통과(11/22)
- 로컬 실서버 확인(11/22, 틀린 API 키로 실제 Anthropic 401 → 비용 0): `AGENT_LLM=claude` 서버에서 GOODS·UNEXPECTED 샘플이 `SUCCEEDED`·마지막 step `FALLBACK`·`precomputed: true`, 대조 3·4개, 의견 1·질문 2, 초안 3·5문장, `GET /draft` 200, 사건 `REVIEW_READY`(15.5초·6.2초). 고친 샘플은 `FAILED`·결과 404. `DAILY_ANALYSIS_LIMIT=0` 서버: 샘플 0.6초에 `FALLBACK`만·Anthropic 호출 0회, 고친 샘플 `429 DAILY_LIMIT`
- 미검증: 배포 서버, 시간 초과(140초)로 인한 대체(자동 테스트·실서버 모두 안 함)

