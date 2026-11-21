# Proofy FE–BE API 계약 v0.3

- 작성일: 2026-11-21 · 상태: **BE 결정 반영, FE 확인 후 "합의됨"으로 바꾼다**
- 화면 기준: `docs/screen-flow.md`(6개 화면) · 데이터 기준: `docs/erd-review.md` · AI 흐름: `docs/agent-design.md`
- 서버 실행 중 실제 스키마는 `GET /docs`(FastAPI OpenAPI)에서 확인한다. **이 문서와 OpenAPI가 다르면 이 문서가 정본**이고, 서버를 고친다.

## 0. 합의 규칙과 일정

1. 계약을 바꾸려면 이 파일을 먼저 고치는 PR을 `dev`에 올리고 상대방이 확인한 뒤 구현한다. 맨 아래 변경 이력에 한 줄 적는다.
2. 필드 **추가**는 언제든 가능(FE는 모르는 필드를 무시한다). 필드 이름·타입 변경과 삭제는 합의 후에만.
3. 일정

| 시점 | BE | FE | 같이 |
|---|---|---|---|
| 11/21(토) 밤 | 이 문서 확정, `AGENT_LLM=scripted`로 전 엔드포인트 동작(가짜 분석 결과) | 문서 예시 JSON으로 화면 작성 | |
| 11/22(일) 오후 | 실제 OCR + Claude 연결, 샘플 서류 2세트, 개발 서버 배포 | 개발 서버에 연결 | |
| 11/22(일) 밤 | | | 시연 시나리오 2건(급여, 물품 거래) 리허설, 소개서 PDF·AI 활용내역 초안 |
| 11/23(월) 12:00 | **계약·기능 동결** | 동결 | |
| 11/23(월) 15:00 | | | 새 브라우저(로그아웃 상태)에서 "샘플로 체험하기"로 처음부터 끝까지 확인 |
| 11/23(월) 17:00 전 | | | 제출 링크에 소개서 PDF·AI 활용내역·프로토타입 링크 업로드 **+ 같은 자료를 운영사무국 이메일로 발송** |

## 1. 공통

| 항목 | 규칙 |
|---|---|
| Base URL | `{API_ORIGIN}/api/v1` (개발 서버 주소는 배포 후 공유) |
| 형식 | JSON, 필드는 camelCase. 업로드만 `multipart/form-data` |
| 날짜 | 날짜만: `"2026-11-21"` (한국 날짜). 시각: ISO 8601 UTC `"2026-11-21T06:30:00Z"` |
| 금액 | 원 단위 정수 `150000` (문자열·소수 금지) |
| 인증 | 로그인 없음. `POST /cases`(또는 `/cases/sample`) 응답의 `caseToken`을 이후 모든 `/cases/{caseId}/**` 요청에 `X-Case-Token` 헤더로 보낸다 |
| CORS | 서버가 FE 배포 주소와 `http://localhost:5173`을 허용하고, 허용 헤더에 `Content-Type`, `X-Case-Token`을 넣는다. 추가 주소는 BE에 알려 줄 것 |
| ID | 전부 UUID 문자열 |
| 빈 값 | 값이 없으면 키를 빼지 않고 `null` |
| 개인정보 | 서버가 보장한다: ① 업로드 원본 이미지·PDF는 외부 AI로 보내지 않는다 ② 서버에서 읽은 글자는 주민등록번호·계좌번호·전화번호·이름을 가린 뒤에만 AI에 보낸다 ③ 신분증과 신청인 인적사항은 받지 않는다 ④ 사건은 24시간 뒤 자동 삭제. 이 서비스는 **시연용이므로 합성 서류만** 올리게 안내한다(6절) |

### 1.1 오류 응답

모든 4xx/5xx는 같은 모양이다.

```json
{
  "error": {
    "code": "ANALYSIS_PRECONDITION",
    "message": "사연을 20자 이상 입력하고 거래내역서를 올려 주세요.",
    "details": { "narrativeLength": 8, "missing": ["NARRATIVE", "TRANSACTION_RECORD"] }
  }
}
```

`message`는 화면에 그대로 띄워도 되는 한국어 문장이다. 분기는 `code`로 한다.

| HTTP | code | 언제 | FE 처리 |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 필드 형식·필수값 오류, 미래 날짜. `details.fields`에 `{필드: 사유}` | 해당 입력칸에 표시 |
| 401 | `CASE_TOKEN_INVALID` | 토큰 없음·불일치 | localStorage 사건 삭제 후 홈으로 |
| 404 | `CASE_NOT_FOUND` | 사건 없음(삭제·24시간 만료 포함) | 같은 처리 |
| 404 | `NOT_FOUND` | 증빙·실행 등 하위 자원 없음 | 목록 새로고침 |
| 409 | `EVIDENCE_LIMIT` | 사건당 증빙 8개 초과 | 안내 |
| 409 | `ANALYSIS_IN_PROGRESS` | 이미 분석 중. `details.runId` 제공 | 그 `runId`로 4번 화면 이동 |
| 409 | `DRAFT_HAS_EDITS` | 재분석하면 사용자가 고친 초안이 덮임 | 확인창 후 `overwriteEditedDraft: true`로 재요청 |
| 409 | `VERSION_CONFLICT` | 초안 저장 시 `expectedVersion` 불일치. `details.currentVersion` | 최신 초안 다시 불러오기 |
| 413 | `FILE_TOO_LARGE` | 10MB 초과 | 안내 |
| 415 | `UNSUPPORTED_FILE_TYPE` | JPG·PNG·PDF 외(파일 내용으로 판별) | 안내 |
| 422 | `ANALYSIS_PRECONDITION` | 사연 20자 미만 또는 거래내역서 없음. `details.missing`에 `NARRATIVE`·`TRANSACTION_RECORD` | 3번 화면에 머물고 빠진 항목 강조 |
| 429 | `RATE_LIMITED` | 같은 IP에서 사건 생성 시간당 20회 초과, 또는 사건당 분석 시간당 5회 초과 | 안내 |
| 429 | `DAILY_LIMIT` | 서비스 전체 AI 분석 하루 300회 초과(비용 보호) | "오늘 시연 한도를 다 썼어요" 안내 |
| 500 | `INTERNAL` | 서버 오류 | 재시도 버튼 |

## 2. 코드값(enum)

| 이름 | 값 | 화면 표시 |
|---|---|---|
| `InflowType` | `SALARY` 급여 · `GOODS` 물품 거래 대금 · `UNEXPECTED` · `OTHER` | P0 화면은 앞의 둘만 선택지로 노출 |
| `DocType` | `NOTICE` 지급정지 통지서 · `TRANSACTION_RECORD` 거래내역서(입금내역) · `INSURANCE_ELIGIBILITY` 건강보험자격득실확인서 · `EMPLOYMENT_CERT` 재직증명서 · `PAYSLIP` 급여명세서 · `BUSINESS_REG` 사업자등록증명 · `CHAT` 대화내역 · `CONTRACT` 계약서 · `TAX_INVOICE` 세금계산서 · `TRANSACTION_STATEMENT` 거래명세서 · `SHIPPING` 배송 기록 · `OTHER` 기타 | **신분증 값은 없다.** 신분증은 받지 않는다 |
| `CaseStatus` | `DRAFT` 입력 중 · `ANALYZING` 분석 중 · `REVIEW_READY` 결과 있음 · `ERROR` 마지막 분석 실패 | 홈 카드 "현재 단계" |
| `ExtractStatus` | `UPLOADED` · `PROCESSING` · `READY` · `FAILED` | `FAILED`는 "직접 확인" |
| `RunStatus` | `RUNNING` · `SUCCEEDED` · `FAILED` | |
| `Stage` | `EXTRACTING` 글자 읽는 중 · `COMPARING` 거래내역과 대조 중 · `DRAFTING` 초안 작성 중 · `FINISHED` | 4번 화면 단계. **FE는 문구를 하드코딩하지 않고 `stages[].label`을 그대로 표시한다** |
| `FindingStatus` | `MATCH` 자료와 일치 · `CONFLICT` 자료와 어긋남 · `STATEMENT_ONLY` 진술만 있음 · `UNKNOWN` 확인 못 함 | 탭 A 배지. `MATCH`는 "일치하는 자료가 있다"는 뜻이지 사실 인정·판정이 아님 |
| `SourceKind` | `EVIDENCE` 올린 서류 · `TRANSACTION` 거래내역서의 거래 행 · `NARRATIVE` 사용자 사연 | |
| `ChecklistCategory` | `OFFICIAL_REQUIRED` 법령상 제출 서류 · `TYPE_GUIDE` 유형별 안내 서류(기사 근거) · `ANALYSIS_INPUT` AI 분석에 필요한 자료(공식 근거 없음) · `OPTIONAL` 있으면 좋은 자료 · `AI_RECOMMENDED` AI 권장 | 탭 B 묶음 제목. 다섯 묶음을 섞지 않고 따로 보여 줄 것 |
| `ChecklistStatus` | `SATISFIED` 올림 · `MISSING` 없음 · `NOT_COLLECTED` 받지 않음(직접 첨부) · `GUIDE_ONLY` 은행에서 작성 | |
| `NeedsCheckReason` | `CONFLICT` 자료와 어긋난 내용 · `NO_SOURCE` 근거 없음 · `QUOTE_NOT_FOUND` 인용을 원문에서 못 찾음 · `NUMBER_MISMATCH` 숫자가 근거와 다름 · `JUDGMENT_EXPRESSION` 판정처럼 읽히는 표현 · `SOURCE_UNREAD` 근거 서류를 못 읽음 | 탭 C "확인 필요" 툴팁. 여러 사유가 겹치면 이 순서대로 앞의 것 하나만 준다 |
| `DeadlineState` | `UNKNOWN_NOTICE_DATE` 공고일 확인 필요 · `OK` · `URGENT` 7일 이하 · `EXPIRED` 지남 | D-day 배지 색 |
| `SampleScenario` | `SALARY` 급여 · `GOODS` 물품 거래(청년 1인 온라인 판매 사업자) | 샘플 체험 |

## 3. 화면별 호출

| 화면 | 호출 |
|---|---|
| 1 홈 | localStorage에 사건 있으면 `GET /cases/{id}` → 진행 중 카드. **"샘플로 체험하기"**: `POST /cases/sample` → 3번 화면(서류가 채워진 상태)으로 |
| 2 내 상황 | "다음": `POST /cases`(처음) 또는 `PATCH /cases/{id}`(수정). 응답의 `deadline`으로 D-day 표시 |
| 3 사연·증빙 | `GET /meta/requirements?inflowType=` 또는 `GET /cases/{id}/checklist` · `PATCH /cases/{id}`(사연, 입력 멈춘 뒤 1초 자동 저장) · `POST/DELETE /cases/{id}/evidence` · `GET /samples`(샘플 서류 내려받기 링크) · "분석 시작": `POST /cases/{id}/analysis-runs`에 **현재 사연을 `narrative`로 함께 보낸다**. 사연 20자 미만이거나 `requiredForAnalysis` 항목이 `SATISFIED`가 아니면 버튼을 비활성화하고 이유를 보여 준다(서버도 422로 막는다) |
| 4 분석 중 | `GET /cases/{id}/analysis-runs/{runId}` 1.5초 간격 폴링 |
| 5 결과 | `GET /cases/{id}/result` · `PATCH /cases/{id}/checklist/{itemId}` · `PUT /cases/{id}/draft` |
| 6 제출 가이드 | 서버 호출 없음(정적 문구). 최종 점검 수치는 5번에서 받은 `result.summary`와 `draft.unconfirmedCount` 사용 · "처음부터": `DELETE /cases/{id}` 후 localStorage 삭제 |

## 4. 엔드포인트

### 4.1 `GET /health`

```json
{ "status": "ok", "agent": "claude", "demoMode": true }
```

- `agent`: `claude` 또는 `scripted`(7절). 시연 전에 확인용.
- `demoMode: true`면 FE는 3번 화면 업로드 영역 위에 "시연용 서비스입니다. 실제 서류 대신 샘플(합성) 서류만 올려 주세요"를 항상 보여 준다. P0는 항상 `true`.

### 4.2 `GET /meta/requirements?inflowType=SALARY`

인증 없음. 화면 3의 유형별 체크리스트 원본. 사건 없이도 부른다.

```json
{
  "inflowType": "SALARY",
  "items": [
    {
      "code": "OBJECTION_FORM",
      "label": "이의제기신청서(별지 제4호서식)",
      "category": "OFFICIAL_REQUIRED",
      "acceptedDocTypes": [],
      "uploadable": false,
      "requiredForAnalysis": false,
      "note": "은행 창구·양식으로 작성합니다. 소명서 초안의 사유를 옮겨 적을 수 있습니다.",
      "sourceRef": { "label": "통신사기피해환급법 시행령 제7조", "url": "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=290281" }
    },
    {
      "code": "ID_COPY",
      "label": "신분증 사본",
      "category": "OFFICIAL_REQUIRED",
      "acceptedDocTypes": [],
      "uploadable": false,
      "requiredForAnalysis": false,
      "note": "이 서비스는 신분증을 받지 않습니다. 은행에 낼 때 직접 첨부하세요.",
      "sourceRef": { "label": "통신사기피해환급법 시행령 제7조", "url": "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=290281" }
    },
    {
      "code": "SALARY_DEPOSIT",
      "label": "급여 입금내역",
      "category": "TYPE_GUIDE",
      "acceptedDocTypes": ["TRANSACTION_RECORD"],
      "uploadable": true,
      "requiredForAnalysis": true,
      "note": "문제된 입금이 보이는 거래내역서(은행 앱 캡처 또는 PDF)",
      "sourceRef": { "label": "한국일보 2026.5.3", "url": "https://www.hankookilbo.com/news/article/A2026050313580002729" }
    },
    {
      "code": "EMPLOYMENT_PROOF",
      "label": "건강보험자격득실확인서 또는 재직증명서 중 하나",
      "category": "TYPE_GUIDE",
      "acceptedDocTypes": ["INSURANCE_ELIGIBILITY", "EMPLOYMENT_CERT"],
      "uploadable": true,
      "requiredForAnalysis": false,
      "note": null,
      "sourceRef": { "label": "한국일보 2026.5.3", "url": "https://www.hankookilbo.com/news/article/A2026050313580002729" }
    },
    {
      "code": "NOTICE",
      "label": "지급정지 통지서",
      "category": "OPTIONAL",
      "acceptedDocTypes": ["NOTICE"],
      "uploadable": true,
      "requiredForAnalysis": false,
      "note": "통지일·공고일을 확인하는 데 씁니다.",
      "sourceRef": null
    }
  ]
}
```

`GOODS`의 유형별 항목은 다음과 같다(공통 항목 `OBJECTION_FORM`, `ID_COPY`, `NOTICE`는 같음). 기사 근거가 사업자 기준이므로 물품 거래 유형은 **사업자(개인사업자 포함)의 판매 대금**을 전제로 안내한다.

| code | label | category | acceptedDocTypes | requiredForAnalysis |
|---|---|---|---|---|
| `BUSINESS_REG` | 사업자등록 | `TYPE_GUIDE` | `BUSINESS_REG` | `false` |
| `COUNTERPARTY_CHAT` | 거래상대방과의 대화내역 | `TYPE_GUIDE` | `CHAT` | `false` |
| `TRADE_DOCUMENT` | 계약서, 세금계산서, 거래명세서 중 하나 | `TYPE_GUIDE` | `CONTRACT`, `TAX_INVOICE`, `TRANSACTION_STATEMENT` | `false` |
| `DEPOSIT_RECORD` | 문제된 입금이 보이는 거래내역서 | `ANALYSIS_INPUT` | `TRANSACTION_RECORD` | **`true`** |

- `acceptedDocTypes`가 여러 개면 **그중 하나만 있어도 충족**이다. 업로드 화면에서 항목을 누르면 `acceptedDocTypes`의 첫 값을 기본 `docType`으로 쓰고, 여러 개면 고르게 한다.
- `requiredForAnalysis: true`는 **AI 분석에 필요한 서류**라는 뜻이고, 법령·기사상 제출 의무와는 별개다. 항목 옆에 "AI 분석에 필요" 배지를 붙인다. 두 유형 모두 거래내역서 한 항목만 `true`다.
  - 급여: `SALARY_DEPOSIT`. 기사가 든 서류와 같아서 `TYPE_GUIDE` 묶음에 있다.
  - 물품 거래: `DEPOSIT_RECORD`. 기사 근거가 없어서 `ANALYSIS_INPUT` 묶음에 있다.

### 4.3 `POST /cases` — 사건 만들기 (화면 2 "다음")

요청

```json
{
  "noticeReceivedDate": "2026-11-10",
  "publicNoticeDate": "2026-11-17",
  "inflow": { "type": "GOODS", "amountKrw": 150000, "occurredAt": null },
  "hasPriorFreeze": false
}
```

| 필드 | 필수 | 규칙 |
|---|---|---|
| `noticeReceivedDate` | 예 | 오늘(한국 날짜) 이하. 미래면 400 |
| `publicNoticeDate` | 아니오 | "모르면 건너뜀"이면 `null`. 미래면 400. 통지일보다 앞서도 받는다(우편 지연 등으로 순서가 바뀔 수 있음) |
| `inflow.type` | 예 | `InflowType` |
| `inflow.amountKrw` | 예 | 1 이상 10,000,000,000 이하 정수 |
| `inflow.occurredAt` | 아니오 | 날짜(`"2026-11-08"`) 또는 `null`. 미래면 400 |
| `hasPriorFreeze` | 예(값으로 `null` 허용) | 예 `true` / 아니오 `false` / 모름 `null` |

같은 IP에서 시간당 20회까지(`429 RATE_LIMITED`).

응답 `201` — `caseToken`은 **이 응답에서 한 번만** 준다. FE는 바로 localStorage에 저장한다.

```json
{
  "caseId": "6f1d2c1e-6d0b-4b8e-9a6b-1f7c2a3e9d10",
  "caseToken": "pk_3q2-7w…(43자, URL-safe)",
  "case": { "...": "4.4 응답의 case와 같은 모양" }
}
```

### 4.3.1 `POST /cases/sample` — 샘플로 체험하기

심사자·처음 온 사용자가 서류 없이 전체 흐름을 체험하게 한다. 합성 서류가 이미 들어간 사건을 만든다.

```json
{ "scenario": "GOODS" }
```

응답 `201`: `POST /cases`와 같은 모양. `case.isSample: true`, 사연·입금 정보·날짜(공고일 = 오늘 − 4일 등 오늘 기준 상대 날짜)·증빙이 채워져 있다. FE는 3번 화면으로 보내고, 사용자는 바로 "분석 시작"을 누를 수 있다. 생성 제한은 4.3과 같다.

| 시나리오 | 들어 있는 합성 서류 | 대조에서 보이는 것 |
|---|---|---|
| `SALARY` | 급여 입금이 보이는 거래내역서(텍스트 PDF), 재직증명서(PNG) | 입금 금액·날짜 일치, 근무 사실 근거 |
| `GOODS` | 거래내역서(텍스트 PDF), 거래처와의 대화내역(PNG), 사업자등록증명(PNG) | 입금 일치, 대화 속 합의 금액과 입금액 **불일치**(탭 A 경고와 탭 C "확인 필요" 시연), 거래명세서 없음(탭 B) |

#### `GET /samples` — 샘플 서류 내려받기

인증 없음. 직접 업로드 흐름을 체험하려는 사람용.

```json
{
  "items": [
    {
      "scenario": "GOODS",
      "files": [
        { "name": "거래내역서_샘플.pdf", "docType": "TRANSACTION_RECORD", "url": "/api/v1/samples/goods/transaction_record.pdf" },
        { "name": "대화내역_샘플.png", "docType": "CHAT", "url": "/api/v1/samples/goods/chat.png" }
      ]
    }
  ]
}
```

### 4.4 `GET /cases/{caseId}` — 사건 조회 (홈 카드, 새로고침 복구)

```json
{
  "case": {
    "caseId": "6f1d2c1e-…",
    "status": "DRAFT",
    "isSample": false,
    "noticeReceivedDate": "2026-11-10",
    "publicNoticeDate": "2026-11-17",
    "inflow": { "type": "GOODS", "amountKrw": 150000, "occurredAt": null },
    "hasPriorFreeze": false,
    "narrative": null,
    "inputVersion": 1,
    "deadline": {
      "state": "OK",
      "deadlineDate": "2027-01-17",
      "daysLeft": 57,
      "label": "D-57",
      "basis": "공고일(2026-11-17) 기준 2개월, 참고 계산",
      "notice": "정확한 기한은 계좌가 있는 은행에 꼭 확인하세요."
    },
    "evidenceCount": 0,
    "latestRun": null,
    "hasResult": false,
    "createdAt": "2026-11-21T06:30:00Z",
    "expiresAt": "2026-11-22T06:30:00Z"
  }
}
```

- `latestRun`: `null` 또는 `{ "runId", "status", "stage" }`. 홈 카드에서 `RUNNING`이면 4번 화면으로, `hasResult`면 5번으로 보낸다.
- `deadline`은 매 응답마다 서버가 오늘 날짜(한국 시간)로 다시 계산한다. **FE는 D-day를 직접 계산하지 않는다.**

### 4.5 `PATCH /cases/{caseId}` — 사건 수정 (화면 2 다시 저장, 화면 3 사연 자동 저장)

보낸 필드만 바꾼다. `inflow`는 객체 통째로 교체. 검증 규칙은 4.3과 같다.

```json
{ "narrative": "온라인 쇼핑몰을 운영하는 개인사업자입니다. 거래처 소매점에 가죽 지갑 3개를 15만 원에 납품하기로 하고 11월 8일 대금을 계좌로 받았습니다. 물건은 다음 날 택배로 보냈습니다." }
```

응답 `200 { "case": { … } }`. 내용이 바뀌면 `inputVersion`이 1 오른다. `narrative`는 최대 2000자.

### 4.6 `DELETE /cases/{caseId}`

`204`. 파일·글자 인식 결과·분석 결과를 모두 지운다. 지우지 않아도 생성 24시간 뒤 자동 삭제된다.

### 4.7 증빙

#### `POST /cases/{caseId}/evidence` (multipart)

| 파트 | 필수 | 규칙 |
|---|---|---|
| `file` | 예 | JPG·PNG·PDF, 10MB 이하. 형식은 파일 내용으로 판별 |
| `docType` | 예 | `DocType` |

`<input accept="image/jpeg,image/png,application/pdf">`를 권장한다. 사건당 8개까지.

응답 `201`

```json
{
  "evidence": {
    "evidenceId": "b0c…",
    "docType": "CHAT",
    "originalName": "chat_capture.png",
    "mimeType": "image/png",
    "sizeBytes": 482113,
    "extractStatus": "UPLOADED",
    "lowConfidenceRegions": null,
    "isSample": false,
    "createdAt": "2026-11-21T06:41:12Z"
  }
}
```

업로드만으로는 글자를 읽지 않는다. 글자 인식은 분석을 시작할 때 한다(글자가 들어 있는 PDF는 OCR 없이 바로 추출). 올리면 `inputVersion`이 오른다.

#### `GET /cases/{caseId}/evidence` → `200 { "items": [Evidence…] }`

#### `DELETE /cases/{caseId}/evidence/{evidenceId}` → `204`

미리보기 이미지는 FE가 업로드 전 파일로 만든다(`URL.createObjectURL`). 서버는 원본 파일을 내려주지 않는다(P0). 샘플 사건의 서류는 `GET /samples`의 `url`로 미리보기를 띄운다.

### 4.8 `GET /cases/{caseId}/checklist` — 현재 체크리스트

화면 3에서 올린 서류에 따라 항목이 채워지는 것을 보여 줄 때, 탭 B에서 쓴다. 분석 전에는 4.2의 항목에 상태만 붙고, 분석 후에는 `AI_RECOMMENDED` 항목이 더해진다.

```json
{
  "items": [
    {
      "itemId": "c01…",
      "code": "TRADE_DOCUMENT",
      "label": "계약서, 세금계산서, 거래명세서 중 하나",
      "category": "TYPE_GUIDE",
      "status": "MISSING",
      "acceptedDocTypes": ["CONTRACT", "TAX_INVOICE", "TRANSACTION_STATEMENT"],
      "requiredForAnalysis": false,
      "satisfiedBy": [],
      "checked": false,
      "note": "거래명세서가 있으면 대화 속 금액과 입금액이 다른 이유를 설명하는 데 도움이 됩니다.",
      "sourceRef": { "label": "한국일보 2026.5.3", "url": "https://www.hankookilbo.com/news/article/A2026050313580002729" }
    },
    {
      "itemId": "c09…",
      "code": null,
      "label": "택배 발송 기록(송장 번호 화면)",
      "category": "AI_RECOMMENDED",
      "status": "MISSING",
      "acceptedDocTypes": ["SHIPPING"],
      "requiredForAnalysis": false,
      "satisfiedBy": [],
      "checked": false,
      "note": "사연에 '다음 날 택배로 보냈다'고 했지만 이를 보여 주는 자료가 없습니다.",
      "sourceRef": null
    }
  ],
  "missingCount": 2
}
```

- `status`는 서버가 올린 서류로 계산한다. `checked`는 사용자가 "따로 준비함"을 누른 표시이고 `status`와 별개다.
- `missingCount` = `status == MISSING` 이면서 `checked == false`인 항목 수.

#### `PATCH /cases/{caseId}/checklist/{itemId}` `{ "checked": true }` → `200 { "item": {…} }`

### 4.9 분석 시작 — `POST /cases/{caseId}/analysis-runs`

```json
{ "narrative": "온라인 쇼핑몰을 운영하는 개인사업자입니다. …", "overwriteEditedDraft": false }
```

- `narrative`(선택): 있으면 서버가 **먼저 저장한 뒤** 사전 조건을 검사하고 분석을 시작한다. 자동 저장(1초 지연)이 끝나기 전에 버튼을 눌러도 최신 사연으로 분석되게 FE는 항상 보낸다.
- 사전 조건: 사연 20자 이상 + `requiredForAnalysis` 항목(거래내역서, `docType=TRANSACTION_RECORD`) 1개 이상 → 아니면 `422 ANALYSIS_PRECONDITION`, `details.missing`에 빠진 것(`NARRATIVE`, `TRANSACTION_RECORD`)
- 이미 실행 중 → `409 ANALYSIS_IN_PROGRESS` (`details.runId`)
- 사용자가 고친 초안이 있고 `overwriteEditedDraft=false` → `409 DRAFT_HAS_EDITS`
- 사건당 시간당 5회 → `429 RATE_LIMITED`, 서비스 전체 하루 300회 → `429 DAILY_LIMIT`

응답 `202`

```json
{ "runId": "a7e…", "status": "RUNNING", "stage": "EXTRACTING" }
```

### 4.10 분석 진행 — `GET /cases/{caseId}/analysis-runs/{runId}`

FE는 1.5초마다 부르고 `status`가 `RUNNING`이 아니면 멈춘다. 180초가 지나도 끝나지 않으면 "다시 시도" 버튼을 보여 준다(서버는 150초에 스스로 실패 처리한다).

```json
{
  "runId": "a7e…",
  "status": "RUNNING",
  "stage": "COMPARING",
  "stages": [
    { "key": "EXTRACTING", "label": "글자 읽는 중", "status": "DONE" },
    { "key": "COMPARING", "label": "거래내역과 대조 중", "status": "RUNNING" },
    { "key": "DRAFTING", "label": "초안 작성 중", "status": "PENDING" }
  ],
  "steps": [
    { "seq": 1, "type": "OCR", "title": "서류 글자 읽기", "summary": "대화내역 1쪽, 글자 줄 34개", "status": "DONE", "at": "2026-11-21T06:45:02Z" },
    { "seq": 2, "type": "OCR", "title": "서류 글자 읽기 실패", "summary": "사업자등록증명.jpg: 글자를 읽지 못했습니다. 결과에서 직접 확인 항목으로 보여 드립니다.", "status": "FAILED", "at": "2026-11-21T06:45:06Z" },
    { "seq": 3, "type": "TOOL_CALL", "title": "거래내역 조회", "summary": "11/1~11/10 입금 2건 확인", "status": "DONE", "at": "2026-11-21T06:45:19Z" }
  ],
  "error": null,
  "startedAt": "2026-11-21T06:45:00Z",
  "finishedAt": null
}
```

- `stages[].status`: `PENDING` · `RUNNING` · `DONE` · `FAILED`
- `steps`는 AI가 실제로 한 일을 보여 주는 기록이다. 화면에 다 보여 줄 필요는 없지만, 마지막 몇 줄을 흐리게 보여 주면 "AI가 무엇을 하는지" 시연에 좋다. `type`: `OCR` · `TOOL_CALL` · `FINDING` · `CONFLICT` · `DRAFT` · `VERIFY` · `FAILED`
- 서류 하나를 못 읽어도 분석은 계속된다(그 단계만 `FAILED`).
- 실패 시 `status: "FAILED"`, `error: { "code": "AGENT_FAILED" | "AGENT_TIMEOUT" | "AGENT_REFUSED", "message": "…" }`. FE는 메시지와 "다시 시도"(4.9 재호출)를 보여 준다.

### 4.11 결과 — `GET /cases/{caseId}/result`

가장 최근 **성공한** 분석 결과. 없으면 `404 NOT_FOUND`.

```json
{
  "runId": "a7e…",
  "basedOnInputVersion": 4,
  "isStale": false,
  "generatedAt": "2026-11-21T06:45:41Z",
  "aiNotice": "AI가 올린 자료를 정리한 결과입니다. 해제 여부를 판단하지 않으며, 은행 심사 결과와 다를 수 있습니다.",
  "deadline": { "...": "4.4와 같음" },
  "findings": [
    {
      "findingId": "f1…",
      "claim": "11월 8일 거래처에서 15만 원을 입금받았다",
      "status": "MATCH",
      "note": "거래내역서의 입금 행과 금액·날짜가 같습니다.",
      "conflict": null,
      "sources": [
        { "kind": "NARRATIVE", "quote": "11월 8일 대금을 계좌로 받았습니다", "verified": true },
        {
          "kind": "TRANSACTION",
          "transactionId": "t3…",
          "evidenceId": "e2…",
          "occurredAt": "2026-11-08",
          "direction": "IN",
          "amountKrw": 150000,
          "counterparty": "김*수",
          "verified": true
        }
      ]
    },
    {
      "findingId": "f2…",
      "claim": "가죽 지갑 3개를 15만 원에 납품하기로 했다",
      "status": "CONFLICT",
      "note": "대화내역의 합의 금액이 사연·입금액과 다릅니다.",
      "conflict": { "field": "AMOUNT", "statement": "150,000원", "found": "120,000원" },
      "sources": [
        {
          "kind": "EVIDENCE",
          "evidenceId": "e1…",
          "docType": "CHAT",
          "originalName": "chat_capture.png",
          "page": 1,
          "regionIndex": 12,
          "quote": "3개 12만원에 할게요",
          "verified": true
        }
      ]
    },
    {
      "findingId": "f3…",
      "claim": "물건을 다음 날 택배로 보냈다",
      "status": "STATEMENT_ONLY",
      "note": "사연에만 있고 이를 보여 주는 자료가 없습니다.",
      "conflict": null,
      "sources": [{ "kind": "NARRATIVE", "quote": "물건은 다음 날 택배로 보냈습니다", "verified": true }]
    }
  ],
  "checklist": { "...": "4.8 응답과 같은 모양" },
  "draft": { "...": "4.12 응답의 draft와 같은 모양" },
  "unreadEvidence": [
    { "evidenceId": "e3…", "originalName": "사업자등록증명.jpg", "reason": "글자를 읽지 못했습니다. 원본을 직접 확인해 주세요." }
  ],
  "summary": {
    "findingCounts": { "MATCH": 1, "CONFLICT": 1, "STATEMENT_ONLY": 1, "UNKNOWN": 0 },
    "missingDocuments": 2,
    "sentencesNeedingCheck": 2,
    "unreadEvidence": 1
  }
}
```

- `isStale: true` = 분석 뒤에 사연·서류가 바뀌었다. 결과 상단에 "자료가 바뀌었어요. 다시 분석하기" 배너.
- `conflict.field`: `AMOUNT` · `DATE` · `COUNTERPARTY` · `OTHER`. 탭 A의 경고 문구에 `statement`(사용자 진술)와 `found`(자료)를 나란히 보여 준다.
- `verified: false`인 근거는 "원문에서 찾지 못한 인용"으로 흐리게 표시한다.
- `counterparty` 등 사람 이름·계좌번호는 서버가 가린 값으로 준다.

### 4.12 소명서 초안

#### `GET /cases/{caseId}/draft`

```json
{
  "draft": {
    "version": 1,
    "basedOnRunId": "a7e…",
    "sentences": [
      {
        "sentenceId": "s1",
        "text": "본인은 온라인 쇼핑몰을 운영하는 개인사업자로, 2026년 11월 8일 거래처에 가죽 지갑 3개를 납품하고 그 대금 150,000원을 입금받았습니다.",
        "origin": "AI",
        "findingIds": ["f1…", "f2…"],
        "needsCheck": true,
        "needsCheckReason": "CONFLICT",
        "confirmed": false,
        "edited": false
      },
      {
        "sentenceId": "s2",
        "text": "판매한 물건은 다음 날 택배로 발송하였습니다.",
        "origin": "AI",
        "findingIds": ["f3…"],
        "needsCheck": true,
        "needsCheckReason": "NO_SOURCE",
        "confirmed": false,
        "edited": false
      }
    ],
    "warnings": [],
    "unconfirmedCount": 2,
    "fullText": "본인은 온라인 쇼핑몰을 … 발송하였습니다.",
    "updatedAt": "2026-11-21T06:45:41Z"
  }
}
```

**확인 필요 규칙(서버)**
1. `CONFLICT` 항목에 연결된 문장은 무조건 `needsCheck: true`, 사유 `CONFLICT`.
2. 문장 속 금액·날짜가 어떤 `CONFLICT` 항목의 `conflict.statement` 값과 같으면, AI가 연결하지 않았더라도 서버가 그 항목을 `findingIds`에 붙이고 1번을 적용한다. (예: s1의 "150,000원"은 f2의 진술 값이라 f2가 붙는다.)
3. 어느 문장에도 연결되지 않은 `CONFLICT` 항목이 있으면 `warnings`에 `{ "code": "CONFLICT_NOT_IN_DRAFT", "findingId": "f…", "message": "자료와 어긋난 내용이 초안에 설명되지 않았습니다." }`를 넣는다. FE는 초안 위에 경고로 보여 준다.

**화면 규칙(FE)**
- `needsCheck: true` 문장은 노란 밑줄 + "확인 필요" + 사유(`NeedsCheckReason`). 문장을 누르면 `findingIds`의 탭 A 항목으로 이동.
- 각 확인 필요 문장 옆에 "직접 확인했어요" 체크를 둔다 → `confirmed: true`로 저장. 체크해도 배지는 "직접 확인함"으로 남는다(근거가 생긴 것은 아니다).
- **복사·PDF 저장 전에** `unconfirmedCount > 0`이면 "아직 확인하지 않은 문장이 N개 있어요. 사실과 다른 내용을 내면 처벌받을 수 있습니다(법 제16조)." 확인창을 띄우고 [문장으로 이동] / [그래도 복사] 중 고르게 한다.
- `fullText`는 복사용(모든 문장을 공백으로 이은 것).

#### `PUT /cases/{caseId}/draft` — 수정 저장

```json
{
  "expectedVersion": 1,
  "sentences": [
    { "sentenceId": "s1", "text": "본인은 … 대금 150,000원을 입금받았습니다. 최초 대화에서는 12만 원으로 이야기했으나 이후 수량 추가로 15만 원이 되었습니다.", "confirmed": true },
    { "sentenceId": "s2", "text": "판매한 물건은 11월 9일 택배로 발송하였습니다.", "confirmed": false },
    { "sentenceId": null, "text": "송장 번호 화면을 함께 제출합니다." }
  ]
}
```

- 배열 전체를 보낸다. 순서 = 화면 순서. 빠진 `sentenceId`는 삭제로 본다.
- 기존 문장의 글을 바꾸면 서버가 `edited: true`로 바꾸고 `findingIds`·`needsCheck`는 유지한다(고쳤다고 근거가 생기지는 않는다).
- `confirmed`: 생략하면 기존 값 유지. 단 **글이 바뀐 문장은 보낸 값과 관계없이 `false`로 되돌린다** — 같은 요청에서 `true`를 보내면 그대로 `true`.
- `sentenceId: null`은 새 문장 → `origin: "USER"`, `needsCheck: false`.
- 응답 `200 { "draft": {…, "version": 2} }`. 버전이 다르면 `409 VERSION_CONFLICT`.
- 저장 시점: 문장 편집칸에서 포커스가 빠질 때, "직접 확인했어요"를 누를 때.

## 5. 기한(D-day) 계산 규칙 — 서버 구현, FE는 표시만

1. `publicNoticeDate`가 없으면 `state = UNKNOWN_NOTICE_DATE`, `deadlineDate = null`, `label = "공고일 확인 필요"`.
2. 기간은 공고일 다음 날부터 센다(민법 제157조 초일 불산입). 시작일 `S = 공고일 + 1일`.
3. `S`에서 2개월 뒤 같은 날짜가 있으면 그 전날이 마지막 날, 그 달에 같은 날짜가 없으면 그 달 말일이 마지막 날(민법 제160조).
   - 예: 공고일 11/17 → 1/17 · 공고일 11/30 → 1/31 · 공고일 12/30 → 2/28(평년)
4. 공휴일 순연(민법 제161조)은 P0에서 하지 않는다. 그래서 `notice`에 항상 "은행 확인" 문구를 붙인다.
5. `daysLeft = deadlineDate − 오늘(한국 날짜)`. `label`: 양수 `D-n`, 0이면 `D-DAY`, 음수면 `기한 지남`.
6. `state`: `daysLeft > 7` → `OK`, `0 ≤ daysLeft ≤ 7` → `URGENT`, 음수 → `EXPIRED`.

## 6. FE만 가지는 것

| 항목 | 규칙 |
|---|---|
| localStorage | 키 `proofy.case` = `{ "caseId", "caseToken", "createdAt" }` 한 건만. 401·404를 받으면 지운다 |
| 화면 2 입력 중 상태 | 서버에 보내기 전까지 FE 상태로만 둔다 |
| 별지 제4호서식 인적사항(이름, 생년월일, 주소, 연락처, 계좌번호) | **서버로 보내지 않는다.** 6번 화면 "PDF로 저장"에서 FE가 입력받아 인쇄용 화면에만 채우고 `window.print()` |
| 합성 데이터 안내 | 홈: "시연용 서비스이며 예시는 합성 데이터입니다". 3번 업로드 영역: `demoMode`이면 "실제 서류 대신 샘플(합성) 서류만 올려 주세요" + [샘플 서류 받기] |
| 복사·PDF 저장 확인창 | 4.12 화면 규칙 |
| 정적 문구 | 홈 소개, 절차 타임라인, 제출 가이드(낼 서류 3종, 심사 5영업일, 보완 요구 시 기한 안 재제출), 거짓 이의제기 처벌 경고 |
| AI 표시 | 결과 화면 상단에 `result.aiNotice`를 항상 보여 준다(해커톤 AI 활용 기준 제7조 권장) |

## 7. 가짜 분석 모드

서버를 `AGENT_LLM=scripted`로 띄우면 Claude를 부르지 않고 정해진 규칙으로 결과를 만든다. 단계마다 1~2초씩 쉬어서 4번 화면 진행 표시가 보인다. 응답 모양은 실제와 같다(샘플 시나리오 2건은 4.11 예시와 같은 결과를 낸다). FE 개발·리허설은 이 모드로 하고, `GET /health`의 `agent` 값으로 어느 모드인지 확인한다.

## 8. 아직 안 정한 것

| 항목 | 기본값(합의 전까지) |
|---|---|
| 개발 서버 주소, FE 배포 주소 | BE가 배포 후 공유. FE 주소는 CORS 등록을 위해 BE에 알려 줌 |
| 재분석 시 탭 B의 사용자 체크(`checked`) 유지 | 같은 `code`인 공식·유형 항목은 유지, AI 권장 항목은 새로 만듦 |
| 홈 "진행 중인 건" 카드 | 시간 부족 시 제외(화면 문서 범위 결정과 같음). API는 이미 있음. **"샘플로 체험하기" 버튼은 제외하지 않는다** |

## 변경 이력

| 날짜 | 버전 | 내용 |
|---|---|---|
| 2026-11-21 | 0.1 | 최초 작성 |
| 2026-11-21 | 0.2 | ① 사건은 화면 2 "다음"에서 생성 확정(사연은 화면 3에서 `PATCH`) ② `COMPARING` 문구를 "거래내역과 대조 중"으로, FE는 `stages[].label`만 표시 ③ 요구 서류에 `requiredForAnalysis` 추가, 거래내역서를 분석 시작 조건으로(`422`의 `details.missing`) |
| 2026-11-21 | 0.3 | 외부 검토 반영. ① 초안: `CONFLICT` 연결 문장 자동 확인 필요, 진술 값 일치 시 서버가 연결, `warnings`, 문장별 `confirmed`·`unconfirmedCount`, 복사·PDF 전 확인창 ② 개인정보 보장 항목·`demoMode`·합성 데이터 안내 ③ `POST /cases/sample`, `GET /samples` 샘플 체험 ④ 일정에 리허설·소개서·제출(업로드+이메일) ⑤ `ANALYSIS_INPUT` 분류 신설, 물품 거래는 사업자 판매 대금 전제·예시를 청년 1인 판매 사업자로 ⑥ IP당 사건 생성 제한, `DAILY_LIMIT` ⑦ 미래 날짜 400 ⑧ 분석 시작에 `narrative` 동봉 ⑨ CORS 허용 헤더 |
