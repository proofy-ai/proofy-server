# T03 사건 API

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 대기 · 이슈: #5 · PR: 없음

## 범위

- `cases`, `case_inflows` 테이블
- `caseToken` 발급(한 번만 응답), DB에는 해시만 저장, `X-Case-Token` 인증
- `POST /cases`, `GET/PATCH/DELETE /cases/{id}`(계약 4.3~4.6), 검증 규칙(미래 날짜 400 등), `inputVersion`
- 응답의 `deadline`은 T02 함수로 매번 계산

## 제외

- IP당 생성 제한(T11)
- 증빙(T05)·샘플(T06)

## 완료 조건

- 계약 테스트 4·5·7 통과

## 구현 계획

(작업 시작 때 작성하고 확인받는다)

## 결정

## 결과

