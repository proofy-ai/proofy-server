# T04 서류 목록·체크리스트

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 대기 · 이슈: #6 · PR: 없음

## 범위

- 유형별 서류 목록을 코드 상수로(계약 4.2: SALARY·GOODS·UNEXPECTED)
- `GET /meta/requirements?inflowType=`
- `checklist_items` 테이블, `GET /cases/{id}/checklist`, `PATCH …/checklist/{itemId}`(계약 4.8)
- 충족 여부(`status`)는 올린 서류의 `docType`으로 코드가 계산
- 통장 묶기(`UNEXPECTED`)에 피해 신고 기록 항목 `INCIDENT_REPORT`(`OPTIONAL`, `acceptedDocTypes: ["OTHER"]`, 계약 v0.5 4.2)

## 제외

- AI 권장 항목(T08 이후)

## 완료 조건

- 세 유형 목록이 계약 표와 같음
- 분석 전 체크리스트가 계약 모양으로 응답

## 구현 계획

(작업 시작 때 작성하고 확인받는다)

## 결정

## 결과

