# T10 상담 안내 + 판정 필드 부재

- 단계: 2단계 가짜 분석 · 예정: 11/22 오후 · 상태: PR · 이슈: #12 · PR: 열림

## 범위

> 11/22 계약 v0.8로 바뀜(`docs/agent-design.md` 2.1). 키워드만으로 끝내던 첫 계획 초안은 git stash "T10 계획 초안(키워드 방식)"에 있다.

- ⓪ 표현 목록(부정문 제외)으로 가린 사연·답에서 찾기 → 실제 분석은 ② 에이전트에 넘겨 문맥 확인, 가짜·대체 결과는 목록만으로 결정
- 에이전트의 상담 권유(`consult`): 사연·답 원문 인용을 서버가 확인 → `result.referral`(`matchedPhrases` = 확인된 인용), `agentReview` 질문, `draft: null`, 초안 조회 404, step `SAFETY`
- 다시 분석해 상담 안내로 끝나면 이전 초안 행 삭제 → `GET /draft` 404(계약 4.11)
- 판정 필드 부재 테스트: 결과·초안 JSON에 판정성 키가 없음(`agentReview` 포함)
- 판정성 표현 검사 함수(`JUDGMENT_EXPRESSION`)는 T17에서 만듦

## 제외

- 없음

## 완료 조건

- 상담 안내·판정 필드 부재 계약 테스트 통과(목록은 구현 계획에서 승인)

## 구현 계획

(11/22 T23·T24·T25·T10을 한꺼번에 작성. 표현 목록·부정문 규칙은 stash 초안을 그대로 씀)

### 바꿀 파일
| 파일 | 내용 |
|---|---|
| `app/services/safety.py`(새) | 표현 목록 4묶음(통장·계좌·체크카드 대여·양도 / 비밀번호·OTP 전달 / 환전·구매대행·송금 알바 / 현금 인출 후 전달). 걸린 곳 뒤 15자 안에 `적이 없`·`지 않`·`않았`·`거절`·`거부`가 있으면 뺌. `find_phrases(texts) -> list[str]`(걸린 글자, 나온 순서, 중복 없음). 안내 문구·연락처(132, 1332) 상수 |
| `app/services/analysis.py` | 시작할 때 사연 + 지금까지의 답을 검사해 `RunContext.safety_hits`로 넘김. 상담 안내로 끝난 실행은 사용 기록 `referral=true` |
| `app/agent/output.py`, `runner.py` | `out.referral = Referral(phrases)`. 상담 안내면 runner가 ③ 초안 단계를 건너뜀(단계 표시는 그대로 넘어감) |
| `app/agent/scripted.py` | 걸린 표현이 있으면 대조·초안 대신 step `SAFETY` + `referral` + 고정 질문 1개("어떤 상황에서 통장(계좌)을 건네거나 돈을 옮기게 됐는지 알려 주세요") |
| `app/agent/compare.py` | 첫 메시지에 `checkPhrases`(걸린 표현을 가린 글). 출력 스키마 `consult {recommend, quotes[], reason}`. 프롬프트: 문맥을 읽고 정함, 부정문이면 권하지 않음, 권하면 사연·답 원문 인용과 상황을 묻는 질문 |
| `app/agent/verify.py` | `consult` 확인: 인용이 가린 사연·답에 있으면 그 인용이 `matchedPhrases`. 없으면 코드 목록이 찾은 표현, 그것도 없으면 상담 안내 안 하고 step `VERIFY`. AI가 권하지 않으면 step `SAFETY`("'…'는 문맥상 상담 안내 안 함", 이유에 판정 표현이 있으면 이유 빼고) |
| `app/services/results.py` | 상담 안내면 `referral_json` 저장, 대조·AI 권장 항목·의견은 저장 안 함, **사건의 초안 행 삭제**. 조회: `referral {code, matchedPhrases, message, contacts}`, `findings: []`, `draft: null`, `summary` 모두 0, 체크리스트는 평소대로, `agentReview`는 질문만 |
| `app/schemas/result.py` | `referral: dict` → `Referral` 모델 |

### 계약 테스트(승인 필요)
| # | 내용 |
|---|---|
| T10-a | 상담 안내(가짜 분석): "통장을 빌려주고" 사연 → `SUCCEEDED`, step `SAFETY`, `referral` 모양(`LEGAL_CONSULT`, `matchedPhrases`, 132·1332), `findings: []`, `draft: null`, `summary` 모두 0, `GET /draft` 404, `agentReview.questions` 1개 이상 |
| T10-b | 다시 분석해 상담 안내로 끝나면 이전 초안 행이 지워지고 `GET /draft` 404 |
| T10-c | 걸리지 않음: 두 샘플 사연, "통장을 빌려준 적이 없습니다" → `referral: null` |
| T10-d | AI 문맥 확인(가짜 SDK): 원문에 없는 인용만 내면 코드가 찾은 표현으로 안내, 코드도 못 찾았으면 안내 없음 + step `VERIFY`, AI가 권하지 않으면 코드가 찾았어도 안내 없음 + step `SAFETY` |
| T10-e | 판정 필드 부재: GOODS·UNEXPECTED·상담 안내 결과와 초안 JSON 전체 키(중첩, `agentReview` 포함)에 판정성 단어(`release`·`accept`·`approv`·`verdict`·`judg`·`decision`·`likelihood`·`probab`·`chance`·`score`·`outcome`·`eligib`·`predict`)가 없음 |

### 정할 것(추천)
1. 표현 목록 검사 위치: **분석 시작 때 서비스 계층에서 원문 사연·답으로**(추천, CLAUDE.md "services/ 상담 안내 검사"). AI에 넘길 때는 runner가 가린다
2. 상담 안내 결과의 의견: **비움, 질문만**(추천). 상담이 먼저인 사안에 법령 의견을 내지 않는다
3. 체크리스트의 AI 권장 항목도 저장 안 함(추천, 대조를 안 쓰므로)
4. step `SAFETY`는 표현이 걸렸을 때만(추천). 안 걸린 실행의 step 목록은 지금과 같다

## 결정

- 11/22 사용자 "추천안대로": 정할 것 1~4 추천안, 계약 테스트 T10-a~e 승인
- 11/22 구현 중 보충
  - 표현 목록에서 그냥 "카드"는 뺐다("카드를 판매하는 가게"가 걸림). "체크카드·직불카드"만. 1묶음에 `건네·건넸`을 넣음(agent-design 2.1 예시 "체크카드를 건넸고")
  - 상담 안내 결과는 `unreadEvidence`도 `[]`(summary 0과 맞춤), 의견 없음, 질문의 대조 번호는 뗌(대조가 없으므로)
  - AI가 권했는데 질문을 안 냈으면 고정 질문 하나("어떤 상황에서 통장(계좌)을 건네거나 돈을 옮기게 됐는지 알려 주세요")
  - 확인 로직은 `app/agent/consult.py`(계획의 `verify.py` 대신 새 파일. 가짜 분석도 같이 써서)
  - T10-e: `acceptedDocTypes`(계약의 받는 서류 종류 칸)는 `accept`가 들어가지만 판정과 무관해 예외로 둠
  - 프롬프트 버전: 대조 `t10-v1`(초안은 `t25-v1` 그대로)

## 결과

- `app/services/safety.py`(새): 표현 목록 4묶음 + 부정문 제외, 안내 문구·연락처. `app/services/analysis.py`가 시작 때 사연·답 원문으로 찾아 `RunContext.safety_hits`로 넘김, 상담 안내면 사용 기록 `referral=true`
- `app/agent/consult.py`(새): `by_phrases`(가짜·미리 만든 결과), `check_consult`(AI 권유 + 원문 인용 확인, T10-d 규칙)
- `app/agent/compare.py`: 첫 메시지 `checkPhrases`, 출력 `consult {recommend, quotes, reason}`, 상담 안내면 대조·의견·권장 서류 버리고 질문만. `app/agent/scripted.py`: 표현이 있으면 step `SAFETY` + 고정 질문. `app/agent/runner.py`: 상담 안내면 ③ 초안 건너뜀
- `app/services/results.py`: `referral_json` 저장, 사건 초안 행 삭제, 조회 때 `referral`·빈 결과·summary 0. `app/schemas/result.py`: `Referral` 모델
- 테스트: `tests/test_t10_referral.py`(T10-a~e + 표현 묶음 단위), `test_t16_compare.py` T16-a 칸 목록에 `consult`·`recommend`·`quotes`
- `uv run python -m pytest -q` 197 passed·2 skipped, `uv run ruff check .` 통과(11/22)
- 로컬 실서버(가짜 분석, 비용 0): 일반 분석 뒤 초안 200 → 통장 대여 사연으로 다시 분석하면 step `SAFETY`, `referral`(`통장을 빌려`, 132·1332), 대조·초안 비움, 질문 1개, `GET /draft` 404 → 사연을 고치고 질문에 답해 다시 분석하면 상담 안내 풀림·초안 생김·`answered` 1개
- 미검증: 실제 Claude의 문맥 판단(새 프롬프트 `t10-v1`은 가짜 SDK로만 확인), 배포 서버


