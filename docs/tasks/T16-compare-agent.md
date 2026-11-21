# T16 대조 에이전트

- 단계: 3단계 실제 AI · 예정: 11/22 낮(실제 Claude 첫 실행 목표 13:00) · 상태: 대기 · 이슈: #18 · PR: 없음

## 범위

- Claude Messages API 도구 루프(`docs/agent-design.md` 2.4): `get_transactions`, `get_evidence_regions`
- 구조화 출력: findings, AI 권장 자료
- `steps` 기록, 거절·시간 초과 처리
- 재사용 시 출처를 커밋 메시지에 기록(corebank `llm/claude.py` 재시도·비용 등)
- `agent/llm.py`: corebank `llm/claude.py`·`port.py`의 단가·비용 계산, 마감 안 재시도, 도구 결과 상한, `Usage`·`Deadline`을 가져온다(`docs/agent-design.md` 5·6절). 자동 캐시, thinking 파라미터 생략, effort `low` 명시, 서버측 fallback
- 도구 인자에 `reason`(조회 이유) 필수 → step `TOOL_CALL` `summary`로 표시
- 대조 결과 검증: 인용 원문 대조, 이 사건 소속·이번에 조회한 거래 ID만 인정(`docs/agent-design.md` 2.4)
- LangGraph 등 프레임워크는 쓰지 않는다(11/21 결정)
- 고정 목록(라벨)을 프롬프트에 넣고 같은 서류를 권하지 말라고 지시한다. 코드는 서류 종류로 거르지 않고 최대 3개로 자른다. 고정 항목과 같은 `docType`으로는 자동 충족되지 않는다(T08, 계약 v0.6.5 4.8)

## 제외

- 초안(T17)

## 완료 조건

- test01·test02 샘플로 실제 분석 → 결과 화면 데이터가 나옴

## 구현 계획

(작업 시작 때 작성하고 확인받는다)

## 결정

## 결과

