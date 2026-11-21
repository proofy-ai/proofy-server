# T08 가짜 분석기 + 결과 API

- 단계: 2단계 가짜 분석 · 예정: 11/22 오전 · 상태: 계획 확인 · 이슈: #10 · PR: 없음

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

> 계약 v0.6.3 4.8·4.10·4.11·7절, ERD v1.1 3.4·3.6·3.7·3.8, `docs/agent-design.md` 2.4 기준. T07 위에 쌓는다(브랜치 `feat/10-scripted-result`는 T07 브랜치에서 만들고, T07 머지 뒤 PR).

### 파일

| 파일 | 내용 |
|---|---|
| `app/agent/scripted.py` | 가짜 분석기. 시나리오별 고정 대조 결과·거래 행·step·AI 권장 항목을 **데이터로** 돌려준다(DB를 만지지 않음). 단계마다 `SCRIPTED_STAGE_DELAY_SECONDS`만큼 쉰다 |
| `app/agent/output.py` | 분석기 출력 모양(`AnalysisOutput`: 거래 행, findings와 근거, 권장 자료). T16 Claude 분석기도 같은 모양을 낸다 |
| `app/models/finding.py` | `ClaimFinding`, `FindingSource`(ERD 3.6·3.7, `source_kind`별 CHECK) |
| `app/models/transaction.py` | `Transaction`(ERD 3.4) |
| `app/models/checklist.py` | `analysis_run_id`에 FK(ON DELETE CASCADE) |
| `app/services/results.py` | 출력 저장(근거를 **이 사건의 증빙·이번 실행의 거래**에만 연결), 결과 응답 만들기, 요약 계산 |
| `app/services/checklist.py` | 가장 최근 성공 실행의 `AI_RECOMMENDED` 항목을 더함. 고정 목록에 이미 있는 `docType`만 받는 권장 항목은 거름 |
| `app/schemas/result.py` | `ResultResponse`, `Finding`, `FindingSource`(종류별 필드), `Summary` |
| `app/api/result.py` | `GET /cases/{id}/result` |
| `tests/test_t08_result.py` | 아래 테스트 |

### 가짜 분석기가 내는 것

분석기는 **사건의 입금 유형**으로 시나리오를 고른다(샘플이 아닌 직접 만든 사건도 FE 개발에 쓸 수 있게). 근거는 그 사건에 올린 서류 중 `docType`이 맞는 첫 서류에 붙인다. 맞는 서류가 없으면 그 근거를 빼고, 근거가 하나도 안 남은 `MATCH`는 `UNKNOWN`으로 바꾼다(agent-design 2.4 규칙과 같음).

**`GOODS`(test01) — 계약 4.11 예시와 같게**

| | 주장 | 상태 | 근거 |
|---|---|---|---|
| f1 | 11월 8일 거래처에서 15만 원을 입금받았다 | `MATCH` | 사연 "11월 8일 대금을 계좌로 받았습니다" + 거래 11/08 입금 150,000원 `김*수` |
| f2 | 가죽 지갑 3개를 15만 원에 납품하기로 했다 | `CONFLICT` `AMOUNT` 150,000원 ↔ 120,000원 | 대화내역 1쪽 12번 줄 "3개 12만원에 할게요" |
| f3 | 물건을 다음 날 택배로 보냈다 | `STATEMENT_ONLY` | 사연 "물건은 다음 날 택배로 보냈습니다" |

- 거래 행(거래내역서에 붙임): 11/03 입금 32,000 `박*진`, 11/08 입금 150,000 `김*수`, 11/10 출금 45,000
- AI 권장: "택배 발송 기록(송장 번호 화면)" `SHIPPING`, note는 계약 4.8 예시 문구
- steps: `OCR` 서류마다 1줄 → `TOOL_CALL` "사연의 11월 8일 대금 입금을 확인하려고 11/1~11/10 입금을 조회 → 2건" → `FINDING` → `CONFLICT` "대화내역의 합의 금액(120,000원)이 사연·입금액(150,000원)과 다릅니다" → `DRAFT`(초안은 T09)

**`UNEXPECTED`(test02) — 계약 4.3.1 표**

| | 주장 | 상태 | 근거 |
|---|---|---|---|
| u1 | 11월 11일 모르는 사람에게서 10만 원이 입금됐다 | `CONFLICT` `DATE` 11월 11일 ↔ 11월 12일 | 사연 인용 + 거래 11/12 입금 100,000원 `이*호` |
| u2 | 받은 돈은 쓰지 않고 그대로 두었다 | `MATCH` | 사연 인용 + 같은 입금 행, note "입금 뒤 이 금액이 빠져나간 거래가 없습니다" |
| u3 | '20만 원 보내면 신고 취하해 줄게'라는 문자를 받았다 | `MATCH` | 협박 문자 1쪽 인용 + 사연 인용 |
| u4 | 바로 은행에 알렸다 | `STATEMENT_ONLY` | 사연 인용 |

- 거래 행: 11/09 출금 23,000, 11/12 입금 100,000 `이*호`
- steps: `OCR` → `TOOL_CALL` "사연의 11월 11일 입금을 확인하려고 11/8~11/14 입금을 조회 → 1건" → `TOOL_CALL` "입금 뒤 돈이 빠져나갔는지 확인하려고 11/12~11/18 출금을 조회 → 0건" → `CONFLICT`(날짜) → `DRAFT`
- AI 권장 항목 없음(아래 "정할 것" 1)

**`SALARY`·`OTHER`(직접 만든 사건용)**: 사연 첫 문장을 주장으로 한 `STATEMENT_ONLY` 1건, 거래 행 없음, AI 권장 없음

### 저장·응답 규칙

- 사연 인용(`NARRATIVE`)의 `verified`는 코드가 정한다: `masked_narrative`(scripted는 마스킹 전이라 사연 그대로, T14가 바꿈)에 공백을 무시하고 들어 있으면 `true`. **샘플 사연을 고쳐 분석하면 그 인용은 `false`로 흐리게 나온다**
- 서류 인용(`EVIDENCE`)은 글자 추출(T13)이 없어 대조할 원문이 없으므로 scripted 고정값 `true`. 실제 대조는 T17
- 거래 근거는 이번 실행이 만든 거래 행 ID만 쓴다. 증빙·거래는 저장 전에 같은 사건 소속인지 확인한다(어긋나면 근거를 빼고 서버 로그). 전체 검증기는 T17
- `GET /cases/{id}/result`: 가장 최근 `SUCCEEDED` 실행, 없으면 404 `NOT_FOUND`
  - `isStale` = 사건 `inputVersion` ≠ 실행의 `basedOnInputVersion`, `generatedAt` = 실행 `finishedAt`
  - `precomputed: false`(T11), `referral: null`(T10), `draft: null`(T09), `aiNotice`는 계약 문구 고정
  - `checklist`는 4.8과 같은 함수로(AI 권장 = 이 실행 것만), `unreadEvidence` = `extract_status=FAILED` 서류(T13 전에는 항상 `[]`)
  - `summary`: `findingCounts`는 네 상태 모두 키를 둔다, `missingDocuments` = 체크리스트 `missingCount`, `sentencesNeedingCheck` = 0(T09가 채움), `unreadEvidence` 개수
- 다시 분석해도 이전 실행 행은 지우지 않고 조회에서 거른다(ERD 4절)

### 테스트

결과 응답 모양과 사건 간 근거 교차 차단은 계약 테스트라 목록 승인을 받는다.

| # | 내용 | 승인 |
|---|---|---|
| 8 | **결과 응답 모양 핵심:** `GOODS` 샘플 분석 → 4.11의 최상위 키 전부, findings 3개(`MATCH`·`CONFLICT`·`STATEMENT_ONLY`), `CONFLICT`의 `conflict = {AMOUNT, "150,000원", "120,000원"}`, 근거 종류별 필드(`TRANSACTION`은 `transactionId`·`amountKrw`·`direction` 등), `summary.findingCounts`가 findings와 일치, 체크리스트에 `AI_RECOMMENDED` 택배 항목 | 11/21 승인됨 |
| 9 | **사건 간 근거 교차 차단:** 같은 시나리오 샘플 사건 두 개를 분석 → 각 결과의 `evidenceId`·`transactionId`가 모두 자기 사건 것 | 11/21 승인됨 |
| T08-a | 분석 전 결과 조회 404 `NOT_FOUND` | 11/21 승인됨 |
| T08-b | 두 번 분석 → 결과·AI 권장 항목이 두 번째 실행 것만(권장 항목이 겹쳐 2개가 되지 않음) | 11/21 승인됨 |
| T08-c | 분석 뒤 사연 수정 → `isStale: true`, 고친 사연의 인용은 다시 분석하면 `verified: false` | 11/21 승인됨 |
| T08-d | `UNEXPECTED` 샘플 → `DATE` 충돌 1건, `MATCH` 2건, `STATEMENT_ONLY` 1건 | 11/21 승인됨 |

판정 필드 부재 테스트는 T10에서 한다(범위 그대로).

### 정할 것

1. **`UNEXPECTED`의 "AI 권장: 신고 내역"은 AI 권장 항목으로 내지 않는다.** 고정 목록에 이미 `INCIDENT_REPORT`(피해 신고 기록, `OTHER`)가 있어 "고정 목록과 같은 `docType`이면 거른다" 규칙에 걸리고, 탭 B에 같은 서류가 두 번 나오게 된다. 대신 u4(`STATEMENT_ONLY`)의 note를 "사연에만 있고 신고 기록이 없습니다. 탭 B의 피해 신고 기록을 확인해 주세요."로 둔다. 계약 4.3.1 표 문구만 고친다(v0.6.4, 응답 모양 변경 없음)
2. **가짜 분석기는 샘플이 아닌 사건에도 입금 유형별 고정 결과를 낸다.** FE가 직접 만든 사건으로도 결과 화면을 붙일 수 있게. 실제 서류 내용과는 무관한 결과라 `GET /health`의 `agent: scripted`로 구분한다
3. **T12 합성 서류는 이 고정값에 맞춰 만든다:** 대화내역 1쪽 12번 줄 "3개 12만원에 할게요", 거래 행 금액·날짜·상대방(위 표)
4. 대체 결과(T11)는 이 시나리오 결과를 그대로 쓴다(계약 7절)

## 결정

- 11/21 사용자 승인: 계획, 계약 테스트 8·9와 T08-a~d, 정할 것 1~4(추천대로). 1의 계약 문구(v0.6.4)는 이슈 #40에서 먼저 고침. T08은 finding `note`·step `summary`를 항상 문장으로 채운다(FE 타입이 null을 받지 않음, #40 대조)

## 결과

