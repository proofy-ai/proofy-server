# Proofy FE–BE API 계약 v0.8.3(제안)

- 작성일: 2026-11-21(v0.6.5 2026-11-22, v0.7·v0.7.1은 되돌림, v0.8 제안 2026-11-22) · 상태: **v0.8은 제안이다(FE 확인 전). FE 확인 후 "합의됨"으로 바꾼다**
- v0.8 요약: 결과에 AI 의견·질문 카드(`agentReview`, 4.11), 분석 시작에 질문 답변(`answers`, 4.9), 상담 안내 판단 방식 변경(응답 모양 그대로). 설명용 문서: `docs/proposals/v0.8-agent-interview.md`
- 화면 기준: `docs/screen-flow.md`(흐름 화면 6개 + 체험 계정 선택·내 사건) · 데이터 기준: `docs/erd.md` · AI 흐름: `docs/agent-design.md`
- 서버 실행 중 실제 스키마는 `GET /docs`(FastAPI OpenAPI)에서 확인한다. **이 문서와 OpenAPI가 다르면 이 문서가 정본**이고, 서버를 고친다.

> 📖 **이 문서 읽는 법**
> - **처음이면:** 3절(화면별 호출)에서 화면마다 부르는 API를 보고, 4절에서 그 엔드포인트를 찾는다
> - **필드 이름·타입:** 4절 각 엔드포인트의 표와 예시 JSON
> - **코드값(enum):** 2절 · **오류 코드:** 1.1절 · **D-day 규칙:** 5절
> - **FE만 가지는 것**(화면 설정, 별지 제4호 인쇄): 6절 · **가짜 분석 모드:** 7절
> - **무엇이 바뀌었나:** 맨 아래 변경 이력
> - 필드 표는 찾아보는 용도라 표로 둔다

## 0. 합의 규칙과 일정

1. 계약을 바꾸려면 이 파일을 먼저 고치는 PR을 `dev`에 올리고 상대방이 확인한 뒤 구현한다. 맨 아래 변경 이력에 한 줄 적는다.
2. 필드 **추가**는 언제든 가능(FE는 모르는 필드를 무시한다). 필드 이름·타입 변경과 삭제는 합의 후에만.
3. 일정

| 시점 | BE | FE | 같이 |
|---|---|---|---|
| 11/21(토) 밤 | 이 문서 확정, `AGENT_LLM=scripted`로 전 엔드포인트 동작(가짜 분석 결과) | 문서 예시 JSON으로 화면 작성 | |
| 11/22(일) 오후 | 실제 OCR + Claude 연결, 샘플 서류 2세트(`GOODS`, `UNEXPECTED`), 개발 서버 배포 | 개발 서버에 연결 | |
| 11/22(일) 밤 | | | 시연 시나리오 2건(test01 물품 거래, test02 통장 묶기) 리허설, 소개서 PDF·AI 활용내역 초안 |
| 11/23(월) 12:00 | **계약·기능 동결** | 동결 | |
| 11/23(월) 15:00 | | | 새 브라우저(로그아웃 상태)에서 체험 계정 test01·test02로 처음부터 끝까지 확인 |
| 11/23(월) 17:00 전 | | | 제출 링크에 소개서 PDF·AI 활용내역·프로토타입 링크 업로드 **+ 같은 자료를 운영사무국 이메일로 발송** |

## 1. 공통

| 항목 | 규칙 |
|---|---|
| Base URL | `{API_ORIGIN}/api/v1` (개발 서버 주소는 배포 후 공유). 로컬 BE는 `http://localhost:8080`(FE `VITE_API_ORIGIN` 기본값) |
| 형식 | JSON, 필드는 camelCase. 업로드만 `multipart/form-data` |
| 날짜 | 날짜만: `"2026-11-21"` (한국 날짜). 시각: ISO 8601 UTC `"2026-11-21T06:30:00Z"` |
| 금액 | 원 단위 정수 `150000` (문자열·소수 금지) |
| 인증 | 서버 로그인 없음. 화면의 "로그인"은 체험 계정 버튼일 뿐이고 서버는 계정을 모른다(6절). `POST /cases`(또는 `/cases/sample`) 응답의 `caseToken`을 이후 모든 `/cases/{caseId}/**` 요청에 `X-Case-Token` 헤더로 보낸다 |
| CORS | 서버가 FE 고정 배포 주소(Cloudflare)와 `http://localhost:5173`을 허용하고, 허용 헤더에 `Content-Type`, `X-Case-Token`을 넣는다. 배포마다 바뀌는 미리보기 주소는 등록하지 않는다. 주소는 서버 환경변수 `CORS_ORIGINS`로 넣으며, 추가 주소는 BE에 알려 줄 것 |
| ID | 전부 UUID 문자열 |
| 빈 값 | 값이 없으면 키를 빼지 않고 `null` |
| 개인정보 | 서버가 보장한다: ① 업로드 원본 이미지·PDF는 외부 AI로 보내지 않는다 ② 서버에서 읽은 글자, 사연, 질문 답변은 주민등록번호·계좌번호·전화번호·이름을 가린 뒤에만 AI에 보낸다 ③ 신분증과 신청인 인적사항은 받지 않는다 ④ 사건은 24시간 뒤 자동 삭제. 이 서비스는 **시연용이므로 합성 서류만** 올리게 안내한다(6절) |

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
| 401 | `CASE_TOKEN_INVALID` | 토큰 없음·불일치 | localStorage 목록에서 그 사건만 지우고 내 사건(또는 홈)으로 |
| 404 | `CASE_NOT_FOUND` | 사건 없음(삭제·24시간 만료 포함) | 같은 처리 |
| 404 | `NOT_FOUND` | 증빙·실행 등 하위 자원 없음 | 목록 새로고침 |
| 409 | `EVIDENCE_LIMIT` | 사건당 증빙 8개 초과 | 안내 |
| 409 | `ANALYSIS_IN_PROGRESS` | 이미 분석 중. `details.runId` 제공 | 그 `runId`로 4번 화면 이동 |
| 409 | `DRAFT_HAS_EDITS` | 재분석하면 사용자가 고친 초안이 덮임 | 확인창 후 `overwriteEditedDraft: true`로 재요청 |
| 409 | `VERSION_CONFLICT` | 초안 저장 시 `expectedVersion` 불일치. `details.currentVersion` | 최신 초안 다시 불러오기 |
| 413 | `FILE_TOO_LARGE` | 10MB 초과 | 안내 |
| 415 | `UNSUPPORTED_FILE_TYPE` | JPG·PNG·PDF 외(파일 내용으로 판별) | 안내 |
| 422 | `ANALYSIS_PRECONDITION` | 사연 20자 미만 또는 거래내역서 없음. `details.missing`에 `NARRATIVE`·`TRANSACTION_RECORD` | 3번 화면에 머물고 빠진 항목 강조 |
| 429 | `RATE_LIMITED` | 같은 IP에서 사건 생성 시간당 100회 초과, 또는 사건당 분석 시간당 5회 초과 | 안내 |
| 429 | `DAILY_LIMIT` | 서비스 전체 AI 분석 하루(한국 날짜) 300회 초과(비용 보호). **샘플 사건은 이 오류 대신 미리 만든 결과로 끝난다(4.10)** | "오늘 시연 한도를 다 썼어요" 안내 |
| 500 | `INTERNAL` | 서버 오류 | 재시도 버튼 |

한도 숫자(20·5·300)는 기본값이고 서버 환경변수로 바꿀 수 있다. 한도는 사건과 따로 저장한 사용량 기록으로 세므로 **사건을 지워도 줄어들지 않는다**(`docs/erd.md` 3.10). 오늘 사용량은 `GET /health`의 `dailyUsage`로 본다.

## 2. 코드값(enum)

| 이름 | 값 | 화면 표시 |
|---|---|---|
| `InflowType` | `SALARY` 급여 · `GOODS` 물품 거래 대금 · `UNEXPECTED` 모르는 입금(통장 묶기) · `OTHER` | P0 화면은 앞의 셋을 선택지로 노출 |
| `DocType` | `NOTICE` 지급정지 통지서 · `TRANSACTION_RECORD` 거래내역서(입금내역) · `INSURANCE_ELIGIBILITY` 건강보험자격득실확인서 · `EMPLOYMENT_CERT` 재직증명서 · `PAYSLIP` 급여명세서 · `BUSINESS_REG` 사업자등록증명 · `CHAT` 대화내역(문자·메신저, 협박 메시지 포함) · `CONTRACT` 계약서 · `TAX_INVOICE` 세금계산서 · `TRANSACTION_STATEMENT` 거래명세서 · `SHIPPING` 배송 기록 · `OTHER` 기타 | **신분증 값은 없다.** 신분증은 받지 않는다 |
| `CaseStatus` | `DRAFT` 입력 중 · `ANALYZING` 분석 중 · `REVIEW_READY` 결과 있음 · `ERROR` 마지막 분석 실패 | 홈 카드 "현재 단계" |
| `ExtractStatus` | `UPLOADED` · `PROCESSING` · `READY` · `FAILED` | `FAILED`는 "직접 확인" |
| `RunStatus` | `RUNNING` · `SUCCEEDED` · `FAILED` | |
| `Stage` | `EXTRACTING` 글자 읽는 중 · `COMPARING` 거래내역과 대조 중 · `DRAFTING` 초안 작성 중 · `FINISHED` | 4번 화면 단계. **FE는 문구를 하드코딩하지 않고 `stages[].label`을 그대로 표시한다** |
| `FindingStatus` | `MATCH` 자료와 일치 · `CONFLICT` 자료와 어긋남 · `STATEMENT_ONLY` 진술만 있음 · `UNKNOWN` 확인 못 함 | 탭 A 배지. `MATCH`는 "일치하는 자료가 있다"는 뜻이지 사실 인정·판정이 아님 |
| `SourceKind` | `EVIDENCE` 올린 서류 · `TRANSACTION` 거래내역서의 거래 행 · `NARRATIVE` 사용자 사연 | |
| `ChecklistCategory` | `OFFICIAL_REQUIRED` 법령상 제출 서류 · `TYPE_GUIDE` 유형별 안내 서류(기사·보도자료 근거) · `ANALYSIS_INPUT` AI 분석에 필요한 자료(공식 근거 없음) · `OPTIONAL` 있으면 좋은 자료 · `AI_RECOMMENDED` AI 권장 | 탭 B 묶음 제목. 다섯 묶음을 섞지 않고 따로 보여 줄 것 |
| `ChecklistStatus` | `SATISFIED` 올림 · `MISSING` 없음 · `NOT_COLLECTED` 받지 않음(직접 첨부) · `GUIDE_ONLY` 은행에서 작성 | |
| `DraftSection` | `DEPOSIT_REASON` 입금 경위 · `NO_INVOLVEMENT` 범죄에 가담하지 않았다는 설명 · `VICTIM_CONTEXT` 피해를 입은 경위 | 탭 C 초안의 묶음 제목. 소명 자료 3분류를 따른다(`docs/agent-design.md` 1절) |
| `NeedsCheckReason` | `CONFLICT` 자료와 어긋난 내용 · `NO_SOURCE` 근거 없음 · `QUOTE_NOT_FOUND` 인용을 원문에서 못 찾음 · `NUMBER_MISMATCH` 숫자가 근거와 다름 · `JUDGMENT_EXPRESSION` 판정처럼 읽히는 표현 · `SOURCE_UNREAD` 근거 서류를 못 읽음 | 탭 C "확인 필요" 툴팁. 여러 사유가 겹치면 이 순서대로 앞의 것 하나만 준다 |
| `LawSource` | `LAW` 통신사기피해환급법 · `DECREE` 같은 법 시행령 · `FORM4` 시행령 별지 제4호 이의제기신청서 | AI 의견·질문의 근거 조항 칩(4.11 `agentReview`). 화면에는 `label`을 그대로 쓴다 |
| `DeadlineState` | `UNKNOWN_NOTICE_DATE` 공고일 확인 필요 · `OK` · `URGENT` 7일 이하 · `EXPIRED` 지남 | D-day 배지 색 |
| `SampleScenario` | `GOODS` 물품 거래(청년 1인 온라인 판매 사업자, 체험 계정 test01) · `UNEXPECTED` 모르는 입금(통장 묶기, test02) · `SALARY` 급여(P1, 체험 계정 없음) | 샘플 체험 |

## 3. 화면별 호출

| 화면 | 호출 |
|---|---|
| L 체험 계정 선택(로그인) | 체험 계정 버튼: `POST /cases/sample { scenario }` → 응답을 localStorage 목록 맨 앞에 넣고 3번 화면(서류가 채워진 상태)으로. "직접 해 보기": 2번 화면으로 |
| 1 홈 | 서버 호출 없음. localStorage 목록이 있으면 "내 사건" 링크를 보여 준다. "샘플로 체험하기"는 L 화면으로 |
| M 내 사건(마이페이지) | localStorage 목록의 사건마다 `GET /cases/{id}` → 카드(유형·D-day·현재 단계·이어서 하기). 401·404면 목록에서 빼고 "만료된 사건을 정리했어요" 안내. 삭제: `DELETE /cases/{id}` 후 목록에서 제거 |
| 2 내 상황 | "다음": `POST /cases`(처음) 또는 `PATCH /cases/{id}`(수정). 응답의 `deadline`으로 D-day 표시 |
| 3 사연·증빙 | `GET /meta/requirements?inflowType=` 또는 `GET /cases/{id}/checklist` · `PATCH /cases/{id}`(사연, 입력 멈춘 뒤 1초 자동 저장) · `POST/DELETE /cases/{id}/evidence` · `GET /samples`(샘플 서류 내려받기 링크) · "분석 시작": `POST /cases/{id}/analysis-runs`에 **현재 사연을 `narrative`로 함께 보낸다**. 사연 20자 미만이거나 `requiredForAnalysis` 항목이 `SATISFIED`가 아니면 버튼을 비활성화하고 이유를 보여 준다(서버도 422로 막는다) |
| 4 분석 중 | `GET /cases/{id}/analysis-runs/{runId}` 1.5초 간격 폴링 |
| 5 결과 | `GET /cases/{id}/result` · `PATCH /cases/{id}/checklist/{itemId}` · `PUT /cases/{id}/draft`. 머리말·배너 아래, 탭 위에 **AI 의견·질문 카드**(`result.agentReview`, `null`이면 숨김). 카드의 "답하고 다시 분석": `POST /cases/{id}/analysis-runs`에 `answers`를 실어 보내고 4번 화면으로(지금의 다시 분석과 같은 흐름, 4.9). **`result.referral`이 있으면 탭 A~C 대신 상담 안내 카드와 그 아래 AI 의견·질문 카드를 보여 주고 6번으로 가는 버튼을 숨긴다(4.11)** |
| 6 제출 가이드 | 서버 호출 없음(정적 문구). 최종 점검 수치는 5번에서 받은 `result.summary`와 `draft.unconfirmedCount` 사용 · "이 사건 지우기": `DELETE /cases/{id}` 후 localStorage 목록에서 제거 |

## 4. 엔드포인트

### 4.1 `GET /health`

```json
{ "status": "ok", "agent": "claude", "demoMode": true, "dailyUsage": { "date": "2026-11-21", "used": 12, "limit": 300 } }
```

- `agent`: `claude` 또는 `scripted`(7절). 시연 전에 확인용.
- `dailyUsage`: 오늘(한국 날짜) 외부 AI를 부른 분석 수와 하루 한도. 운영 확인용이며 FE가 쓰지 않아도 된다. `used`가 `limit`에 닿으면 직접 만든 사건과 수정한 샘플 사건은 `429 DAILY_LIMIT`을 받는다.
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

`UNEXPECTED`(모르는 입금, 통장 묶기)의 유형별 항목은 다음과 같다(공통 항목은 같음). 사기범이 일부러 입금한 뒤 허위 신고로 계좌를 묶고 해제 대가를 요구하는 경우를 전제로 한다.

| code | label | category | acceptedDocTypes | requiredForAnalysis | sourceRef |
|---|---|---|---|---|---|
| `THREAT_MESSAGE` | 해제 대가를 요구하는 협박 문자·메시지 | `TYPE_GUIDE` | `CHAT` | `false` | 금융위원회 보도참고 2024.2.1 "통장협박 … 객관적인 자료(예: 협박문자 등)" `https://www.fsc.go.kr/no010101/81640` |
| `UNKNOWN_DEPOSIT_RECORD` | 모르는 입금이 보이는 거래내역서 | `ANALYSIS_INPUT` | `TRANSACTION_RECORD` | **`true`** | `null` |
| `INCIDENT_REPORT` | 경찰·은행에 신고한 기록(사건사고사실확인원, 신고 접수증 등) | `OPTIONAL` | `OTHER` | `false` | 법률사무소 안내 글(공식 자료 아님) `https://www.yglaw.co.kr/bbs/board.php?bo_table=lawinfo&wr_id=27` |

- `THREAT_MESSAGE.note`: "통장협박 피해는 협박 문자 같은 객관적인 자료로 소명할 수 있습니다. 받은 메시지는 지우지 말고 캡처해 두세요." (금융위원회 보도참고 2024.2.1, 위 표의 출처와 같음)
- `INCIDENT_REPORT.note`: "내가 피해를 입었다는 것을 보여 주는 기록입니다. 신고했다면 접수증이나 사건사고사실확인원을 받아 두세요." 공식 근거를 찾으면 `TYPE_GUIDE`로 올린다.
- 이 항목의 서류는 v0.4 FE와 맞추려고 새 `DocType`을 만들지 않고 `OTHER`로 받는다. 그래서 이 사건에 `OTHER` 서류가 하나라도 있으면 충족(`SATISFIED`)으로 계산한다.
- 이 유형은 공식 서류 목록을 확인하지 못했다. 그래서 위 세 항목 외에는 AI가 사연을 보고 `AI_RECOMMENDED` 항목(예: 은행 상담 기록, 입금자에게 반환을 제안한 기록)을 더한다. 이 항목들은 고정 항목과 같은 서류 종류(`CHAT`·`OTHER`)를 받으므로, 협박 문자를 올렸다고 자동으로 충족되지 않는다(4.8 규칙).

- `acceptedDocTypes`가 여러 개면 **그중 하나만 있어도 충족**이다. 업로드 화면에서 항목을 누르면 `acceptedDocTypes`의 첫 값을 기본 `docType`으로 쓰고, 여러 개면 고르게 한다.
- `requiredForAnalysis: true`는 **AI 분석에 필요한 서류**라는 뜻이고, 법령·기사상 제출 의무와는 별개다. 항목 옆에 "AI 분석에 필요" 배지를 붙인다. 모든 유형에서 거래내역서 한 항목만 `true`다.
  - 급여: `SALARY_DEPOSIT`. 기사가 든 서류와 같아서 `TYPE_GUIDE` 묶음에 있다.
  - 물품 거래: `DEPOSIT_RECORD`. 기사 근거가 없어서 `ANALYSIS_INPUT` 묶음에 있다.
  - 모르는 입금: `UNKNOWN_DEPOSIT_RECORD`. 같은 이유로 `ANALYSIS_INPUT` 묶음에 있다.
- `OTHER`(화면에 없는 값)는 공통 항목(`OBJECTION_FORM`, `ID_COPY`, `NOTICE`)과 `DEPOSIT_RECORD`(거래내역서, `ANALYSIS_INPUT`, `requiredForAnalysis: true`)만 준다. 분석 시작 조건이 모든 유형에 거래내역서를 요구하기 때문이다.
- 이 절에 문구가 없는 항목의 `note`는 `null`이다. 고정 항목은 어느 사건에나 맞는 내용만 담고, 사건 상황에 맞춘 안내는 분석 후 `AI_RECOMMENDED` 항목과 탭 A의 어긋남 경고가 맡는다.

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

같은 IP에서 시간당 100회까지(`429 RATE_LIMITED`). 샘플 사건 생성(4.3.1)도 함께 센다.

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

응답 `201`: `POST /cases`와 같은 모양. `case.isSample: true`, `case.sampleScenario`에 시나리오 값, 사연·입금 정보·날짜(공고일 = 오늘 − 4일 등 오늘 기준 상대 날짜)·증빙이 채워져 있다. FE는 3번 화면으로 보내고, 사용자는 바로 "분석 시작"을 누를 수 있다. 버튼을 누를 때마다 새 사건이 생기므로 여러 심사위원이 같은 체험 계정을 눌러도 서로 섞이지 않는다. 생성 제한은 4.3과 같다.

| 시나리오 | 체험 계정 | 들어 있는 합성 서류 | 대조에서 보이는 것 |
|---|---|---|---|
| `GOODS` | test01 | 거래내역서(텍스트 PDF), 거래처와의 대화내역(PNG), 사업자등록증명(PNG) | 입금 일치, 대화 속 합의 금액과 입금액 **불일치**(탭 A `AMOUNT` 경고와 탭 C "확인 필요"), 거래명세서 없음(탭 B) |
| `UNEXPECTED` | test02 | 모르는 사람의 입금 10만 원이 보이는 거래내역서(텍스트 PDF), "20만 원 보내면 신고 취하해 줄게" 협박 문자(PNG) | 입금 금액 일치, 입금 뒤 그 돈이 빠져나가지 않음(거래내역 조회), 사연의 입금 날짜와 거래내역 날짜 **불일치**(탭 A `DATE` 경고), "바로 은행에 알렸다"는 진술만 있음(탭 A `STATEMENT_ONLY`, 탭 B는 고정 항목 `INCIDENT_REPORT` 피해 신고 기록이 `MISSING`으로 보인다. 같은 서류를 AI 권장 항목으로 다시 내지 않는다) |
| `SALARY` | 없음(P1, 시간이 남으면) | 급여 입금이 보이는 거래내역서(텍스트 PDF), 재직증명서(PNG) | 입금 금액·날짜 일치, 근무 사실 근거 |

- **날짜:** 통지일·공고일만 오늘 기준 상대 날짜다(통지일 = 오늘 − 6일, 공고일 = 오늘 − 4일). 입금일과 사연·서류 속 날짜는 고정이다(`GOODS` 2026-11-08, `UNEXPECTED` 사연 2026-11-11). 서류가 고정 파일이라 입금일까지 바꾸면 사연·서류와 어긋나기 때문이다.
- `SALARY`는 P1이라 준비되기 전까지 `400 VALIDATION_ERROR`(`details.fields.scenario`)를 준다.
- 서류는 사건마다 복사본으로 들어간다(`isSample: true`). 지우기·분석·24시간 삭제는 일반 서류와 같다.

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
    "sampleScenario": null,
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
- `deadline.basis`는 항상 문장이다(`null` 아님). 공고일을 모르면 `"공고일을 몰라 기한을 계산하지 못했습니다."`(5절 1).

### 4.5 `PATCH /cases/{caseId}` — 사건 수정 (화면 2 다시 저장, 화면 3 사연 자동 저장)

보낸 필드만 바꾼다. `inflow`는 객체 통째로 교체. 검증 규칙은 4.3과 같다.

```json
{ "narrative": "온라인 쇼핑몰을 운영하는 개인사업자입니다. 거래처 소매점에 가죽 지갑 3개를 15만 원에 납품하기로 하고 11월 8일 대금을 계좌로 받았습니다. 물건은 다음 날 택배로 보냈습니다." }
```

응답 `200 { "case": { … } }`. 저장된 값과 **실제로 다른 값**이 들어오면 `inputVersion`이 1 오른다. 같은 값을 다시 보내면 그대로다. `narrative`는 최대 2000자.

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

- `lowConfidenceRegions`: 글자를 흐리게 읽은 줄 수(정수). 글자를 읽기 전에는 `null`이다.

업로드만으로는 글자를 읽지 않는다. 글자 인식은 분석을 시작할 때 한다(글자가 들어 있는 PDF는 OCR 없이 바로 추출). 올리면 `inputVersion`이 오른다.

#### `GET /cases/{caseId}/evidence` → `200 { "items": [Evidence…] }`

#### `DELETE /cases/{caseId}/evidence/{evidenceId}` → `204`

미리보기 이미지는 FE가 업로드 전 파일로 만든다(`URL.createObjectURL`). 서버는 원본 파일을 내려주지 않는다(P0). 샘플 사건의 서류는 `GET /samples`의 `url`로 미리보기를 띄운다.

### 4.8 `GET /cases/{caseId}/checklist` — 현재 체크리스트

화면 3에서 올린 서류에 따라 항목이 채워지는 것을 보여 줄 때, 탭 B에서 쓴다. 분석 전에는 4.2의 항목에 상태만 붙고, 분석 후에는 `AI_RECOMMENDED` 항목이 더해진다. `AI_RECOMMENDED` 항목은 **가장 최근 성공한 분석 실행 것만** 준다(다시 분석하면 이전 실행의 권장 항목은 빠진다).

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
      "note": null,
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
- `AI_RECOMMENDED` 항목(한 실행당 최대 3개)의 `status`도 올린 서류로 계산하지만, **같은 사건의 고정 항목이 이미 받는 `docType`은 세지 않는다.** 예: test02에서 "반환을 제안한 대화"(`CHAT`)는 협박 문자(`CHAT`, `THREAT_MESSAGE`)를 올려도 `MISSING`이다. 이런 항목은 사용자가 "따로 준비함"(`checked`)으로 표시한다. 서류 종류가 겹친다고 AI 권장 항목을 지우지는 않는다(고정 목록과 같은 서류를 권하지 않는 것은 AI 지시로 막는다).

#### `PATCH /cases/{caseId}/checklist/{itemId}` `{ "checked": true }` → `200 { "item": {…} }`

### 4.9 분석 시작 — `POST /cases/{caseId}/analysis-runs`

```json
{
  "narrative": "온라인 쇼핑몰을 운영하는 개인사업자입니다. …",
  "overwriteEditedDraft": false,
  "answers": [
    { "questionId": "q1…", "answer": "다음 날 1개를 더 주문받아 4개 15만 원이 됐어요." }
  ]
}
```

- `narrative`(선택): 있으면 서버가 **먼저 저장한 뒤** 사전 조건을 검사하고 분석을 시작한다. 자동 저장(1초 지연)이 끝나기 전에 버튼을 눌러도 최신 사연으로 분석되게 FE는 항상 보낸다. 저장된 사연과 같으면 아무것도 바꾸지 않고 `inputVersion`도 그대로다(4.5와 같은 규칙). 그래서 샘플 사건을 고치지 않고 분석하면 "샘플 그대로" 조건(4.10)이 유지된다.
- `answers`(선택, v0.8): 결과 화면 AI 의견·질문 카드(4.11 `agentReview.questions`)의 답. 답을 쓴 질문만 보낸다(빈 답은 보내지 않음). 규칙:
  - `questionId`는 **가장 최근 성공 결과의 `agentReview.questions`**에 있는 것만 받는다. 아니면 `400 VALIDATION_ERROR`(`details.fields.answers`). 다른 탭에서 이미 다시 분석해 질문이 바뀐 경우이므로 FE는 결과를 새로고침하게 안내한다
  - `answer`는 1~500자(앞뒤 공백 제거 후). 벗어나면 `400 VALIDATION_ERROR`
  - 서버는 `narrative`처럼 답을 **먼저 저장한 뒤** 사전 조건을 검사하고 분석을 시작한다. 답이 하나라도 있으면 `inputVersion` +1(그래서 샘플 "그대로" 조건(4.10)은 깨진다)
  - 다음 분석에서 에이전트는 사연과 **이 사건에서 지금까지 받은 모든 질문·답**을 가린 뒤 함께 본다. 답은 사용자 진술이라 대조 근거로 쓰일 때 `kind`는 `NARRATIVE`다(새 근거 종류 없음)
  - 같은 질문에 다시 답하면 마지막 답만 남는다
- 사전 조건: 사연 20자 이상 + `requiredForAnalysis` 항목(거래내역서, `docType=TRANSACTION_RECORD`) 1개 이상 → 아니면 `422 ANALYSIS_PRECONDITION`, `details.missing`에 빠진 것(`NARRATIVE`, `TRANSACTION_RECORD`)
- 이미 실행 중 → `409 ANALYSIS_IN_PROGRESS` (`details.runId`)
- 사용자가 고친 초안이 있고 `overwriteEditedDraft=false` → `409 DRAFT_HAS_EDITS`
- 사건당 시간당 5회 → `429 RATE_LIMITED`, 서비스 전체 하루 300회 → `429 DAILY_LIMIT`. 하루 한도는 외부 AI를 부르는 실행만 센다(1.1)
- **상담 안내 검사(v0.8 변경):** 서버가 먼저 사연과 답변을 정해 둔 표현 목록(통장·계좌·체크카드 대여·양도, 비밀번호 전달, 환전·구매대행·송금 알바, 현금 인출 후 전달 등)으로 찾는다. 찾은 부분은 에이전트에 넘기고, **에이전트가 문맥을 읽어** 상담을 권할지 정한다("빌려준 적 없어요"처럼 부정하는 문장은 권하지 않는다). 권할 때는 사연·답변 원문을 인용해야 하고 서버가 원문에 있는지 확인한다. 권하면 실행은 `SUCCEEDED`로 끝나고 결과에 `referral`과 질문(`agentReview.questions`)을 넣으며 초안은 만들지 않는다(4.11). 사용자가 질문에 답하고 다시 분석하면 상담 안내가 풀릴 수 있다. 가짜 분석·미리 만든 결과에서는 표현 목록(부정문 제외)만으로 정한다. 이 실행은 외부 AI를 부르므로 하루 한도에 센다

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
    { "seq": 3, "type": "TOOL_CALL", "title": "거래내역 조회", "summary": "사연의 11월 8일 대금 입금을 확인하려고 11/1~11/10 입금을 조회 → 2건", "status": "DONE", "at": "2026-11-21T06:45:19Z" },
    { "seq": 4, "type": "CONFLICT", "title": "자료와 어긋남", "summary": "대화내역의 합의 금액(120,000원)이 사연·입금액(150,000원)과 다릅니다", "status": "DONE", "at": "2026-11-21T06:45:27Z" }
  ],
  "error": null,
  "startedAt": "2026-11-21T06:45:00Z",
  "finishedAt": null
}
```

- `stages[].status`: `PENDING` · `RUNNING` · `DONE` · `FAILED`
- `TOOL_CALL`은 거래내역·서류 조회 말고 **법령 조회**(v0.8)도 남긴다. 예: `{ "type": "TOOL_CALL", "title": "법령 조회", "summary": "물품 대금이 이의제기 사유가 되는지 확인하려고 법 제7조 조회" }`. step `type` 값은 늘지 않는다.
- `TOOL_CALL`의 `summary`는 **AI가 밝힌 조회 이유 + 결과 건수**다. 이유에 판정처럼 읽히는 표현이 있으면 서버가 이유를 빼고 조회 범위만 적는다. `VERIFY`는 후검증 결과다(예: "근거와 다른 숫자 1개를 AI가 고쳐 다시 확인했습니다", `docs/agent-design.md` 2.6).
- `steps`는 AI가 실제로 한 일을 보여 주는 기록이다. 화면에 다 보여 줄 필요는 없지만, 마지막 몇 줄을 흐리게 보여 주면 "AI가 무엇을 하는지" 시연에 좋다. `type`: `OCR` · `TOOL_CALL` · `FINDING` · `CONFLICT` · `DRAFT` · `VERIFY` · `FALLBACK` · `SAFETY` · `FAILED`
- 서류 하나를 못 읽어도 분석은 계속된다(그 단계만 `FAILED`).
- **샘플 사건 대체 결과:** `isSample: true`이고 사연·서류를 샘플 그대로 둔 사건(`inputVersion`이 생성 때와 같음)에서 AI 호출이 실패하거나 하루 한도(`DAILY_LIMIT`)를 넘으면, 서버는 실패로 끝내지 않고 그 시나리오용으로 미리 만든 결과로 `SUCCEEDED` 처리한다. 이때 `steps`에 `{ "type": "FALLBACK", "title": "미리 만든 결과 사용", "summary": "지금은 AI 분석을 쓸 수 없어 샘플용으로 미리 만든 결과를 보여 드립니다." }`를 남기고, 결과의 `precomputed`가 `true`가 된다(4.11). 사용자가 사연이나 서류를 바꾼 샘플 사건은 일반 사건처럼 실패·429를 받는다.
- 실패 시 `status: "FAILED"`, `error: { "code": "AGENT_FAILED" | "AGENT_TIMEOUT" | "AGENT_REFUSED", "message": "…" }`. FE는 메시지와 "다시 시도"(4.9 재호출)를 보여 준다.

### 4.11 결과 — `GET /cases/{caseId}/result`

가장 최근 **성공한** 분석 결과. 없으면 `404 NOT_FOUND`. `findings`, 근거 거래, `checklist`의 `AI_RECOMMENDED` 항목, `draft`는 모두 이 실행 것만 준다. 이전 실행의 것은 섞이지 않는다.

```json
{
  "runId": "a7e…",
  "basedOnInputVersion": 4,
  "isStale": false,
  "generatedAt": "2026-11-21T06:45:41Z",
  "precomputed": false,
  "referral": null,
  "agentReview": { "...": "아래 'AI 의견·질문' 참고(v0.8)" },
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
- `referral`: 보통은 `null`. 4.9의 상담 안내 검사에서 상담을 권하면 아래 모양이고, 이때 `findings: []`, `draft: null`, `summary`는 모두 0이며 `GET /cases/{id}/draft`는 `404 NOT_FOUND`다. **이전 분석에서 만든 초안이 있었으면 서버가 지운다**(다시 분석해 상담 안내로 끝난 경우). 체크리스트는 평소처럼 준다. `agentReview`는 이때도 있고, 어떤 상황이었는지 묻는 질문이 들어 있다(v0.8).

```json
"referral": {
  "code": "LEGAL_CONSULT",
  "matchedPhrases": ["통장을 빌려"],
  "message": "사연에 통장을 빌려주거나 남의 돈을 대신 보낸 것으로 보이는 표현이 있어 소명서 초안을 만들지 않았습니다. 이런 경우에는 이의제기 전에 법률 상담을 먼저 받으세요.",
  "contacts": [
    { "name": "대한법률구조공단", "phone": "132" },
    { "name": "금융감독원", "phone": "1332" }
  ]
}
```

  - 이 안내는 사람이나 사건을 판정하는 것이 아니라 사연에 상담이 먼저 필요해 보이는 표현이 있음을 알리는 것이다. `matchedPhrases`는 **서버가 사연·답변 원문에 있다고 확인한 글자**이고(v0.8), 화면에 그대로 보여 준다. 잘못 걸렸으면 사용자가 AI 의견·질문 카드의 질문에 답하거나 사연을 고쳐 다시 분석할 수 있다.
#### AI 의견·질문 — `agentReview` (v0.8)

에이전트가 법령·서류를 근거로 낸 **조건부 의견**과, 소명에 부족한 사실을 묻는 **질문**이다. 사용자가 질문에 답하고 다시 분석하면(4.9 `answers`) 에이전트가 답을 반영해 대조·초안을 다시 만들고 필요하면 또 묻는다. 실제·가짜·미리 만든 결과 모두 채운다. v0.8 이전에 만든 결과는 `null`이다.

```json
"agentReview": {
  "notice": "올린 자료와 말씀하신 내용을 기준으로 AI가 정리한 의견입니다. Proofy는 변호사가 아니며, 지급정지 해제 여부는 은행이 판단합니다.",
  "opinions": [
    {
      "opinionId": "o1…",
      "text": "말씀하신 내용과 거래내역을 기준으로 보면, 11월 8일에 받은 150,000원은 물건값으로 받은 돈이라고 설명할 수 있는 사정으로 보여요.",
      "findingIds": ["f1…"],
      "lawRefs": [
        {
          "source": "LAW",
          "label": "법 제7조 제1항 제2호",
          "quote": "재화 또는 용역의 공급에 대한 대가로 받았거나",
          "verified": true
        }
      ],
      "needsCheck": false
    }
  ],
  "questions": [
    {
      "questionId": "q1…",
      "text": "대화에서는 '3개 12만원'이라고 했는데 입금은 15만 원이에요. 금액이 달라진 이유가 있나요?",
      "why": "자료와 어긋난 금액은 은행이 설명을 요청할 수 있어요.",
      "findingIds": ["f2…"],
      "lawRefs": []
    },
    {
      "questionId": "q2…",
      "text": "물건을 보낸 택배 송장이나 배송 조회 화면이 있나요?",
      "why": "'다음 날 택배로 보냈다'를 뒷받침하는 자료가 아직 없어요.",
      "findingIds": ["f3…"],
      "lawRefs": []
    }
  ],
  "answered": [
    { "questionId": "q0…", "text": "…", "answer": "…", "answeredAt": "2026-11-22T06:45:41Z" }
  ]
}
```

| 필드 | 뜻 |
|---|---|
| `notice` | 카드 맨 아래 안내 문구. 서버가 주는 문장을 그대로 보여 준다 |
| `opinions` | 0~3개. 조건부 의견("말씀하신 내용과 자료를 기준으로 보면 ~로 설명할 수 있어 보여요"). **결과 예측("해제될 거예요", "가능성이 높아요")은 하지 않는다** |
| `opinions[].findingIds` | 같은 결과의 `findings` ID. 누르면 탭 A의 그 항목으로 이동하게 쓸 수 있다(선택) |
| `opinions[].needsCheck` | 서버 검사에서 걸린 의견: 근거 조항을 원문에서 못 찾음, 결과를 예측하는 표현, 근거 자료에 없는 금액·날짜. FE는 초안의 "확인 필요"와 같은 표시를 한다 |
| `lawRefs[]` | 근거 조항. `source`(`LawSource`), `label`(칩에 보일 이름, 서버가 붙임), `quote`(원문 인용), `verified`(서버가 법령 원문에서 찾았나. `false`면 탭 A 인용처럼 흐리게 + "원문에서 찾지 못함") |
| `questions` | 0~3개. 질문마다 답 입력칸(최대 500자)을 하나씩. 0개면 질문 영역과 "답하고 다시 분석" 버튼을 숨긴다 |
| `questions[].why` | 왜 묻는지(작은 글씨) |
| `answered` | 이 사건에서 지금까지 답한 질문, 오래된 것부터. "이전에 답한 내용 N개"로 접어서 보여 준다 |

- **판정 필드는 두지 않는다.** `releasable`·`probability`·`verdict` 같은 필드는 없다. 의견은 결과 화면에만 보여 주고 **소명서 초안에는 넣지 않는다**(초안은 본인의 사실 진술만).
- 카드 동작: 답을 하나도 안 쓰면 버튼 비활성, 일부만 답하면 쓴 것만 보낸다. 버튼은 지금의 "다시 분석"과 같다(직접 고친 초안이 있으면 `409 DRAFT_HAS_EDITS` 확인창 → `overwriteEditedDraft: true`로 다시 보냄 → 4번 화면).

#### 그 밖의 필드

- `precomputed: true` = 이번에 AI가 분석한 결과가 아니라 샘플용으로 미리 만든 결과다(4.10). 결과 상단에 "지금은 AI 분석을 쓸 수 없어 미리 만든 샘플 결과를 보여 드려요" 배너를 `aiNotice`와 함께 보여 준다.
- `conflict.field`: `AMOUNT` · `DATE` · `COUNTERPARTY` · `OTHER`. 탭 A의 경고 문구에 `statement`(사용자 진술)와 `found`(자료)를 나란히 보여 준다.
- `verified: false`인 근거는 "원문에서 찾지 못한 인용"으로 흐리게 표시한다. 서버는 인용을 **AI가 실제로 본 마스킹한 글**(서류 줄의 마스킹본, 마스킹한 사연)과 대조한다. 그래서 `quote`에도 가린 값(`김*수`)이 그대로 나올 수 있다.
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
        "section": "DEPOSIT_REASON",
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
        "section": "DEPOSIT_REASON",
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
- `section`(`DraftSection`): AI 문장은 항상 값이 있고 `DEPOSIT_REASON` → `NO_INVOLVEMENT` → `VICTIM_CONTEXT` 순서로 온다. `VICTIM_CONTEXT`는 사연·자료에 피해 정황이 있을 때만 나온다. 사용자가 더한 문장은 `null`이다.
- FE는 문장을 배열 순서대로 보여 주고, `section`이 앞 문장과 달라지는 곳에 묶음 제목(`DraftSection` 화면 표시)을 넣는다. `null` 문장은 앞 문장 묶음에 이어 보여 준다.
- `fullText`는 복사용. 같은 묶음 안의 문장은 공백으로, 묶음이 바뀌는 곳은 빈 줄(줄바꿈 두 번)로 잇는다.

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
- `sentenceId: null`은 새 문장 → `origin: "USER"`, `needsCheck: false`, `section: null`. `section`은 PUT으로 바꿀 수 없다(보내도 무시).
- 응답 `200 { "draft": {…, "version": 2} }`. 버전이 다르면 `409 VERSION_CONFLICT`.
- 저장 시점: 문장 편집칸에서 포커스가 빠질 때, "직접 확인했어요"를 누를 때.

## 5. 기한(D-day) 계산 규칙 — 서버 구현, FE는 표시만

1. `publicNoticeDate`가 없으면 `state = UNKNOWN_NOTICE_DATE`, `deadlineDate = null`, `daysLeft = null`, `label = "공고일 확인 필요"`, `basis = "공고일을 몰라 기한을 계산하지 못했습니다."`.
2. 기간은 공고일 다음 날부터 센다(민법 제157조 초일 불산입). 시작일 `S = 공고일 + 1일`.
3. `S`에서 2개월 뒤 같은 날짜가 있으면 그 전날이 마지막 날, 그 달에 같은 날짜가 없으면 그 달 말일이 마지막 날(민법 제160조).
   - 예: 공고일 11/17 → 1/17 · 공고일 11/30 → 1/31 · 공고일 12/30 → 2/28(평년)
4. 공휴일 순연(민법 제161조)은 P0에서 하지 않는다. 그래서 `notice`에 항상 "은행 확인" 문구를 붙인다.
5. `daysLeft = deadlineDate − 오늘(한국 날짜)`. `label`: 양수 `D-n`, 0이면 `D-DAY`, 음수면 `기한 지남`.
6. `state`: `daysLeft > 7` → `OK`, `0 ≤ daysLeft ≤ 7` → `URGENT`, 음수 → `EXPIRED`.

## 6. FE만 가지는 것

| 항목 | 규칙 |
|---|---|
| localStorage | 키 `proofy.cases` = `[{ "caseId", "caseToken", "createdAt", "sampleScenario" }]` 배열, 최신이 앞. 최대 10건(넘으면 가장 오래된 것부터 뺀다). 401·404를 받은 사건만 목록에서 지운다. 읽기·쓰기는 try/catch로 감싸고 실패하면 빈 목록으로 본다 |
| 체험 계정(로그인 화면) | 아이디·비밀번호 입력 없이 버튼만 둔다. 서버는 계정을 모르고, 버튼은 아래 시나리오로 `POST /cases/sample`을 부를 뿐이다. 이름·연락처는 받지 않고 고정 가상 프로필만 보여 준다. "내 사건"은 이 브라우저의 localStorage 목록이라 계정과 무관하다 |
| 화면 2 입력 중 상태 | 서버에 보내기 전까지 FE 상태로만 둔다 |
| 별지 제4호서식 인적사항(이름, 생년월일, 주소, 연락처, 계좌번호) | **서버로 보내지 않는다.** 6번 화면 "PDF로 저장"에서 FE가 입력받아 인쇄용 화면에만 채우고 `window.print()`. 칸별 규칙은 아래 "별지 제4호 인쇄" |
| 합성 데이터 안내 | 홈: "시연용 서비스이며 예시는 합성 데이터입니다". 3번 업로드 영역: `demoMode`이면 "실제 서류 대신 샘플(합성) 서류만 올려 주세요" + [샘플 서류 받기] |
| 복사·PDF 저장 확인창 | 4.12 화면 규칙 |
| 화면 설정 | 큰글씨 모드·다크 모드 등은 FE만 가진다. localStorage 키 `setting-storage`(`proofy.cases`와 별개). 서버로 보내지 않는다 |
| 헤더 "내 사건" 버튼 | 내 사건 화면(M)을 뺀 모든 화면 헤더에 항상 보인다. 사건이 없으면 M 화면에서 빈 목록을 보여 준다 |
| 체험 계정 목록 | 아래 표 |

| 버튼 | 가상 프로필(화면 표시용) | `scenario` |
|---|---|---|
| test01 | 온라인으로 가죽 소품을 파는 1인 사업자(가상) · "물건값으로 받은 돈 때문에 계좌가 묶였어요" | `GOODS` |
| test02 | 사회초년생(가상) · "모르는 돈이 들어온 뒤 계좌가 묶였어요(통장 묶기)" | `UNEXPECTED` |
| 정적 문구 | 홈 소개, 절차 타임라인, 제출 가이드(낼 서류 3종, 심사 5영업일, 보완 요구 시 기한 안 재제출), 거짓 이의제기 처벌 경고 |
| AI 표시 | 결과 화면 상단에 `result.aiNotice`를 항상 보여 준다(해커톤 AI 활용 기준 제7조 권장) |

### 별지 제4호 인쇄 (6번 화면 "PDF로 저장", v0.8.1)

서식은 **현행판**(시행령 별지 제4호서식, 2026.9.29 개정, 레포 `docs/legal/form4_20260929.pdf`)을 따른다. 은행 배포 예시(예: 2016년판 "피해금 환급", "예금종별")와 칸 이름이 다르다. 서버 API는 바뀌지 않는다.

| 서식 칸 | 채우는 곳 | 규칙 |
|---|---|---|
| 접수번호·접수일자 | 비움 | 은행이 쓰는 칸(서식의 어두운 칸) |
| 신청인: 성명·생년월일·주소·휴대전화번호·전자우편주소·전화번호 | 사용자가 6번 화면에서 입력 | **서버로 보내지 않고 저장하지 않는다.** 사유 칸 작성에 필요 없고, 공개 시연 화면이라 사용자가 실제 정보를 넣을 수 있기 때문이다(대회 AI 활용 기준 제7조: 외부 AI에 실제 개인정보 전송 금지, 필요 없으면 개인정보를 쓰지 않음. 합성 데이터 자체는 금지 대상이 아니다). localStorage 등 브라우저 저장소에도 넣지 않고 화면 상태로만 둔다 |
| 지급정지 계좌등: 금융회사등·개설점포·자산종류·명의인·계좌번호 또는 계정정보 | 사용자가 6번 화면에서 입력 | 위와 같다 |
| **이의제기 사유** | `draft.fullText` + FE가 붙이는 "첨부 자료" 한 줄 | 아래 |
| 신청 날짜 | FE(오늘, 한국 날짜) | `OOOO년 OO월 OO일` |
| 신청인 성명 · (서명 또는 인) | 성명은 위 입력값, 서명은 비움 | 인쇄 뒤 손으로 서명 |
| ○○○ 금융회사등 귀하 | 위 "금융회사등" 입력값 | |
| 첨부서류 | 서식 고정 문구 그대로 | "1. 사기이용계좌등이 아니라는 사실을 증명하는 자료 1부 / 2. 사기이용계좌등 명의인의 신분증 사본 1부". 신분증은 Proofy가 받지 않으므로 사용자가 따로 낸다(6번 안내) |

**이의제기 사유 칸**
1. 본문은 가장 최근 `GET /draft`의 `fullText`(사용자가 고친 판). AI 의견(`agentReview`)은 넣지 않는다(신청서는 본인 사실 진술)
2. 끝에 빈 줄 하나를 두고 FE가 "첨부 자료" 한 줄을 붙인다: `첨부 자료: ` + (올린 증빙의 `docType` 화면 이름(FE `DOC_TYPE_LABELS`, 예: 거래내역서·대화내역. 중복 제거, `OTHER`는 `originalName`) ∪ `checked: true`인 체크리스트 항목의 `label`)을 `, `로 이음 + `.`. 둘 다 없으면 붙이지 않는다. 별지 안내의 "객관적인 증빙자료 내용"을 코드로 채우는 것이고, AI가 쓰면 근거 없음으로 "확인 필요"가 붙기 때문에 FE가 만든다
3. 칸 위에 서식 안내 세 줄을 작은 글씨로 둘 수 있다(인쇄 포함 여부는 FE 판단): "입금된 시간, 금액 / 해당 자금을 입금받게 된 상세 사유 / 입금받은 자금에 대하여 본인의 권원임을 주장하는 사유와 객관적인 증빙자료 내용"
4. 칸을 넘치면 다음 쪽에 "이의제기 사유(계속)"으로 이어 인쇄한다. 글을 자르지 않는다
5. 인쇄본에는 "확인 필요"·"직접 확인함" 표시와 근거 링크를 넣지 않는다

**인쇄 전**: `unconfirmedCount > 0`이면 복사와 같은 확인창(4.12 화면 규칙, 법 제16조)을 띄운다. `result.referral`이 있는 사건은 초안이 없으므로 인쇄 버튼을 보여 주지 않는다(3절 5번).
**6번 안내**: "은행이 주는 이의제기 신청서 양식이 있으면 사유 칸 내용을 그대로 옮겨 적으세요" 한 줄을 둔다.

## 7. 가짜 분석 모드

서버를 `AGENT_LLM=scripted`로 띄우면 Claude를 부르지 않고 정해진 규칙으로 결과를 만든다. 단계마다 1~2초씩 쉬어서 4번 화면 진행 표시가 보인다. 응답 모양은 실제와 같다(`GOODS` 샘플은 4.11 예시와 같은 결과를 낸다). `agentReview`도 시나리오별로 정해 둔 의견·질문을 낸다(v0.8). 질문에 답하고 다시 분석해도 가짜 분석은 답 내용을 읽지 않고 같은 결과를 내며, 답한 질문은 `answered`로 옮긴다. 상담 안내는 표현 목록(부정문 제외)만으로 정한다. 4.10의 "미리 만든 결과"는 이 모드가 각 샘플 시나리오에 내는 결과와 같은 것을 쓴다. FE 개발·리허설은 이 모드로 하고, `GET /health`의 `agent` 값으로 어느 모드인지 확인한다.

## 8. 아직 안 정한 것

| 항목 | 기본값(합의 전까지) |
|---|---|
| 개발 서버 주소, FE 배포 주소 | BE가 배포 후 공유. FE는 Cloudflare 고정 도메인을 CORS 등록을 위해 BE에 알려 줌(미리보기 주소 제외) |
| 재분석 시 탭 B의 사용자 체크(`checked`) 유지 | 같은 `code`인 공식·유형 항목은 유지, AI 권장 항목은 새로 만듦 |
| M 내 사건(마이페이지) | 시간 부족 시 제외(화면 문서 범위 결정과 같음). API는 이미 있음. **L 체험 계정 선택은 제외하지 않는다** |
| 법령 안내("내 상황 정리": 이의제기 사유 3가지와 유형별 보통 쓰는 사유, 6번 제출 안내) | **보류.** FE와 합의한 v0.6.5로 프로토타입을 먼저 완성하고, 그 뒤 개선안으로 FE와 다시 논의한다. 되돌린 안: v0.7(화면 2A + `GET /legal-guides`), v0.7.1(2A 대신 3번 위 카드). 서버에는 `GET /legal-guides`가 남아 있지만 계약 밖이라 FE는 쓰지 않는다 |

## 변경 이력

| 날짜 | 버전 | 내용 |
|---|---|---|
| 2026-11-23 | 0.8.3 | 4.2 `THREAT_MESSAGE.note` 문구를 "통장협박 피해는 협박 문자 같은 객관적인 자료로 소명할 수 있습니다. …"로(이전 "협박 문자가 없으면 이의제기가 받아들여지기 어렵다는 보도"는 결과 예측처럼 읽힘, 원칙 1). test02 샘플 사연을 문단 4개로(#90). 응답 모양 그대로, FE 변경 없음 |
| 2026-11-22 | 0.8.2 | 같은 IP 사건 생성 한도를 시간당 20회 → 100회로(1.1 429, 4.3). 심사장·리허설에서 같은 와이파이로 체험 사건을 많이 만들기 때문. 응답 모양 그대로, FE 변경 없음 |
| 2026-11-22 | 0.8.1(제안) | 6절 "별지 제4호 인쇄": 현행 서식(2026.9.29 개정) 칸별로 누가 채우는지, 이의제기 사유 칸 = `fullText` + FE가 붙이는 "첨부 자료" 한 줄(올린 증빙 `docType` 이름 ∪ `checked` 항목 `label`), 넘치면 다음 쪽, 인쇄 전 확인창. **서버 API 변경 없음(FE 규칙만)** |
| 2026-11-22 | 0.8(제안) | 인터뷰형 에이전트(`docs/proposals/v0.8-agent-interview.md`). ① 4.11 결과에 `agentReview`(조건부 AI 의견 `opinions`, 근거 조항 `lawRefs`, 질문 `questions`, 이전 답 `answered`), 2절 `LawSource` ② 4.9 분석 시작에 `answers`(질문 답변, 답이 있으면 `inputVersion` +1, 잘못된 `questionId`는 400) ③ 상담 안내: 표현 목록이 찾은 부분을 에이전트가 문맥으로 확인해 정함, `matchedPhrases`는 서버가 확인한 원문 인용, 상담 안내 결과에도 질문이 있어 답하고 다시 분석 가능, 하루 한도에 셈. `referral` 응답 모양은 그대로 ④ 4.10 법령 조회도 `TOOL_CALL` ⑤ 3절 5번 화면: 탭 위(상담 안내 때는 상담 카드 아래)에 AI 의견·질문 카드. **필드 추가뿐이라 v0.6.5 FE가 그대로 동작한다.** FE 할 일: 카드 1개 새로, `ResultView`·`useAnalysisRetry`·`types/api.ts` 수정 |
| 2026-11-21 | 0.1 | 최초 작성 |
| 2026-11-21 | 0.2 | ① 사건은 화면 2 "다음"에서 생성 확정(사연은 화면 3에서 `PATCH`) ② `COMPARING` 문구를 "거래내역과 대조 중"으로, FE는 `stages[].label`만 표시 ③ 요구 서류에 `requiredForAnalysis` 추가, 거래내역서를 분석 시작 조건으로(`422`의 `details.missing`) |
| 2026-11-21 | 0.3 | 외부 검토 반영. ① 초안: `CONFLICT` 연결 문장 자동 확인 필요, 진술 값 일치 시 서버가 연결, `warnings`, 문장별 `confirmed`·`unconfirmedCount`, 복사·PDF 전 확인창 ② 개인정보 보장 항목·`demoMode`·합성 데이터 안내 ③ `POST /cases/sample`, `GET /samples` 샘플 체험 ④ 일정에 리허설·소개서·제출(업로드+이메일) ⑤ `ANALYSIS_INPUT` 분류 신설, 물품 거래는 사업자 판매 대금 전제·예시를 청년 1인 판매 사업자로 ⑥ IP당 사건 생성 제한, `DAILY_LIMIT` ⑦ 미래 날짜 400 ⑧ 분석 시작에 `narrative` 동봉 ⑨ CORS 허용 헤더 |
| 2026-11-21 | 0.4 | 체험 계정·마이페이지. ① L 체험 계정 선택(test01 `GOODS`, test02 `UNEXPECTED`), M 내 사건 화면 추가, 서버 인증은 그대로 ② localStorage `proofy.case` 한 건 → `proofy.cases` 배열 ③ `UNEXPECTED` 화면 노출, 유형별 항목(`THREAT_MESSAGE`, `UNKNOWN_DEPOSIT_RECORD`), 샘플 시나리오 추가, `SALARY` 샘플은 P1 ④ `case.sampleScenario` 추가 ⑤ 샘플 사건은 AI 실패·하루 한도 초과 때 미리 만든 결과로 끝남(`result.precomputed`, step `FALLBACK`) ⑥ 상담 안내 검사: 통장 대여·송금 대행 표현이 사연에 있으면 초안 대신 `result.referral`(step `SAFETY`) |
| 2026-11-22 | 0.6.5(되돌림) | v0.7·v0.7.1(화면 2A·3번 위 "내 상황 정리" 카드, `GET /legal-guides`)을 되돌리고 FE와 합의한 v0.6.5로 돌아감. 두 안은 8절에 보류로 남김(프로토타입 완성 뒤 FE와 논의). FE가 새로 만들 것 없음 |
| 2026-11-22 | 0.6.5 | 4.8: `AI_RECOMMENDED` 항목은 한 실행당 최대 3개, 고정 항목이 받는 `docType`으로는 자동 충족되지 않음(`MISSING`, 사용자가 `checked`로 표시). 4.2 `UNEXPECTED`에 같은 설명. 응답 모양 변경 없음 |
| 2026-11-22 | 0.6.4 | FE 코드(타입·목 서버)와 대조해 정하지 않았던 곳을 명시(이슈 #40). ① 4.4·5절: 공고일을 모를 때 `deadline.basis`는 `null`이 아니라 문장(FE가 이미 문장으로 처리) ② 4.1 `dailyUsage`를 지금부터 실제로 준다(오늘 외부 AI를 부른 분석 수, 한도 `DAILY_ANALYSIS_LIMIT`). 한도 초과 429는 그대로 ③ 4.7 `lowConfidenceRegions`는 정수 또는 `null`(FE 타입 `unknown[]`은 `number`로, 지금은 항상 `null`) ④ 4.3.1 test02: "바로 은행에 알렸다"는 AI 권장 항목이 아니라 고정 항목 `INCIDENT_REPORT`로 보인다(탭 B에 같은 서류가 두 번 나오지 않게). **FE 코드 수정 없이 동작한다** |
| 2026-11-21 | 0.6.3 | 4.3.1 설명 보충: 샘플 사건 날짜 규칙(통지일·공고일만 상대, 입금일·사연·서류 날짜 고정), `SALARY` 샘플은 준비 전까지 400, 서류는 사건마다 복사본. 응답 모양 변경 없음 |
| 2026-11-21 | 0.6.2 | ① 4.2에 `OTHER` 유형 목록과 "문구가 없는 항목의 `note`는 `null`" 규칙 ② 4.8 예시의 `TRADE_DOCUMENT.note`를 `null`로(사건별 문구는 AI 권장 항목·탭 A가 맡음). 서버 응답 모양 변경 없음 |
| 2026-11-21 | 0.6.1 | FE 코드에 맞춤(서버 동작 변경 없음). ① 로컬 BE 주소 `http://localhost:8080` ② 6절에 FE 전용 화면 설정(`setting-storage`)과 헤더 "내 사건" 버튼 |
| 2026-11-21 | 0.6 | FE 수정 요청 반영(`docs/erd.md` v1.1). ① 한도·비용을 사건과 분리한 사용량 기록으로 셈(사건 삭제로 줄지 않음), 한도 숫자는 서버 환경변수 ② `GET /health`에 `dailyUsage` 추가 ③ 인용 검증은 마스킹한 글(서류·사연) 기준, 사연도 마스킹해서 AI에 보냄 ④ `PATCH`와 분석 시작의 `narrative`는 값이 실제로 바뀔 때만 `inputVersion` +1 ⑤ 다시 분석해 상담 안내로 끝나면 이전 초안 삭제(`GET /draft` 404) ⑥ 결과·근거 거래·AI 권장 항목·초안은 가장 최근 성공 실행 것만 ⑦ CORS는 FE 고정 도메인만(미리보기 제외). **필드 추가와 동작 명시뿐이라 v0.4·v0.5 FE가 그대로 동작한다** |
| 2026-11-21 | 0.5 | AI 에이전트 계획 반영(`docs/agent-design.md`). ① 초안 문장에 `section`(`DraftSection`: 입금 경위·가담하지 않았다는 설명·피해 경위), `fullText`는 묶음 사이 빈 줄 ② `UNEXPECTED`에 피해 신고 기록 항목 `INCIDENT_REPORT`(`OPTIONAL`, 서류 종류는 기존 `OTHER`). **모두 필드·항목 추가라 v0.4 FE가 그대로 동작한다** ③ `TOOL_CALL` step `summary`에 AI가 밝힌 조회 이유, `VERIFY` step 설명 |
