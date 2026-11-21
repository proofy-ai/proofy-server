# T03 사건 API

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 완료 · 이슈: #5 · PR: (이 PR)

## 범위

- `cases`, `case_inflows` 테이블
- `caseToken` 발급(한 번만 응답), DB에는 해시만 저장, `X-Case-Token` 인증
- `POST /cases`, `GET/PATCH/DELETE /cases/{id}`(계약 4.3~4.6), 검증 규칙(미래 날짜 400 등), `inputVersion`
- 응답의 `deadline`은 T02 함수로 매번 계산

## 제외

- IP당 생성 제한(T11)
- 증빙(T05)·샘플(T06)

## 완료 조건

- 계약 테스트 4·5·7 통과

## 구현 계획

> 계약 v0.6·ERD v1.1(PR #32) 기준으로 맞춘 계획이다. PATCH의 `inputVersion` 규칙(값이 실제로 바뀔 때만)은 v0.6과 같다.

### 파일

| 파일 | 내용 |
|---|---|
| `app/models/case.py` | `cases`, `case_inflows` 테이블 |
| `app/schemas/case.py` | 요청(`CaseCreate`, `CasePatch`, `InflowIn`), 응답(`CaseOut`, `CaseCreated`, `CaseEnvelope`) |
| `app/services/auth.py` | 토큰 발급·해시·검증, 라우터용 의존성 `get_authorized_case` |
| `app/services/cases.py` | 생성·조회·수정·삭제, 날짜 검증, `CaseOut` 만들기(`deadline`은 T02 함수) |
| `app/api/cases.py` | `POST /cases`, `GET/PATCH/DELETE /cases/{caseId}` |
| `tests/test_t03_cases.py` | 아래 테스트 |

### 테이블

- `cases`: `id`(UUID 문자열), `access_token_hash`(SHA-256 hex), `status`(기본 `DRAFT`), `is_sample`, `sample_scenario`, `sample_input_version`, `notice_received_date`, `public_notice_date`(NULL 허용), `has_prior_freeze`(NULL 허용), `narrative`(NULL 허용, 최대 2000자), `input_version`(기본 1), `created_at`, `updated_at`, `expires_at`(생성 + 24시간)
- `case_inflows`: `id`, `case_id`(FK UNIQUE, 사건 삭제 시 함께 삭제), `inflow_type`, `reported_amount_krw`(BigInteger, 사용자 **진술** 금액, API는 `inflow.amountKrw`), `occurred_at`(DATE, NULL 허용), `created_at`
- 컬럼 정본은 `docs/erd.md` 3.1·3.2
- 샘플 컬럼(`is_sample`, `sample_*`)은 T06에서 쓰지만 지금 같이 만든다. 마이그레이션 도구가 없어서 나중에 컬럼을 더하면 로컬 DB를 지워야 하기 때문이다. IP 해시는 ERD v1.1에서 `cases`가 아니라 `usage_events`(T11)로 옮겼다

### 동작

- **토큰:** `"pk_" + secrets.token_urlsafe(32)`(계약 예시 모양). 생성 응답에서만 주고 DB에는 SHA-256만 저장. 비교는 `hmac.compare_digest`
- **인증 순서:** `X-Case-Token` 없음 → 401 `CASE_TOKEN_INVALID` / 사건 없음 또는 만료(`expires_at` 지남) → 404 `CASE_NOT_FOUND` / 토큰 불일치 → 401 `CASE_TOKEN_INVALID`. 만료 사건의 실제 삭제는 T11
- **검증(400 `VALIDATION_ERROR`, `details.fields`):** 통지일 필수·미래 불가, 공고일·입금일 미래 불가(공고일이 통지일보다 앞서는 것은 허용), 금액 1~10,000,000,000 정수, `inflow.type`은 `SALARY`·`GOODS`·`UNEXPECTED`·`OTHER`, `hasPriorFreeze`는 키 필수·값 `null` 허용, 사연 2000자 이하. "오늘"은 T02의 `today_kst()`
- **PATCH:** 보낸 필드만 바꾼다(`null`을 보내면 `null`로). `inflow`는 통째로 교체. 값이 실제로 바뀌었을 때만 `inputVersion` +1
- **DELETE:** 204, 사건과 입금 정보 삭제(파일 삭제는 T05에서 추가)
- **응답 `case`:** 계약 4.4 키 전부. 아직 없는 기능의 값은 `evidenceCount: 0`, `latestRun: null`, `hasResult: false`로 고정하고 해당 작업(T05·T07·T08)에서 채운다. 시각은 `"2026-11-21T06:30:00Z"`(UTC, 초 단위)

### 테스트

계약 테스트 4·5·7은 11/21 승인됨.

| # | 내용 |
|---|---|
| 4 | `POST /cases` 201에 `caseId`·`caseToken`(`pk_`로 시작)·`case`. 이후 `GET` 응답 본문 어디에도 토큰 값이 없음 |
| 5 | 토큰 없이 `GET` → 401 `CASE_TOKEN_INVALID`, 틀린 토큰 → 401, 없는 `caseId` → 404 `CASE_NOT_FOUND`. 모두 `{error:{code,message,details}}` |
| 7 | 사건 A의 토큰으로 사건 B를 `GET`·`PATCH`·`DELETE` → 모두 401, 사건 B는 바뀌지 않음 |

**추가 제안(계약 관련이라 승인 필요):**

| # | 내용 |
|---|---|
| T03-a | 미래 통지일 → 400 `VALIDATION_ERROR`, `details.fields`에 `noticeReceivedDate` |
| T03-b | `PATCH`로 사연을 바꾸면 `inputVersion` 1 → 2, 같은 값을 다시 보내면 그대로 2 |
| T03-c | `expires_at`이 지난 사건 → 404 `CASE_NOT_FOUND` |

### 정할 것

- `inflow.type`에 `OTHER`도 받는다. 화면은 세 가지만 보여 주지만 계약 enum에 있으므로 서버는 거절하지 않는다
- 만료 사건을 404로 막는 것은 지금 하고, 실제 삭제(주기 정리)는 T11에서 한다

## 결정

- 11/21 사용자 승인: 계획과 추가 테스트 T03-a~c
- 11/21 PATCH에서 `noticeReceivedDate`·`inflow`를 `null`로 보내면 400(`details.fields`에 그 필드). 사건에 꼭 있어야 하는 값이다
- 11/21 금액·`hasPriorFreeze`는 엄격 타입(`StrictInt`·`StrictBool`). `"150000"` 같은 문자열 금액은 400(계약 1절 "문자열·소수 금지")
- 11/21 시각은 UTC로 시간대 없이, 초 단위로 저장하고 `"…Z"`로 응답(`app/schemas/common.py` `UtcDatetime`)
- 11/21 SQLite는 연결마다 `PRAGMA foreign_keys=ON`(ERD의 ON DELETE CASCADE가 실제로 동작하도록, `app/db.py`)
- 11/21 라우터 인자는 `Annotated` 타입(`DbSession`, `AuthorizedCase`). ruff B008(`Depends`를 기본값으로 쓰지 않기)

## 결과

- `uv run python -m pytest -q` → 29 passed(T03 13개: 계약 4·5·7, T03-a~c, 응답 키·입력 검증·PATCH 규칙·삭제)
- `uv run ruff check .` → All checks passed, `uv run ruff format --check .` → 이상 없음
- 미검증: 서버를 띄워 FE와 직접 연결해 보지는 않음(TestClient로만 확인). Postgres에서 실행 안 해 봄(T18)

