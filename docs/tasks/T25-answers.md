# T25 답변 받기 (`answers`)

- 단계: 3단계 실제 AI(계약 v0.8, 11/22 추가) · 예정: 11/22 저녁 · 상태: 대기 · 이슈: 없음 · PR: 없음

## 범위

- 분석 시작 `answers`(계약 4.9): 가장 최근 성공 실행의 질문만, 1~500자, 아니면 `400 VALIDATION_ERROR`. 먼저 저장, `inputVersion` +1, 같은 질문은 덮어씀
- 다음 분석에서 지금까지의 질문·답을 사건 이름 목록으로 가려 에이전트 첫 메시지에 넣음. 인용 검증 기준(`masked_narrative`)에 붙임
- 결과 `agentReview.answered`(사건 단위, 답한 순서)
- 가짜 분석: 답 내용은 읽지 않고, 답한 질문은 다시 내지 않음

## 제외

- 실시간 대화(`messages`, P1)

## 완료 조건

- 답하고 다시 분석하면 `answered`에 남고 에이전트 입력에 가린 답이 들어간다. 계약 테스트(목록은 구현 계획에서 승인) 통과

## 구현 계획

(11/22 T23·T24·T25·T10을 한꺼번에 작성)

### 바꿀 파일
| 파일 | 내용 |
|---|---|
| `app/schemas/analysis.py` | `AnalysisStart.answers: list[AnswerIn] \| None`(`questionId`, `answer`), 목록 최대 10개 |
| `app/services/questions.py`(새) | `save_answers(db, case, answers)`: 앞뒤 공백 제거 후 1~500자, `questionId`가 가장 최근 성공 실행의 질문인지 확인 → 아니면 `400 VALIDATION_ERROR`(`details.fields.answers`). 같은 요청에 같은 질문이 두 번이면 마지막 것. 저장(덮어씀)·`answered_at`, 하나라도 있으면 `input_version` +1. `answered_list(case)`, `answered_pairs(case)`(질문·답 원문, 답한 순서) |
| `app/services/analysis.py` | 순서: 사연 저장 → **답 저장** → 사전 조건 422 → 실행 중 409 → 고친 초안 409. `RunContext.answers`(질문·답 원문 쌍)를 넘김 |
| `app/agent/runner.py` | 가리기 단계에서 답 속 `○○○ 씨`도 이름 목록에 넣고, 질문·답을 가려 `out.masked_answers`에 둠 |
| `app/agent/compare.py`, `drafting.py` | 첫 메시지에 `answers: [{question, answer}]`(가린 글). 프롬프트: 답은 사용자 진술이라 `NARRATIVE` 근거로 인용할 수 있고, 이미 답한 질문은 다시 묻지 않으며, 초안은 답의 사실도 본인 진술로 쓴다 |
| `app/services/results.py` | 저장할 때 `run.masked_narrative` = 가린 사연 + 빈 줄 + 가린 질문·답 묶음(인용 대조 기준. 답 인용도 `verified: true`가 되게). 조회 `answered` = 사건의 답 있는 질문, 답한 순서 |
| `app/agent/scripted.py` | 이미 답한 질문과 같은 글의 질문은 다시 내지 않음(답 내용은 읽지 않음) |

### 추가(11/22 사용자 결정, `docs/agent-design-v2.md` 4.6): 지난 분석 성찰 넘기기
| 파일 | 내용 |
|---|---|
| `app/services/questions.py` | `previous_review(case)`: 가장 최근 성공 실행에서 어긋남·확인 못 함·진술만 항목(claim·status·note), 계획했지만 확인 못 한 항목(실행의 `VERIFY` 계획 점검 결과), 확인 필요 초안 문장 수·의견 수. 새 표 없음 |
| `app/services/analysis.py`, `app/agent/runner.py` | `RunContext.previous`로 넘기고 runner가 사건 이름 목록으로 가림 |
| `app/agent/compare.py` | 첫 메시지 `previousRun`. 프롬프트: 있으면 `make_plan`의 `revision`에 지난 분석과 답을 보고 무엇을 왜 바꾸는지 한 문장 |
| `app/agent/scripted.py` | 다시 분석(지난 성공 실행이 있음)이면 계획 줄에 고정 `revision`("지난 분석과 답변을 보고 다시 확인합니다") |
- 테스트(단위): 두 번째 분석의 첫 메시지에 `previousRun`이 있고 이름이 가려짐, 첫 분석에는 없음

### 계약 테스트(승인 필요)
| # | 내용 |
|---|---|
| T25-a | 답 검증: 최근 성공 실행에 없는 `questionId`(이전 실행 질문, 다른 사건 질문, 없는 값) → `400 VALIDATION_ERROR`·`details.fields.answers`, 빈 답·501자 → 400. 400이면 아무것도 저장 안 됨 |
| T25-b | 답 반영(가짜 분석): 답하면 `inputVersion` +1, 다시 분석 결과 `answered`에 남고(답한 순서, 같은 질문 다시 답하면 마지막 답) 그 질문은 `questions`에 다시 안 나옴 |
| T25-c | 답이 AI에 가려서 감(가짜 SDK): 첫 메시지에 질문·답이 있고 답 속 이름은 가려져 있으며, 답을 인용한 `NARRATIVE` 근거가 `verified: true` |

### 정할 것(추천)
1. 400일 때 사연(`narrative`)도 저장하지 않음(추천). 답 검증을 사연 저장보다 **먼저** 하고 저장은 그 뒤에 한다(요청 하나가 반만 반영되지 않게). 계약의 "먼저 저장한 뒤 사전 조건 검사" 순서는 그대로
2. 분석이 실패해도 답은 남음(추천). 다시 시도하면 같은 답으로 분석된다

## 결정

- 11/22 사용자 "추천안대로": 정할 것 1·2 추천안(1은 설명 후 진행), 계약 테스트 T25-a~c 승인

## 결과
