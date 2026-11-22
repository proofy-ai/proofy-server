# T11 운영 보호

- 단계: 2단계 가짜 분석 · 예정: 11/22 오후 · 상태: 대기 · 이슈: #13 · PR: 없음

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

(작업 시작 때 작성하고 확인받는다)

## 결정

## 결과

