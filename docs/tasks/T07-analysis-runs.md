# T07 분석 실행·진행

- 단계: 2단계 가짜 분석 · 예정: 11/22 오전 · 상태: 계획 확인 · 이슈: #9 · PR: 없음

## 범위

- `analysis_runs` 테이블
- `POST /cases/{id}/analysis-runs`(계약 4.9): `narrative` 먼저 저장, 사전 조건 422, 실행 중 409, 고친 초안 409
- 백그라운드 실행(서버 안 스레드), 사건당 동시 실행 1개, 150초 시간 초과
- `GET …/analysis-runs/{runId}`(계약 4.10): `stages`, `steps`
- 분석 시작 때 보낸 `narrative`는 저장된 값과 다를 때만 저장·`inputVersion` +1(계약 v0.6 4.9)
- 분석 시작마다 `usage_events`(`ANALYSIS_RUN`) 기록(ERD 3.10, 한도 계산은 T11)

## 제외

- 분석 내용(T08 가짜, T16 실제)

## 완료 조건

- 빈 분석기로 실행 → 단계 진행 → 완료까지 폴링으로 확인

## 구현 계획

> 계약 v0.6.3 4.9·4.10, ERD v1.1 3.5·3.10·4절, `docs/agent-design.md` 2·2.7 기준. 분석 내용은 비어 있다(세 단계를 지나가기만 함). T08이 가짜 분석기를 끼운다.

### 파일

| 파일 | 내용 |
|---|---|
| `app/models/analysis.py` | `AnalysisRun`(ERD 3.5 컬럼 전부. T08~T16이 쓸 컬럼도 지금 만든다) |
| `app/models/usage.py` | `UsageEvent`(ERD 3.10). T07은 `ANALYSIS_RUN` 행만 쓰고, 한도 계산·`CASE_CREATE`·IP 해시는 T11 |
| `app/agent/runner.py` | 분석 실행의 유일한 입구. 설정(`AGENT_LLM`)으로 분석기를 고르고 ①②③ 단계를 순서대로 부른다. DB를 직접 만지지 않고 넘겨받은 기록기(`recorder`)로만 단계·step을 남긴다 |
| `app/agent/steps.py` | 단계 이름·라벨 상수(`EXTRACTING` "글자 읽는 중" 등), step 모양, `AgentTimeout`·`AgentFailed` 오류 |
| `app/services/analysis.py` | 분석 시작(검사 → 실행 행 → 스레드), 실행 조회, 시간 초과 처리, 기록기 구현(step을 DB에 바로 저장) |
| `app/schemas/analysis.py` | `AnalysisStart`(`narrative`, `overwriteEditedDraft`), `AnalysisStarted`, `AnalysisRunOut`(`stages`·`steps`·`error`) |
| `app/api/analysis.py` | `POST /cases/{id}/analysis-runs`(202), `GET /cases/{id}/analysis-runs/{runId}` |
| `app/services/cases.py` | `latestRun`·`hasResult` 채우기(지금은 항상 `null`·`false`) |
| `app/config.py` | `ANALYSIS_TIMEOUT_SECONDS`(기본 150), `SCRIPTED_STAGE_DELAY_SECONDS`(기본 1.0, 테스트는 0) |
| `tests/test_t07_analysis_runs.py` | 아래 테스트 |

### 동작

**`POST /cases/{id}/analysis-runs`** 검사 순서
1. `narrative`가 있으면 먼저 저장. 저장된 값과 다를 때만 `inputVersion` +1(4.5와 같은 함수 재사용). 2000자 초과는 400
2. 사전 조건: 사연(앞뒤 공백 뺀 길이) 20자 이상 + `TRANSACTION_RECORD` 서류 1개 이상 → 아니면 422 `ANALYSIS_PRECONDITION`, `details.narrativeLength`·`details.missing`
3. 실행 중인 실행이 있으면 409 `ANALYSIS_IN_PROGRESS`(`details.runId`)
4. 고친 초안 409 `DRAFT_HAS_EDITS`: 초안 테이블이 T09에서 생기므로 **검사 자리만 만들고 지금은 항상 통과**. `overwriteEditedDraft`는 지금부터 받는다
5. `analysis_runs` 행(`version` = 사건별 +1, `based_on_input_version`, `status=RUNNING`, `stage=EXTRACTING`, `agent`) + `usage_events`(`ANALYSIS_RUN`, `ai_called`는 scripted면 false) → 사건 `status=ANALYZING` → 커밋 → 스레드 시작 → 202 `{ runId, status, stage }`
- 사건당 동시 실행 1개: 3~5를 사건별 잠금(프로세스 안 `threading.Lock`) 안에서 한다. 서버 프로세스 1개 전제(프로토타입)

**백그라운드 실행**(서버 안 스레드, 자기 DB 세션 사용)
- 단계: `EXTRACTING` → `COMPARING` → `DRAFTING` → `FINISHED`. 단계가 바뀔 때마다, step을 남길 때마다 바로 커밋해 폴링에 보이게 한다
- 성공: `SUCCEEDED`, `stage=FINISHED`, `finished_at`, 사건 `REVIEW_READY`
- 실패: `FAILED`, 실패한 단계는 그대로 두고 `error_code`·`error_message`, step `FAILED`, 사건 `ERROR`. 예상 못 한 예외는 `AGENT_FAILED`(메시지는 "분석 중 문제가 생겼습니다. 다시 시도해 주세요.", 상세는 서버 로그에만)
- **150초:** 스레드는 단계마다 마감을 확인해 넘으면 `AGENT_TIMEOUT`. 서버가 재시작돼 스레드가 사라진 실행도 남지 않게, 조회·분석 시작 때 `RUNNING`인데 마감이 지났으면 그 자리에서 `AGENT_TIMEOUT`으로 바꾼다
- 시간 초과로 끝난 뒤 늦게 끝난 스레드는 결과를 쓰지 않는다(상태가 `RUNNING`일 때만 마무리)

**`GET /cases/{id}/analysis-runs/{runId}`**
- 다른 사건의 실행이거나 없으면 404 `NOT_FOUND`
- `stages`: 현재 단계 앞은 `DONE`, 현재는 `RUNNING`(실패면 `FAILED`), 뒤는 `PENDING`. `FINISHED`면 셋 다 `DONE`. 라벨은 서버 상수
- `steps`: `steps_json` 그대로(`seq`, `type`, `title`, `summary`, `status`, `at`). 빈 분석기는 단계마다 step을 남기지 않는다(T08부터 채움)
- `error`: 실패 때 `{ code, message }`, 아니면 `null`

**사건 응답(4.4)**: `latestRun` = 가장 최근 실행 `{ runId, status, stage }`, `hasResult` = 성공한 실행이 하나라도 있으면 `true`

### 테스트

계약 4.9·4.10의 요청·응답 모양이라 목록 승인을 받는다.

| # | 내용 | 승인 |
|---|---|---|
| T07-a | 샘플 사건 분석 시작 202 `{runId, status: RUNNING, stage}` → 폴링 → `SUCCEEDED`·`FINISHED`, `stages` 3개 순서·라벨·모두 `DONE`, `finishedAt` 값 있음, 사건 `status=REVIEW_READY`·`latestRun`·`hasResult: true` | 승인 필요 |
| T07-b | 사전 조건 422: 사연 짧음 → `missing: [NARRATIVE]`, 거래내역서 없음 → `[TRANSACTION_RECORD]`, 둘 다 → 둘 다 | 승인 필요 |
| T07-c | `narrative` 동봉: 같은 값이면 `inputVersion` 그대로, 다른 값이면 저장·+1, 20자 미만을 보내면 저장된 뒤 422 | 승인 필요 |
| T07-d | 실행 중 다시 시작 → 409 `ANALYSIS_IN_PROGRESS`, `details.runId`가 실행 중인 것(테스트에서 멈춰 있는 분석기를 끼움) | 승인 필요 |
| T07-e | 마감 초과 → `FAILED`, `error.code=AGENT_TIMEOUT`, 사건 `ERROR`(테스트에서 마감을 짧게) | 승인 필요 |
| T07-f | 다른 사건의 `runId`로 조회 → 404 `NOT_FOUND`, 분석 시작마다 `usage_events`에 `ANALYSIS_RUN` 1행 | 승인 필요 |

### 정할 것

- **`usage_events` 테이블을 T07에서 만든다.** ERD 7절은 T11로 적혀 있지만, T07 범위에 "분석 시작마다 기록"이 있어 테이블을 먼저 만든다. 한도 계산은 그대로 T11. ERD 7절 표를 함께 고친다
- **실행 중 확인은 프로세스 안 잠금으로 한다.** 서버를 여러 프로세스로 띄우지 않는다(배포도 1개, T18)
- 로컬 `proofy.sqlite3`는 새 테이블이 시작할 때 자동으로 생긴다. T08에서 기존 테이블(`checklist_items`)에 FK를 걸면 기존 파일에는 반영되지 않으니, T08 뒤에는 로컬 DB 파일을 지우고 다시 띄우는 것을 권한다(검증용 샘플 사건도 남아 있음)

## 결정

## 결과

