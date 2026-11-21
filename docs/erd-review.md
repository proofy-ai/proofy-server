# proofy_erd_v0.1 리뷰

- 대상: `etc/proofy_erd_v0.1.md` (DBML 파일 `proofy_erd_v0.1.dbml`은 폴더에 없어 문서 기준으로 봄)
- 기준: `docs/screen-flow.md`의 6개 화면, 마감(11/23 17:00), `docs/agent-design.md`
- 총평: **원칙은 아주 좋고, 범위가 화면보다 크다.** 진술과 증빙의 분리, 판정·제출 상태를 만들지 않는 점, 기한을 저장하지 않는 점은 그대로 가져간다. 대신 화면에 없는 추가 질문·승인·서버 PDF 흐름은 P1로 미루고, 화면에 필요한데 빠진 것(사건 접근 토큰, 체크리스트↔증빙 연결, 문장 단위 초안)을 채운다.

## 1. 잘 된 점 (유지)

| 항목 | 이유 |
|---|---|
| `case_inflows.reported_amount_krw`를 "진술"로, 거래 기록과 절대 합치지 않음 | 서비스의 핵심 원칙(주장 ≠ 증거)이 데이터에 박혀 있다 |
| `finding_sources`의 FK 셋 중 정확히 하나(`CHECK`) + 서버 검증기 조건 5개 | corebank의 후검증과 같은 생각. 그대로 구현 |
| `SUBMITTED`·심사 상태를 만들지 않음 | 제출·심사는 은행 몫이라는 경계가 명확 |
| D-day 비저장, 60일 고정 금지, `public_notice_source` | 기한 오산 위험을 설계로 막음 |
| `has_prior_freeze` NULL/false 구분 | 모름과 없음을 구분 |
| 체크리스트 `OFFICIAL_REQUIRED` / `AI_RECOMMENDED` 구분 + 공식 항목 출처 필수 | AI 권장이 법정 필수로 둔갑하는 것을 막음 |
| `analysis_runs.status`(기술 상태)와 `stage`(화면 단계) 분리 | 4번 화면 진행 표시에 바로 쓰임 |

## 2. 화면과 맞지 않는 곳

### 2.1 사건 생성 시점 — 화면 2 끝에서 만든다 (2026-11-21 결정, 계약 v0.2 반영)

ERD는 `narrative NOT NULL` 때문에 화면 3 완료 시점에 사건을 만들자고 한다. 그런데 화면 3은 **사연 입력과 사진 업로드가 같은 화면**이고, 업로드에는 `caseId`가 필요하다. 그러면 사연을 다 쓰기 전에는 사진을 못 올리고, 사진을 올리다 새로고침하면 다 날아간다. 홈의 "이어서 하기"도 서버 사건이 있어야 자연스럽다.

- 결정: `cases.narrative`는 **NULL 허용**으로 바꾼다. 화면 2의 "다음"에서 `POST /cases`, 화면 3에서 `PATCH`로 사연 저장. **분석 시작 때 사연 20자 이상 + 거래내역서(`TRANSACTION_RECORD`) 1개 이상을 검증**한다(2.5 참고).
- "빈 사건 남발" 우려는 로그인이 없는 이상 어느 시점에 만들어도 같다. 대신 24시간 자동 삭제(`expires_at`)로 정리한다.
- 이득: D-day를 화면 2에서 서버가 계산해 바로 돌려줄 수 있어 기한 계산이 한 곳에만 있다.

### 2.2 로그인 없음 → 사건 접근 토큰이 없다 (ERD 6-7 미결 사항)

화면 문서는 "로그인 없음, localStorage에 한 건". ERD는 "랜덤 ID만으로는 불충분"이라고만 적었다.

- 제안: `cases.access_token_hash`(CHAR 64). `POST /cases` 응답에 `caseToken`(32바이트 난수)을 **한 번만** 주고 서버는 SHA-256만 저장. FE는 `caseId`+`caseToken`을 localStorage에 두고 모든 요청에 `X-Case-Token` 헤더. 토큰 분실 = 새로 시작.

### 2.3 탭 B "부족한 서류"를 계산할 연결이 없다

화면 3은 "유형별 체크리스트에 맞춰 사진을 올린다", 탭 B는 그 체크리스트의 빈칸이다. 그런데 `checklist_items`와 `evidence` 사이에 연결이 없고, "건강보험자격득실확인서 **또는** 재직증명서 중 하나" 같은 택일 묶음을 표현할 수 없다.

- 제안: 유형별 **요구 서류 목록은 DB가 아니라 코드 상수**(출처 포함)로 두고, 각 항목에 허용 `docType` 목록을 둔다. 업로드 시 `evidence.doc_type`을 받으면 충족 여부는 계산으로 나온다.
- 분류(`category`)는 계약 v0.3 기준 `OFFICIAL_REQUIRED` / `TYPE_GUIDE` / `ANALYSIS_INPUT` / `OPTIONAL` / `AI_RECOMMENDED` 다섯 가지.
- `checklist_items` 테이블은 **AI 권장 항목과 사용자의 체크 표시**만 저장한다. 컬럼: `code`(공식 항목이면 상수 코드), `category`, `label`, `source_reference`, `checked`, `analysis_run_id`.
- 신분증 사본은 `NOT_COLLECTED`(받지 않음, 별도 첨부 안내) 상태로 항상 표시.

### 2.4 탭 C의 "확인 필요" 표시를 문장 단위로 못 한다

`drafts.reason_text`가 TEXT 하나라 "증빙 없는 문장"을 표시할 단위가 없다.

- 제안: `drafts.sentences_json` = `[{id, text, origin, findingIds[], needsCheck, needsCheckReason, confirmed, edited}]`, `drafts.warnings_json`. 사용자 수정 시 배열 전체를 `expectedVersion`과 함께 교체(409 충돌 처리는 ERD 그대로). 수정한 문장은 `edited=true`, `needsCheck`는 유지(근거가 생긴 게 아니므로), `confirmed`(사용자가 직접 확인함)는 글이 바뀌면 `false`로 되돌림. CONFLICT 관련 규칙은 계약 4.12.

### 2.5 "원장"의 정체 — `demo_transactions` 재검토 (거래내역서는 분석 필수로 결정)

신청인은 은행 원장을 볼 수 없다. 사용자가 가진 것은 **은행 앱에서 받은 거래내역서**다. 현재 `demo_transactions`는 은행 원장을 흉내 낸 고정 데이터라 (1) 시연 때 어떤 사건에 어떤 합성 거래를 넣을지 정하는 장치가 없고 (2) 실제 서비스로 확장하는 이야기가 안 된다.

- 제안: `transactions`로 바꾸고 `source`(`STATEMENT_OCR` / 확장 시 `OPEN_BANKING`), `evidence_id`(FK, 거래내역서), `region_index`, `raw_text` 추가. 거래내역서 OCR에서 AI가 행을 뽑고, 금액·일자 문자열이 OCR 영역에 실제로 있는 행만 저장한다.
- `finding_sources.source_kind`: `EVIDENCE` / `TRANSACTION` / `NARRATIVE`.

### 2.6 화면에 없는 기능이 ERD에 있음 → P1

| ERD 요소 | 화면 근거 | 제안 |
|---|---|---|
| `analysis_questions`, `messages`, `NEEDS_INPUT` 상태, 답변 후 재분석 | 6개 화면 어디에도 질문·답변 UI 없음 | **P1**. P0의 재분석은 "증빙 추가 → 다시 분석" 버튼만 |
| `drafts` 승인(`APPROVED`/`STALE`, `approved_*_version`) + 서버 PDF 생성 게이트 | 화면 6은 "최종 점검, 복사 또는 PDF 저장", PDF는 "시간 부족하면 뺀다" | **P1**. P0는 복사 + 브라우저 인쇄(PDF 저장) |
| `applicant_fields_json`, `account_fields_json`(별지 제4호 인적사항·계좌) | 화면에 입력 없음 | **서버에 저장하지 않는다.** 인쇄 화면에서 FE가 입력받아 그 자리에서만 쓴다. 개인정보를 서버·AI에 안 보내는 근거가 됨 |
| `cases.input_version` 증가 규칙 | 결과가 최신 입력 기준인지 보여 줄 때 필요 | **유지**. 결과 응답에 `isStale` 하나만 노출 |

### 2.7 빠진 컬럼

| 테이블 | 추가 | 이유 |
|---|---|---|
| `cases` | `access_token_hash`, `expires_at`, `is_sample`, `created_ip_hash` | 2.2, 자동 삭제, 샘플 체험(계약 4.3.1), IP당 생성 제한 |
| `evidence` | `is_sample` | 샘플 사건의 합성 서류 표시 |
| `analysis_runs` | `model`, `prompt_version`, `input_tokens`, `output_tokens`, `cost_micro_usd`, `steps_json` | 비용 근거(심사 "비용·운영 부담"), 4번 화면 진행 기록 |
| `evidence` | `low_confidence_regions`, `masked_text` | OCR 신뢰도 표시, AI에는 마스킹본만 전달 |
| `claim_findings` | `conflict_detail`(기대값/실제값) | 탭 A "어긋나는 부분 경고" |

`tool_trace_json`은 `steps_json`으로 합친다(단계 = 화면 표시 + 도구 호출 기록).

## 3. 작은 지적

- **상태 이름 통일.** ERD `DOCUMENT_MATCH/CONFLICT/USER_STATEMENT/UNKNOWN`, 프로토타입 HTML `MATCH/STATEMENT/UNKNOWN`. → `MATCH / CONFLICT / STATEMENT_ONLY / UNKNOWN`으로 통일(계약서 기준).
- **기한 계산 규칙을 적어 둘 것.** "달력상 2개월"만으로는 구현자마다 달라진다. 민법 기간 계산(초일 불산입, 말일 응당일 없으면 그 달 말일)을 따르고, 공휴일 순연은 P0에서 하지 않되 "은행 확인" 문구로 보완. 계약서 5절에 적었다.
- **증빙 개수 상한 5개는 빠듯하다.** 물품 거래는 통지서 + 사업자등록 + 대화내역 + 계약 서류 + 거래내역서 = 5개라 여유가 없다. 8개 제안.
- **사건 유형 확장값**(`UNEXPECTED`, `OTHER`)은 데이터 모델에 두되 FE 선택지는 `SALARY`, `GOODS`만. 동의.
- **`cases.status`는 4개로 충분**: `DRAFT`(입력 중) → `ANALYZING` → `REVIEW_READY` / `ERROR`. 홈 카드의 "현재 단계"는 이 값과 FE 라우트로 표현.
- **DBMS**: 로컬 SQLite, 배포 Postgres. JSON 컬럼은 SQLAlchemy `JSON` 타입이면 둘 다 동작.

## 4. P0 테이블 (9개)

```text
cases ─┬─< case_inflows          (P0 1건)
       ├─< evidence ──< transactions        (거래내역서에서 추출)
       ├─< analysis_runs ─┬─< claim_findings ──< finding_sources ─> evidence | transactions | (narrative)
       │                  └─< checklist_items (AI 권장)
       ├─< checklist_items      (사용자 체크 표시)
       └── drafts               (사건당 1개)
```

P1: `analysis_questions`, `messages`, `draft_revisions`, 승인·PDF 생성 이력.
