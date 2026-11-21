# T08 가짜 분석기 + 결과 API

- 단계: 2단계 가짜 분석 · 예정: 11/22 오전 · 상태: 대기 · 이슈: #10 · PR: 없음

## 범위

- `AGENT_LLM=scripted` 분석기: 시나리오별로 정해 둔 대조 결과(GOODS는 계약 4.11 예시, UNEXPECTED는 계약 4.3.1 표)
- `claim_findings`, `finding_sources`, AI 권장 체크리스트 항목 저장
- `GET /cases/{id}/result`(계약 4.11), `isStale`, `summary`
- scripted 결과에도 초안 `section`과 `TOOL_CALL` 조회 이유(`summary`)를 넣는다(계약 v0.5, `docs/agent-design.md` 2.4·2.5)
- 결과·근거 거래·AI 권장 체크리스트 항목은 가장 최근 성공 실행 것만(계약 v0.6 4.8·4.11)
- AI 권장 항목은 고정 목록(계약 4.2)에 이미 있는 `docType`만 받는 항목이면 코드가 거른다(같은 서류가 두 번 나오지 않게)

## 제외

- 초안(T09)
- 실제 AI(T16)

## 완료 조건

- test01·test02 샘플로 분석 → 결과가 계약 모양으로 응답
- 결과 응답 모양 계약 테스트(목록은 구현 계획에서 승인)

## 구현 계획

(작업 시작 때 작성하고 확인받는다)

## 결정

## 결과

