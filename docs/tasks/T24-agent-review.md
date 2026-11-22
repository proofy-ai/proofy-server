# T24 AI 의견·질문 (`agentReview`)

- 단계: 3단계 실제 AI(계약 v0.8, 11/22 추가) · 예정: 11/22 오후 · 상태: PR · 이슈: #62 · PR: (아래 결과)

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

(11/22 T23·T24·T25·T10을 한꺼번에 작성)

~~두 번에 나눠 PR을 낸다.~~ → **PR 하나로 냄(11/22 구현 중 변경).** 배포 서버는 `AGENT_LLM=scripted`라 실제 Claude 경로가 들어가도 꺼져 있고, 머지 한 번으로 FE 연동이 가능해 검토·머지를 한 번 줄였다. ① 가짜 분석 + 저장 + 결과 API ② 실제 Claude 출력·검증·고쳐 쓰기.

### 바꿀 파일
| 파일 | 내용 |
|---|---|
| `app/models/review.py`(새) | `AnalysisOpinion`, `AnalysisQuestion`(ERD 3.11·3.12 그대로). 질문은 `case_id` FK `ondelete=CASCADE`. `models/__init__.py`에 등록 |
| `app/agent/output.py` | `LawRef(ref, source, label, quote, verified)`, `Opinion(text, finding_indexes, law_refs, check_reason)`, `Question(text, why, finding_indexes, law_refs)`, `AnalysisOutput.opinions·questions` |
| `app/agent/scripted.py` | ① 시나리오별 고정 의견·질문. GOODS = 계약 4.11 예시 그대로(의견 1: 법 제7조①2호 "재화 또는 용역의 공급에 대한 대가로 받았거나", 질문 2: 금액 차이·택배 송장). UNEXPECTED = 의견 1(법 제7조①3호, 협박 문자·입금 행 기준) + 질문 2(입금일 11일·12일 차이, 은행 신고 기록). 법령 조회 흉내 step 1개. `verified`는 T23 `check_quote`로 실제 대조 |
| `app/services/results.py` | 저장: 번호 → 이 실행의 `findingId`(없는 번호 버림). 조회: `agentReview { notice, opinions, questions, answered }`. `questions`는 이 실행 질문 중 아직 답 없는 것, `answered`는 T25에서 채움(그전엔 `[]`) |
| `app/schemas/result.py` | `AgentReview`, `AgentOpinion`, `AgentQuestion`, `LawRefOut`, `AnsweredOut`, `ResultResponse.agent_review` |
| `app/agent/compare.py` | ② 출력 스키마에 `opinions[] {text, findingIndexes[], lawRefs[{ref, quote}]}`, `questions[] {text, why, findingIndexes[], lawRefs[]}`(각 0~3). 프롬프트에 조건부 의견 형식·금지 표현·질문 기준(agent-design 2.8). `PROMPT_VERSION` t24-v1 |
| `app/agent/verify.py` | ② 의견·질문 거르기: 글자 수 자르기, 3개 상한, `findingIndexes`를 걸러진 뒤 번호로 다시 맞춤(빈 claim으로 빠진 항목 때문에 밀림), `lawRefs`는 `seen_law_refs`에 있고 원문에 있어야 `verified: true`(아니면 `false`로 남김) |
| `app/agent/drafting.py` | ② 의견 검사: 법령 인용 못 찾음 `LAW_QUOTE_NOT_FOUND` / 결과 예측·확정 표현 `JUDGMENT_EXPRESSION`(초안의 `_JUDGMENT` + 의견만 "해당합니다·해당됩니다") / 근거에 없는 금액·날짜 `NUMBER_MISMATCH`. 뒤의 둘은 **초안 고쳐 쓰기 호출 1회에 같이 넣어** 고치고 다시 검사(통과하면 고친 문장, 또 걸리면 원래 문장 + `needsCheck`). 질문은 고쳐 쓰지 않음 |

### 추가(11/22 사용자 결정, `docs/agent-design-v2.md` 4.3): 조사 계획과 계획 대비 점검
| 파일 | 내용 |
|---|---|
| `app/agent/compare.py` | ② 도구 `make_plan(items[{claim, check, sources[]}], revision)`. 프롬프트로 첫 호출에 쓰게 함. 상한 12회에 세지 않고 실행당 2번(처음 + 수정 1회). step `TOOL_CALL` "조사 계획"/"조사 계획 수정": `확인할 것 N가지: 주장(자료) · …`, `revision`이 있으면 앞에 붙임. 출력 `findings[].planItem`(정수 또는 null) |
| `app/agent/verify.py` | 계획 대비 점검: 계획 항목마다 `planItem`이 그 번호인 주장이 있나 → step `VERIFY` "계획한 확인 3개 중 2개를 마쳤습니다. 확인 못 한 것: …". 프롬프트가 확인 못 한 항목은 질문하게 함 |
| `app/agent/scripted.py` | ① 고정 조사 계획 줄(GOODS 3가지, UNEXPECTED 3가지)과 "계획한 확인을 모두 마쳤습니다" 점검 줄 |
- 테스트(단위): `make_plan` step 모양·2번 상한·상한 12회에 안 셈, 계획 대비 점검 step(가짜 SDK)

### 계약 테스트(승인 필요)
| # | 내용 |
|---|---|
| T24-a | `agentReview` 응답 모양(가짜 분석 GOODS·UNEXPECTED): `notice`, 의견 1개(`lawRefs[0]` `source`·`label`·`quote`·`verified: true`), 질문 2개(`why`), `answered: []`, `findingIds`가 같은 결과의 `findings` ID |
| T24-b | 의견 검증(가짜 SDK): 이번 실행에서 조회하지 않은 조항·원문에 없는 인용 → `verified: false`·`needsCheck: true`(지우지 않음). 없는 항목 번호는 빠짐 |
| T24-c | 의견 1회 고쳐 쓰기: "해제될 가능성이 높아요" 의견이 고친 문장으로 통과하면 고친 문장·`needsCheck: false`, 또 걸리면 원래 문장·`needsCheck: true` |
| T16-a 수정 | 판정 필드 부재: 대조 출력 스키마 칸 목록에 `opinions`·`questions`(T10 뒤 `consult`)와 그 안의 칸을 더한다. 해제 가능성·수용 여부 같은 칸은 여전히 없음 |

### 정할 것(추천)
1. `agentReview`가 `null`인 때: **의견·질문·답한 기록이 모두 없을 때**(추천). 배포 DB의 v0.8 전 결과가 `null`이 되고, AI가 아무것도 안 낸 경우도 FE에서 카드가 숨는다(어차피 빈 카드)
2. 결과 예측 검사: 초안 표현 목록 + 의견에만 "해당합니다·해당됩니다"(확정) 추가(추천). 의견 형식 "설명할 수 있는 사정으로 보여요"는 통과
3. 질문에 단 근거 조항도 `verified`만 표시하고 `needsCheck`는 두지 않음(계약에 질문 `needsCheck` 칸 없음)

## 결정

- 11/22 사용자 "추천안대로": 정할 것 1~3 추천안, 계약 테스트 T24-a~c·T16-a 수정 승인
- 11/22 사용자: 조사 계획(`make_plan`)·계획 대비 점검 추가(`docs/agent-design-v2.md`)

## 결과

- 표 `analysis_opinions`·`analysis_questions`(`app/models/review.py`, 새 표만 → 배포 DB 초기화 불필요), `app/services/review.py`(저장·`agentReview`), 결과 응답 `agentReview`
- 가짜 분석: 조사 계획 줄 → 거래내역 조회 → 법령 조회 → 계획 점검, GOODS·UNEXPECTED 의견 1·질문 2(근거 조항은 `law.law_ref`로 실제 원문 대조, label "법 제7조 제1항 제2호/제3호"). 급여·기타는 의견·질문 없음 → `agentReview: null`
- 실제 분석: `make_plan` 도구(조회 한도에 안 셈, 2번까지, 판정 표현이 든 `revision`은 화면에서 뺌), 출력 `findings[].planItem`·`opinions`·`questions`, `verify`가 근거 번호 다시 맞춤·법령 인용 대조(`LAW_QUOTE_NOT_FOUND`), `drafting.check_opinion`(숫자·결과 예측·"해당합니다") + 초안과 같은 고쳐 쓰기 호출 1회, step `VERIFY` "계획 점검"·"의견 확인". `PROMPT_VERSION` t24-v1. `drafting._JUDGMENT` → `JUDGMENT`(공용)
- 테스트: T24-a(2), T24-b, T24-c(2), 계획 도구 2, `agentReview: null`, T16-a·도구 이유 테스트 수정, T08 결과 키·조회 줄 찾기 수정
- 관찰: 테스트가 느려짐(claude 모드 실행 1회 약 10초). 원인은 이 작업이 아니라 Tesseract 없는 PC에서 PNG 전처리(장당 약 4초). 전체 실행 70초 → 230초(PC 부하일 수 있음, 미확인)
- 미검증: 실제 Claude가 계획·법령 조회·의견·질문을 잘 내는지(가짜 SDK로만 확인). 6번 실제 Claude 점검에서 test01·test02로 확인
