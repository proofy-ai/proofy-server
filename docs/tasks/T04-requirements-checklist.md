# T04 서류 목록·체크리스트

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 완료 · 이슈: #6 · PR: #36

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

> 계약 v0.6.1 4.2·4.8, ERD v1.1 3.8 기준.

### 파일

| 파일 | 내용 |
|---|---|
| `app/services/requirements.py` | 유형별 서류 목록 **코드 상수**(계약 4.2 표 그대로, 출처 포함)와 `items_for(inflow_type)` |
| `app/services/checklist.py` | 사건별 행 맞추기(`sync_items`), 충족 여부 계산(`compute_status`), `missingCount`, 체크 표시 변경 |
| `app/models/checklist.py` | `checklist_items` 테이블 |
| `app/schemas/checklist.py` | `RequirementItem`·`RequirementsResponse`(4.2), `ChecklistItem`·`ChecklistResponse`·`ChecklistPatch`(4.8) |
| `app/api/meta.py` | `GET /meta/requirements?inflowType=` (인증 없음) |
| `app/api/checklist.py` | `GET /cases/{caseId}/checklist`, `PATCH /cases/{caseId}/checklist/{itemId}` |
| `tests/test_t04_checklist.py` | 아래 테스트 |

### 동작

- **목록(4.2):** 공통 `OBJECTION_FORM`·`ID_COPY`(`OFFICIAL_REQUIRED`, 올릴 수 없음) + 유형별 항목 + 공통 `NOTICE`(`OPTIONAL`). 순서는 묶음 순(`OFFICIAL_REQUIRED` → `TYPE_GUIDE` → `ANALYSIS_INPUT` → `OPTIONAL`), 묶음 안은 계약 표 순
  - `SALARY`·`GOODS`·`UNEXPECTED`는 계약 표 그대로. 계약에 문구가 없는 `note`는 `null`(지어내지 않는다)
  - `OTHER`(화면에 없는 값): 공통 항목 + `DEPOSIT_RECORD`(거래내역서, `ANALYSIS_INPUT`, 분석 필요). 분석 시작 조건이 모든 유형에 거래내역서를 요구하기 때문
  - `inflowType`이 없거나 enum 밖 → 400 `VALIDATION_ERROR`
- **충족 여부(코드가 계산):** `ID_COPY` → `NOT_COLLECTED`, `OBJECTION_FORM` → `GUIDE_ONLY`, 나머지는 올린 서류 중 `docType`이 `acceptedDocTypes` 하나라도 맞으면 `SATISFIED`(`satisfiedBy`에 그 `evidenceId`들), 없으면 `MISSING`. 계산 함수는 (evidenceId, docType) 목록을 받게 만들고, 증빙 테이블이 생기는 T05 전까지는 빈 목록을 넘긴다
- `missingCount` = `MISSING`이면서 `checked == false`인 항목 수
- **사건별 행:** `GET /checklist`를 부를 때 현재 입금 유형의 상수 항목과 행을 맞춘다(없는 `code`는 만들고, 유형이 바뀌어 목록에 없는 `code`는 지운다). 같은 `code`의 행은 그대로 두므로 `checked`가 이어진다(ERD 3.8 "유형이 바뀌면 다시 만들고 이어받는다"를 읽을 때 처리). UNIQUE(`case_id`, `code`)로 중복 행을 막는다
- **PATCH:** `{ "checked": true|false }`(엄격 불리언) → `200 { "item": … }`. 다른 사건의 `itemId`·없는 `itemId` → 404 `NOT_FOUND`. 체크 표시는 분석 입력이 아니라 `inputVersion`을 올리지 않는다
- 응답 항목 키는 계약 4.8 예시 그대로: `itemId, code, label, category, status, acceptedDocTypes, requiredForAnalysis, satisfiedBy, checked, note, sourceRef`

### 테이블

- `checklist_items`: `id`, `case_id`(FK, 사건 삭제 시 함께 삭제), `analysis_run_id`(NULL), `code`(NULL), `category`, `label`·`note`(NULL), `accepted_doc_types_json`(NULL), `checked`(기본 false), `created_at`. UNIQUE(`case_id`, `code`)
- `analysis_run_id`는 `analysis_runs` 테이블이 생기는 T07에서 FK를 건다. 지금은 FK 없는 칼럼으로 둔다(로컬 DB는 T07 때 지우고 다시 만든다. 마이그레이션은 T18)

### 테스트(계약 관련이라 승인 필요)

| # | 내용 |
|---|---|
| T04-a | `GET /meta/requirements`: `SALARY`·`GOODS`·`UNEXPECTED` 각각 `code`·`category`·`acceptedDocTypes`·`requiredForAnalysis`가 계약 4.2 표와 같고, `requiredForAnalysis: true`는 거래내역서 항목 하나뿐. 어느 항목도 신분증을 받지 않음(`ID_COPY.uploadable == false`) |
| T04-b | 분석 전 `GET /checklist`: 계약 4.8 키, `ID_COPY` `NOT_COLLECTED`·`OBJECTION_FORM` `GUIDE_ONLY`·나머지 `MISSING`, `missingCount` 계산. `PATCH checked: true` 뒤 `missingCount` 1 감소 |
| T04-c | 충족 계산: 여러 `acceptedDocTypes` 중 하나만 있어도 `SATISFIED`·`satisfiedBy`, `OTHER` 서류가 `INCIDENT_REPORT`를 충족(함수 단위 테스트) |
| T04-d | 사건 입금 유형을 바꾸면 목록이 새 유형으로 바뀌고, 같은 `code`(`NOTICE`)의 `checked`는 유지 |

그 밖에(승인 불필요): 다른 사건의 `itemId` PATCH → 404, `inflowType` 없음 → 400

### 정할 것

- `OTHER` 유형 목록(위 제안: 공통 + 거래내역서)
- 행 맞추기를 `GET` 때 하는 방식(위 제안). 대안은 사건 생성·입금 유형 변경 때 맞추는 것인데, 호출 지점이 늘고 T03 코드도 고쳐야 한다

## 결정

- 11/21 사용자 승인: 계획, 정할 것 2개(`OTHER` 목록 = 공통 + 거래내역서, 행 맞추기는 `GET` 때), 테스트 T04-a~d
- 11/21 계약 v0.6.2(사용자 선택 C): 4.2에 `OTHER` 목록과 "문구가 없는 항목의 `note`는 `null`" 규칙, 4.8 예시의 `TRADE_DOCUMENT.note`를 `null`로. 고정 항목은 어느 사건에나 맞는 내용만 담고, 사건별 안내는 AI 권장 항목·탭 A가 맡는다
- 11/21 AI 권장 항목이 고정 목록에 이미 있는 서류 종류를 추천하면 코드가 거른다 → T08·T16 범위에 추가
- 11/21 같은 묶음 안 순서: 공통 항목(`NOTICE`) 먼저, 그다음 유형별 항목(계약은 순서를 정하지 않음)
- 11/21 `DocType`·`InflowType`을 `app/schemas/common.py`로 옮김(T05 증빙에서도 씀)

## 결과

- `uv run python -m pytest -q` → 40 passed(T04 11개: T04-a 4유형, 잘못된 `inflowType` 400, T04-b~d, 다른 사건 항목 404, 토큰·`inputVersion`, 사건 삭제 시 행 삭제)
- `uv run ruff check .` → All checks passed, `uv run ruff format --check .` → 이상 없음
- 미검증: 올린 서류로 `SATISFIED`가 되는 것은 함수 단위로만 확인(증빙 업로드는 T05에서 연결). FE 연동 안 해 봄

