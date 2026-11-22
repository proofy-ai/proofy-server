# T24 AI 의견·질문 (`agentReview`)

- 단계: 3단계 실제 AI(계약 v0.8, 11/22 추가) · 예정: 11/22 오후 · 상태: 대기 · 이슈: 없음 · PR: 없음

## 범위

- 결과 API에 `agentReview`(계약 4.11): `notice`, `opinions`, `questions`, `answered`
- 표 `analysis_opinions`, `analysis_questions`(ERD v1.4 3.11·3.12). 새 표만 추가
- 가짜 분석기: 시나리오별 고정 의견·질문(먼저 만들어 FE가 붙여 볼 수 있게 배포)
- 실제 분석: 대조 에이전트 출력에 `opinions`·`questions` 추가(법령 조회 T23), 검증(근거 조항 인용 대조, 결과 예측 표현, 숫자) → 초안과 같은 1회 고쳐 쓰기 → `needsCheck`
- 근거 번호는 같은 실행의 findings ID로만(없는 번호 버림)

## 제외

- 답변 저장·반영(T25), 상담 권유(T10)

## 완료 조건

- 두 샘플의 결과에 `agentReview`가 계약 모양으로 나오고, 계약 테스트(목록은 구현 계획에서 승인) 통과

## 구현 계획

(T23·T24·T25·T10을 한꺼번에 써서 확인받는다)

## 결정

## 결과
