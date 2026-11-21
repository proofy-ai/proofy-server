# Proofy AI 에이전트 설계와 진행 계획

- 작성일: 2026-11-21 · 개정: 2026-11-21(진행 계획·가져오는 코드·심사 기준 대응 추가, 이슈 #29) · 마감 2026-11-23(월) 17:00
- 관련 문서: `docs/contract.md`(API 계약 정본), `docs/erd.md`(데이터 정본), `docs/screen-flow.md`(화면), `docs/tasks/`(작업)
- 한 줄 요약: **AI는 판사가 아니라 정리 담당이다.** 사용자의 사연과 올린 서류를 맞대어 "자료와 맞음 / 어긋남 / 자료 없음"으로 정리하고, 그 정리만 가지고 소명서 초안을 쓴다. 해제될지는 말하지 않는다. 숫자·날짜·기한은 코드가 만들고, AI가 쓴 것은 코드가 다시 검증한다.

## 1. Proofy가 맡는 곳

### 이의제기 5단계 중 2단계

일반적인 이의제기 흐름(참고: [법률사무소 안내 글](https://www.yglaw.co.kr/bbs/board.php?bo_table=lawinfo&wr_id=27), 법령 기준 절차는 `docs/screen-flow.md`)과 Proofy의 역할이다.

| 단계 | Proofy | 비고 |
|---|---|---|
| 1 지급정지 사실 확인 | 일부(화면 2) | 통지일·공고일 입력, D-day. 사유 확인은 은행에 직접 |
| **2 소명 자료 준비** | **핵심(화면 3·4·5)** | 체크리스트, 사연–자료 대조, 소명서 초안. **AI가 일하는 곳은 여기뿐** |
| 3 신청서 제출 | 안내(화면 6) | 초안을 신청서 사유란에 옮겨 적게 안내. 은행 연동 없음 |
| 4 심사·결정 | **하지 않음** | 은행의 판단이다. 해제 가능성을 보여 주면 원칙 1 위반 |
| 5 불수용 시 대응 | 안내(화면 6, 정적) | 법률 상담(대한법률구조공단 132) 안내 한 줄 |

### 소명 자료 3분류와 초안 구조

같은 글은 소명 자료를 세 가지로 나눈다. Proofy는 이 분류를 **초안의 묶음(`DraftSection`)** 으로 쓴다.

| 분류 | 보여 주는 것 | 초안 묶음 | Proofy에서 |
|---|---|---|---|
| 01 입금 경위 | 어디서 왜 들어온 돈인지 | `DEPOSIT_REASON` | ② 대조가 바로 이 일을 한다(사연 + 거래내역서 + 대화) |
| 02 범죄 가담 의사 없음 | 정상 거래였다는 정황 | `NO_INVOLVEMENT` | 대화·계약서·사업자등록. 문장은 **사용자 본인의 진술**로 쓰고 AI가 사실로 단정하지 않는다 |
| 03 사기 피해 경위 | 오히려 내가 피해자라는 기록 | `VICTIM_CONTEXT` | 협박 문자, 신고 기록(`INCIDENT_REPORT`). 통장 묶기(test02)의 핵심. 정황이 없으면 이 묶음은 쓰지 않는다 |

## 2. 에이전트 흐름

```text
POST /analysis-runs (202) → 백그라운드 실행, 마감 150초
  ⓪ SAFETY      [코드]      상담 안내 표현 검사 → 걸리면 여기서 끝(referral)
  ① EXTRACTING  [코드]      글자 추출 → 마스킹
  ①-b           [AI 1회]    거래내역서 → 거래 행 (+ 코드가 원문 대조)
  ② COMPARING   [AI 도구 루프] 사연 주장 ↔ 자료 대조 → findings, AI 권장 자료
  ③ DRAFTING    [AI 1회]    findings만 가지고 초안 문장 + 근거 번호 + 묶음
  ④ VERIFY      [코드 → AI 1회 → 코드] 후검증, 고칠 수 있는 문장만 AI가 1회 고쳐 쓰고 재검증
```

화면 단계(`stages`)는 ①·②·③ 세 개다. ⓪은 ①에, ①-b는 ①에, ④는 ③에 포함해 보여 준다. 각 단계에서 한 일은 `steps`에 한 줄씩 남는다(계약 4.10).

아래 예시는 체험 계정 test01(물품 거래)이다. 사연 "11월 8일 거래처에 가죽 지갑 3개를 15만 원에 납품하고 대금을 받았습니다", 거래내역서(11/8 입금 150,000원), 판매 채팅("3개 12만원에 할게요", 일부러 어긋나게 만든 자료).

### 2.1 ⓪ SAFETY — 상담 안내 (T10, 코드)

- 사연을 정해 둔 표현 목록(통장·계좌·체크카드 대여·양도, 비밀번호 전달, 환전·구매대행·송금 알바, 현금 인출 후 전달 등)으로 검사한다.
- 걸리면 AI를 부르지 않고 `SUCCEEDED`로 끝낸다. 초안 없이 `result.referral`만 준다. step `SAFETY`.
- 사람을 판정하는 것이 아니라 표현이 있는지만 본다. 걸린 표현을 그대로 보여 준다.

### 2.2 ① EXTRACTING — 글자 추출과 마스킹 (T13·T14, 코드)

| 입력 | 처리 | 출력(DB) |
|---|---|---|
| 올린 서류(PDF·PNG·JPG) | 글자가 든 PDF는 OCR 없이 추출(`pypdf`). 사진·스캔 PDF는 전처리 후 Tesseract OCR | `evidence.regions_json` 줄 단위 `{index, page, text, bbox, confidence}` |
| 추출한 글자 | 주민번호·계좌·전화·이름을 가림(`김민수` → `김*수`) | `evidence.masked_text`, 영역마다 `maskedText` |

- 못 읽은 서류는 `FAILED`로 두고 분석을 계속한다. 결과의 `unreadEvidence`로 "직접 확인"에 넘긴다.
- **AI에는 마스킹한 글자만 간다.** 원본 이미지는 외부로 보내지 않는다. 인용 검증도 마스킹본 기준이다(AI가 본 글과 대조해야 하므로).
- 시연 서류는 글자가 든 PDF로 만든다(T12). 대조 품질이 거래내역서 인식에 달려 있기 때문이다. 사진 OCR은 Docker 이미지에서 동작을 확인한다.

### 2.3 ①-b 거래 행 추출 (T15, AI 1회 + 코드)

- 입력: 거래내역서의 마스킹 글자. 출력(구조화): `rows[] = {occurredAt, direction, amountKrw, counterparty, regionIndex}`.
- **코드 검사:** 금액·날짜 문자열이 그 `regionIndex` 줄에 실제로 있는 행만 `transactions`에 저장한다. 없으면 버리고 step에 남긴다.
- 늦어지면 텍스트 PDF 규칙 파싱만 한다(시연 서류 형식은 우리가 정한다).

### 2.4 ② COMPARING — 대조 (T16, AI 도구 루프)

AI에게 거래내역을 통째로 주지 않고 **조회 도구**를 준다.

| 도구 | 인자 | 돌려주는 것 |
|---|---|---|
| `get_transactions` | `reason`, `from`, `to`, `direction?`, `counterparty?`, `minAmount?`, `maxAmount?` | 이 사건의 거래 행 `{transactionId, occurredAt, direction, amountKrw, counterparty(가림)}` |
| `get_evidence_regions` | `reason`, `evidenceId`, `page?` | 이 사건 서류의 줄 `{regionIndex, page, text(가림)}` |

- 첫 메시지: 사연(가림), 사용자가 말한 입금(유형·금액·일자), 서류 목록(`evidenceId`, `docType`, 쪽 수, 앞부분 몇 줄).
- **`reason`(조회 이유 한 문장)은 필수 인자다.** 서버는 이를 step `TOOL_CALL`의 `summary`로 남긴다: "사연의 11월 8일 대금 입금을 확인하려고 11/1~11/10 입금을 조회 → 2건". 4번 화면에서 AI가 스스로 무엇을 왜 찾는지가 보인다.
- 도구는 **이 사건 소속 행만** 조회한다. 서버는 도구가 실제로 돌려준 거래 ID를 모아 둔다(후검증 기준, `analysis_runs.steps_json`).
- 상한: 도구 호출 8회, 도구 결과 60,000자(넘으면 앞부분만 주고 범위를 좁혀 다시 조회하라고 알림). 넘으면 지금까지 본 자료로 답하게 한다.
- 최종 출력(구조화, `output_config.format`):

```text
findings[]        = { claim, status: MATCH | CONFLICT | STATEMENT_ONLY | UNKNOWN, note,
                      conflict: { field: AMOUNT | DATE | COUNTERPARTY | OTHER, statement, found } | null,
                      sources[]: { kind: NARRATIVE | EVIDENCE | TRANSACTION, quote?, evidenceId?, regionIndex?, transactionId? } }
recommendedDocs[] = { label, reason, acceptedDocTypes[] }   → 체크리스트 AI_RECOMMENDED
```

- **판정 필드는 스키마에 없다**(해제 가능성, 수용 여부, 위험도 등). 프롬프트로만 막지 않는다.
- test01 예시 결과: f1 "15만 원 입금" `MATCH`(t3) · f2 "15만 원에 합의" `CONFLICT`(채팅 12번 줄 "3개 12만원에 할게요") · f3 "다음 날 택배" `STATEMENT_ONLY`. f2는 step `CONFLICT`로 바로 보인다. **시연의 핵심 장면**이다.
- 대조 결과 검증(코드, 저장 전):
  - 인용문이 그 서류 줄(또는 사연)에 공백을 무시하고 들어 있나 → 아니면 `verified: false`(흐리게 표시, 지우지 않음)
  - `evidenceId`·`regionIndex`가 이 사건에 있나, `transactionId`가 이번 실행의 도구가 돌려준 ID인가 → 아니면 그 근거를 빼고 step `VERIFY`에 남긴다. 근거가 하나도 남지 않은 `MATCH`는 `UNKNOWN`으로 바꾼다
  - 글자 수 상한으로 자른다(긴 출력 유도 방지)

### 2.5 ③ DRAFTING — 초안 (T17, AI 1회)

- 입력: 검증을 통과한 findings(번호로), 입금 유형, 묶음 규칙.
- 출력(구조화): `sentences[] = { section: DraftSection, text, findingIds[] }`. `findingIds`는 **준 번호만 고를 수 있게 enum으로 고정**한다.
- 묶음 순서: `DEPOSIT_REASON` → `NO_INVOLVEMENT` → `VICTIM_CONTEXT`(정황이 있을 때만). `NO_INVOLVEMENT` 문장은 1인칭 진술("본인은 … 알지 못했습니다")로 쓰게 한다.
- 문체: 은행에 내는 존댓말 서술. 판정·예측 표현 금지.

### 2.6 ④ VERIFY — 후검증과 1회 고쳐 쓰기 (T17, 코드 → AI → 코드)

문장마다 검사하고, 걸린 문장은 `needsCheck: true` + 사유(계약 `NeedsCheckReason`, 앞의 것 하나).

| 검사 | 사유 | AI가 고쳐 쓸 수 있나 |
|---|---|---|
| CONFLICT 항목에 연결됐거나, 문장 속 금액·날짜가 CONFLICT 항목의 진술 값과 같음(서버가 연결을 붙임) | `CONFLICT` | 아니요. 사용자가 사실을 확인할 일 |
| 근거 번호가 없음 | `NO_SOURCE` | 아니요. 고치게 하면 근거를 지어낼 수 있음 |
| 근거의 인용이 원문에 없음 | `QUOTE_NOT_FOUND` | 아니요 |
| 문장 속 숫자가 인용한 근거에 없음 ("30만 원" → 300000으로 읽어 비교) | `NUMBER_MISMATCH` | **예** |
| 판정처럼 읽히는 표현("해제될 것", "확실히", "승인") | `JUDGMENT_EXPRESSION` | **예** |
| 근거 서류를 못 읽음 | `SOURCE_UNREAD` | 아니요 |

- **1회 고쳐 쓰기:** `NUMBER_MISMATCH`·`JUDGMENT_EXPRESSION`에 걸린 문장이 있고 마감까지 40초 이상 남았으면, 그 문장들만 오류 사유와 함께 AI에 다시 보내 고쳐 쓰게 한다(같은 `findingIds` 유지). 다시 검사해서 통과하면 고친 문장을 쓰고, 또 걸리면 **원래 문장을 두고** "확인 필요"로 표시한다. 문장을 지우지 않는다.
- step `VERIFY`: "근거와 다른 숫자 1개를 AI가 고쳐 다시 확인했습니다", "확인 필요 문장 2개".
- 어느 문장에도 연결되지 않은 CONFLICT → `draft.warnings`(`CONFLICT_NOT_IN_DRAFT`).
- 체크리스트 충족 여부는 코드가 계산한다(유형별 목록 상수 × 올린 서류 `docType`).

### 2.7 실패와 대체

| 상황 | 처리 |
|---|---|
| 모델 거절 | 서버측 fallback이 다른 모델로 다시 돌린다. 그래도 거절이면 `AGENT_REFUSED` |
| 일시 오류(429·5xx·연결) | 마감 안에서만 재시도(`retry-after` 존중) |
| 150초 초과 | `AGENT_TIMEOUT` |
| 샘플 사건에서 AI 실패·하루 한도 초과 | 미리 만든 결과로 `SUCCEEDED`, `precomputed: true`, step `FALLBACK` |
| API 키 없이 개발·CI·리허설 | `AGENT_LLM=scripted` 가짜 분석기(T08). 응답 모양은 같다 |

## 3. 왜 이 형태인가

- **AI가 필요한 곳에만 AI.** 자유 서술한 사연과 비정형 서류(채팅 캡처, 거래내역)를 맞대어 보는 일은 규칙으로 못 한다 → AI. D-day·금액 비교·체크리스트 충족처럼 틀리면 안 되는 계산 → 코드.
- **AI가 스스로 판단하는 부분은 ②에 모았다.** 어느 기간·상대를 조회할지, 어느 서류를 더 읽을지는 모델이 고른다. 나머지는 코드라 시연이 흔들리지 않는다.
- **판정 없음을 스키마로 보장한다.** 출력 스키마에 판정 필드가 없다.
- **독립된 원문이 있어야 검증이 된다.** Claude 비전으로 서류를 바로 읽히면 "AI가 읽은 글"과 "AI가 인용한 글"을 같은 AI가 만들어 검증이 순환한다. 로컬 추출 글자가 기준이 된다.
- **도구 루프라서 "조회한 거래만 인정" 검증이 된다.** 거래내역을 통째로 주면 더 빠르지만 AI가 본 것과 안 본 것을 구분할 수 없다.
- **"원장"은 사용자가 낸 거래내역서다.** 신청인은 은행 원장을 볼 수 없다. 오픈뱅킹·마이데이터 연동은 확장 항목(`transactions.source`)이다(`docs/erd-review.md`).
- **LangGraph 같은 프레임워크를 쓰지 않는다(11/21 결정).** 흐름이 정해진 한 줄이고 고리는 ② 도구 루프와 ④ 1회 고쳐 쓰기뿐이라 직접 짠 코드가 짧다. 루프 안에 step 기록·호출 상한·마감·조회 ID 수집을 끼워야 하고, 외부 AI 호출이 `agent/llm.py` 한 곳이어야(원칙 4) 전송 경로를 보여 줄 수 있다. 의존성을 늘리면 이 PC의 애플리케이션 제어와 시연 안정성에도 위험이 된다.

## 4. 심사 기준 대응

배점(대회 안내문 4·5쪽): 예선 **AI 활용 적절성 25점**(가장 큼, 동점 시 1순위), 프로토타입 20점. 본선 AI 활용 수준 25점 + 질의응답의 "AI 활용 방식 이해도" 5점. 제출(11/23 17:00) 뒤에는 기능·프롬프트를 바꿀 수 없다.

| 심사 항목 | Proofy의 답 | 어디서 보이나 |
|---|---|---|
| AI를 쓰는 이유·방식이 적절한가(10) | 3절 첫 줄의 역할 나눔(비정형 대조 = AI, 계산 = 코드) | 소개서 "AI를 활용한 해결 방안" 표 |
| AI가 핵심 기능에 실질적으로 기여하나(10) | ② AI가 조회 범위를 스스로 고르고 이유를 밝힘 · CONFLICT 발견(12만/15만) · ③ 소명 자료 3분류 구조의 초안 · ④ 스스로 고쳐 쓰기 · 사건별 권장 자료 | 4번 화면 step 타임라인, 5번 화면 탭 A 경고·탭 B AI 권장·탭 C 묶음 초안 |
| 오류·불확실성 대응(5) | 인용 원문 대조, 조회한 거래만 인정, 같은 사건 소속, 숫자 대조, 판정 표현 검사, "확인 필요"와 직접 확인 체크, 복사 전 확인창, 못 읽은 서류 표시, 미리 만든 결과 대체 | 7절 표를 소개서 "AI 결과의 한계"에 그대로 |
| 프로토타입 안정성(20) | scripted 모드, 샘플 대체 결과, 서류 하나 실패해도 계속 | 시연 |
| 비용·운영 부담(10) | 건당 비용 실측, 한도(사건당 시간당 5회, 하루 300회), 캐시 | 소개서 "활용·확장 가능성" |
| 질의응답 이해도(5) | 프레임워크 없이 직접 짠 짧은 코드, 이 문서 | 발표 |

## 5. 모델·API 설정 (T16 `agent/llm.py`)

| 항목 | 결정 | 이유 |
|---|---|---|
| 표면 | Claude **Messages API**(`anthropic` Python SDK 1.x) + 직접 짠 도구 루프 | 단계가 코드로 정해진 워크플로이고 루프 안에 기록·검증을 끼워야 한다. Managed Agents는 쓰지 않는다 |
| 모델 | `claude-opus-5-5` | corebank 측정: effort low에서 건당 $0.04, 17초. Proofy는 호출 3~4회라 건당 $0.1 안팎, 30~60초 예상(실측 필요, T19) |
| effort | `output_config.effort: "low"`로 시작 → 측정 후 조정 | Opus 5.5 기본값은 `medium`이라 명시한다 |
| thinking | 파라미터를 넣지 않는다(adaptive로 돈다) | Opus 5.5는 `disabled`를 보내면 400. 응답 블록은 바꾸지 않고 그대로 이력에 붙인다 |
| 출력 | `output_config.format` JSON 스키마 | 프리필·강제 `tool_choice`(any/tool)는 400. 스키마로 형식 보장 |
| 거절 대응 | `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"` | 금융·사기 문맥이라 안전 분류기 거절 대비. 대신 답한 모델은 `response.model`로 기록하고 그 단가로 비용 계산 |
| 캐시 | 요청 최상위 `cache_control`(자동 캐시) | 도구 루프에서 앞 턴 이력을 캐시 읽기로. corebank의 캐시 지점 옮기기 함수가 필요 없다 |
| 재시도 | SDK 재시도는 끄고(`max_retries=0`) 실행 마감을 보며 직접 | SDK 재시도는 마감을 모른다 |
| 입력 제한 | `llm.py`는 마스킹을 거친 글자 타입만 받는다 | 원칙 4를 코드 구조로 보장 |
| 키 | `.env`의 `ANTHROPIC_API_KEY`. 배포 키는 T18에서 따로 | 원칙 5 |

서버 스택: Python 3.12, FastAPI, SQLAlchemy, Pydantic v2. 분석 실행은 FastAPI 백그라운드 작업(사건당 동시 1개). OCR은 Docker 이미지에 `tesseract-ocr tesseract-ocr-kor`. 배포에서 OCR이 막히면 추출기를 바꿀 수 있게 인터페이스로 둔다.

## 6. 가져오는 코드

### 기준

- 대회 기준(안내문 3-(2), AI 활용 기준 제6조): 타 대회 출품작이 아니면 기존 코드를 쓸 수 있고, **범용 코드는 출처와 활용 범위를 공개**한다. corebank·DonWorry는 이용 권한이 있고 다른 대회에 낸 적이 없다(11/21 사용자 확인). 두 레포 모두 LICENSE 파일은 없다.
- CLAUDE.md 원칙 6: 범용 유틸(OCR 전처리, API 재시도·비용 계산 등)은 가져온다. **에이전트 흐름·검증·프롬프트는 새로 작성한다.** 두 레포 모두 기관(은행 심사자, 가맹점 보안 직원)이 판정하는 도구라 출력 구조부터 다르다.
- 가져올 때 커밋 메시지에 원본 레포·파일·범위를 적는다. 아래 표가 T20 소개서 별첨 "기존 개발물·사전 개발 내역"의 원본이다.

### 그대로 가져옴 (범용 유틸)

| 원본 | 범위 | 가져올 곳 | 바꿀 점 |
|---|---|---|---|
| corebank-objection-agent `objection_agent/preprocess.py` | 전체(1~140행): 방향·기울기·조명·잡음·해상도 보정, 원본 좌표 되돌리기(`Transform`) | T13 `app/agent/extract/preprocess.py` | 줄 길이 100 맞춤. 의존성 `Pillow` 추가 |
| corebank-objection-agent `objection_agent/ocr.py` | `detect_format`, `OcrError`, `OcrEngine`, `TesseractEngine`, `parse_tsv`, `_child_env`, `_binary`, `count_low_confidence`(1~293행 중 서버 계약 상한 상수 제외) | T13 `app/agent/extract/ocr.py` | 서버 계약 주석 제거, Tesseract 경로를 설정으로(Windows), 결과 모양을 `evidence.regions_json`에 맞춤. 텍스트 PDF 추출은 새로 작성 |
| corebank-objection-agent `objection_agent/llm/claude.py` | 단가표·`cost_micro_usd`(27~66행), 재시도 상수(41~51행), 마감 안 재시도 `_create`(153~173행), `_retry_after`(176~181행), `_tool_error`·`_tool_content`(198~211행), `_usage`(234~240행) | T16 `app/agent/llm.py` | 자동 캐시로 바꿔 `_mark_cache` 제외, 거절 시 `stop_details` 기록, 마스킹 글자 타입만 받기 |
| corebank-objection-agent `objection_agent/llm/port.py` | `Usage`(32~44행), `Deadline`(66~93행), 예외 클래스(54~63행) | T16 `app/agent/llm.py` | `Deadline`에서 서버 점유(lease) 시계 제거 |

### 방식만 참고하고 새로 작성 (핵심 기능)

| 원본 | 참고한 방식 | 새로 쓰는 곳 | Proofy에서 다른 점 |
|---|---|---|---|
| corebank `llm/claude.py` `analyze`·`_run_tool` | 도구 루프, `reason` 인자, 호출 상한, 응답 그대로 이력에 붙이기 | T16 `app/agent/compare.py` | 도구·출력 스키마가 다르고 판정 갈래 없음 |
| corebank `worker.py` `_check_quotes`·`_check_claim_sources`·`_keep_seen`·`_clamp`(288~378행) | 공백 무시 인용 대조, 없는 서류·영역 번호 비우기, 조회한 거래만 남기기, 길이 상한 | T16·T17 `app/agent/verify.py` | 원본 정규화가 암호화된 `prompts.sanitize`에 기대서 정규화도 새로 작성. 빼지 않고 `verified: false`로 표시 |
| DonWorry `ai-server/app/agent/narrative.py` `narrative_schema`·`_numbers`·`_style_errors`·`validate_narrative`(59~249행) | 근거 번호 enum 고정 스키마, 문장 속 숫자("만" 단위) 대조, 판정 문구 검사, 오류 사유를 붙여 다시 쓰기 | T17 `app/agent/drafting.py`, `verify.py` | 다시 쓰기는 고칠 수 있는 사유에만 1회, 실패하면 지우지 않고 "확인 필요" |
| DonWorry `ai-server/app/agent/assemble.py` | 숫자·ID·날짜는 AI가 아니라 코드가 채운다 | 전체 | 원칙 2 |
| corebank `steps.py`, `llm/scripted.py` | 단계 시작 = 앞 단계 끝, 시연용 단계 간격, API 키 없는 규칙 분석기 | T07·T08 | step은 서버 DB에 바로 저장 |

### 가져오지 않음

- corebank: `server.py`, `worker.py`의 대기열·작업 토큰·점유(인프라 과함), `policy.py`(판정 갈래 보정, 원칙 1 위반), `prompts.py`(git-crypt 암호화, 읽을 수 없음), `eval/`
- DonWorry: `llm.py`(Ollama·OpenAI), `graph.py`(LangGraph), `facts.py`·`tools.py`(결제 도메인)

## 7. 한계와 대응 (소개서 "AI 결과의 한계"에 그대로 쓸 것)

| 한계 | 대응 |
|---|---|
| OCR 오인식(사진 각도, 조명, 손글씨, 표 형태 거래내역 캡처) | 텍스트 PDF는 OCR 생략, 전처리, 신뢰도 낮은 영역 수 표시, 못 읽은 서류는 숨기지 않고 "직접 확인". 거래 행은 금액·일자 문자열이 원문에 있을 때만 저장 |
| 모델이 없는 사실을 씀 | 인용 원문 대조, 조회 안 한 거래 ID 제거, 문장 속 숫자 대조 → 실패 문장은 1회 고쳐 쓰고, 그래도 실패하면 "확인 필요" |
| 자료와 어긋난 내용이 초안에 그대로 들어감 | CONFLICT 연결·진술 값 일치 문장 자동 "확인 필요", 설명 안 된 CONFLICT 경고, 문장별 "직접 확인", 복사·저장 전 확인창(거짓 이의제기 처벌 안내) |
| 판정처럼 읽히는 문장 | 스키마에 판정 필드 없음 + 판정 표현 검사(조회 이유 문장 포함) + 화면 고지(`aiNotice`) |
| 기한 오산 | AI가 계산하지 않음. 공고일 없으면 "공고일 확인 필요", 있어도 "참고 계산, 은행 확인" |
| 서류 기준이 기사·보도자료 몇 건뿐 | 공식(법령)·유형별 안내(기사)·AI 분석용·있으면 좋은 자료·AI 권장을 체크리스트에서 구분해 표시 |
| 통장 대여·송금 대행처럼 처벌 위험이 먼저인 사안 | 표현 목록 검사에 걸리면 초안 대신 법률 상담 안내. 걸린 표현을 보여 주고 판정하지 않음 |
| 개인정보 | 신분증 미수집, 원본 이미지 외부 전송 없음, 마스킹한 글자만 AI로, 신청인 인적사항 미저장, 24시간 자동 삭제, 시연은 합성 데이터만 |
| AI 거절·장애 | 서버측 fallback, 샘플은 미리 만든 결과로 대체, scripted 모드 |

## 8. 작업별 진행 순서

| 작업 | 만드는 것(에이전트 관련) | 가져오는 코드 |
|---|---|---|
| T04 | 유형별 목록 상수(통장 묶기에 `INCIDENT_REPORT` 포함) | — |
| T07·T08 | 실행·단계 기록, scripted 결과(계약 4.10·4.11 예시와 같게, `section`·조회 이유 포함) | corebank `steps.py`·`scripted.py` 방식 |
| T10 | ⓪ 상담 안내 | — |
| T12 | 합성 서류: test01(거래내역서·판매 채팅·사업자등록), test02(거래내역서·협박 문자, 가능하면 신고 접수증) | — |
| T13 | ① 글자 추출 | corebank `preprocess.py`·`ocr.py` |
| T14 | ① 마스킹 | — |
| T15 | ①-b 거래 행 | — |
| T16 | `agent/llm.py`, ② 대조 루프(`reason` 표시), 대조 결과 검증 — **실제 Claude 첫 실행 목표 11/22 13:00** | corebank `claude.py`·`port.py` |
| T17 | ③ 초안(묶음), ④ 후검증 + 1회 고쳐 쓰기 | 방식만(worker, narrative) |
| T19 | 건당 비용·시간 실측, effort 조정, 고쳐 쓰기가 150초 안에 드는지 | — |
| T20 | 소개서 별첨(6절 표), AI 활용내역(5절) | — |

## 9. 남은 결정

1. 배포 환경(Render/Railway/Fly/VM) → OCR 설치 가능 여부. 11/22 오후 배포 전까지. Docker 이미지로 어디든 올릴 수 있게 한다
2. `INCIDENT_REPORT` 항목의 공식 근거(금감원·금융위 자료). 찾으면 `TYPE_GUIDE`로 올린다(T04)

### 지난 결정(11/21)

- 거래내역서는 모든 유형에서 분석 시작 조건. 시연용 합성 거래내역서 2종(물품 거래, 모르는 입금). 급여는 P1
- 심사자 체험: `POST /cases/sample`. 물품 거래 샘플은 청년 1인 판매 사업자, 대화 속 합의 금액과 입금액을 어긋나게 만들어 CONFLICT 흐름을 보여 준다
- 체험 계정 test01 물품 거래, test02 통장 묶기(`UNEXPECTED`). 샘플은 AI 실패·한도 초과 때 미리 만든 결과로 끝냄
- 통장 대여·송금 대행 사연은 초안 대신 법률 상담 안내
- 범용 코드 재사용, LangGraph 미사용, 조회 이유 표시·1회 고쳐 쓰기·초안 3묶음 추가(이 개정)
