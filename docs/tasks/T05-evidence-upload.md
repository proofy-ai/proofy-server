# T05 증빙 업로드

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 완료 · 이슈: #7 · PR: #37

## 범위

- `evidence` 테이블, `POST/GET/DELETE /cases/{id}/evidence`(계약 4.7)
- 파일 내용으로 형식 판별(JPG·PNG·PDF), 10MB 413, 형식 415, 사건당 8개 409
- 사건 삭제 시 파일도 함께 삭제
- 올리면 `inputVersion` 증가, 체크리스트 충족 반영
- 파일 내용은 서버 디스크가 아니라 DB `evidence_files`에 저장(재배포 때 유실 방지, ERD v1.1 3.3.1). 쓰지 않게 되는 `UPLOAD_DIR` 설정(`app/config.py`, `.env.example`, README)은 이때 뺀다

## 제외

- 글자 추출(T13)

## 완료 조건

- 업로드·목록·삭제가 계약 모양으로 동작, 한도 오류 코드가 계약과 같음

## 구현 계획

> 계약 v0.6.2 4.7, ERD v1.1 3.3·3.3.1 기준.

### 파일

| 파일 | 내용 |
|---|---|
| `pyproject.toml`·`uv.lock` | `python-multipart` 추가(FastAPI가 multipart 업로드를 받는 데 필요, 순수 Python) |
| `app/models/evidence.py` | `evidence`, `evidence_files` 테이블 |
| `app/schemas/evidence.py` | `EvidenceOut`(계약 4.7 키), `EvidenceEnvelope`, `EvidenceList` |
| `app/services/evidence.py` | 형식 판별, 한도 검사, 저장·목록·삭제, `inputVersion` +1 |
| `app/api/evidence.py` | `POST/GET /cases/{caseId}/evidence`, `DELETE /cases/{caseId}/evidence/{evidenceId}` |
| `app/services/checklist.py` | `uploaded_evidence()`를 실제 증빙 조회로 바꿈(T04에서 빈 목록으로 둔 곳) |
| `app/services/cases.py` | 사건 응답의 `evidenceCount`를 실제 개수로 |
| `app/config.py`, `tests/conftest.py`, `.env.example`, README | `UPLOAD_DIR` 제거(파일을 DB에 두므로) |
| `tests/test_t05_evidence.py` | 아래 테스트 |

### 동작

- **검사 순서:** 토큰(401/404) → `docType` 값(400 `VALIDATION_ERROR`) → 사건당 8개 이미 있음(409 `EVIDENCE_LIMIT`) → 10MB 초과(413 `FILE_TOO_LARGE`) → 형식(415 `UNSUPPORTED_FILE_TYPE`). 개수는 파일을 읽기 전에 막는다
- **형식 판별:** 파일 앞부분(매직 바이트)으로만 판단한다. JPEG `FF D8 FF`, PNG `89 50 4E 47 0D 0A 1A 0A`, PDF `%PDF-`. 파일 이름·브라우저가 보낸 Content-Type은 믿지 않는다. 빈 파일은 415
- **크기:** 10MB = 10 × 1024 × 1024바이트. 최대치 + 1바이트까지만 읽어서 넘으면 413
- **저장:** `evidence` 행(`content_sha256`, `extract_status = UPLOADED`) + `evidence_files`에 파일 원본. 디스크에는 쓰지 않는다. 글자 추출 칼럼(`extracted_text` 등)은 T13에서 쓰지만 지금 같이 만든다(로컬 DB를 다시 만들지 않게)
- **원래 이름:** 경로를 떼고 파일 이름만, 255자까지. 비어 있으면 `upload`
- **올리기·지우기:** 성공하면 `inputVersion` +1(계약 4.7). 실패한 요청은 아무것도 바꾸지 않는다
- **목록:** 올린 순서(오래된 것 먼저). 파일 원본은 내려주지 않는다(계약 4.7, P0)
- **지우기:** 다른 사건의 `evidenceId`·없는 ID → 404 `NOT_FOUND`. 사건을 지우면 `evidence`·`evidence_files`가 함께 지워진다(ON DELETE CASCADE)
- **연결:** 체크리스트 충족 계산(T04)과 사건 응답 `evidenceCount`가 실제 증빙을 본다
- 샘플 사건용 `is_sample`은 칼럼만 두고 T06에서 쓴다

### 테스트(계약 관련이라 승인 필요)

| # | 내용 |
|---|---|
| T05-a | PNG 업로드 → 201, 계약 4.7 키, `mimeType`은 파일 내용 기준(이름이 `.jpg`여도 `image/png`), `extractStatus: UPLOADED`, `inputVersion` +1, 사건 `evidenceCount` 1, 해당 체크리스트 항목 `SATISFIED`·`satisfiedBy`에 그 ID |
| T05-b | 10MB 초과 413 `FILE_TOO_LARGE`, 이름만 `.pdf`인 텍스트 파일 415 `UNSUPPORTED_FILE_TYPE`, 9번째 업로드 409 `EVIDENCE_LIMIT`. 실패한 요청은 `inputVersion`을 바꾸지 않음 |
| T05-c | 지우기 204 → 목록에서 빠지고 `inputVersion` +1, 다른 사건의 `evidenceId`는 404, 사건을 지우면 `evidence_files`까지 지워짐 |

그 밖에(승인 불필요): 잘못된 `docType` 400, 토큰 없이 업로드 401

### 정할 것

- 없음(계약대로). `python-multipart` 의존성 추가만 확인

## 결정

- 11/21 사용자 승인: 계획과 테스트 T05-a~c
- 11/21 `python-multipart` 0.0.34 추가(`uv add`)
- 11/21 증빙 `created_at`은 마이크로초까지 저장해 올린 순서를 지킨다(응답은 초 단위)
- 11/21 사건 응답 `evidenceCount`는 조회로 계산(`to_case_out`이 DB 세션을 받도록 바꿈)

## 결과

- `uv run python -m pytest -q` → 45 passed(T05 5개: 계약 테스트 T05-a~c, 잘못된 `docType` 400·토큰 없음 401, 파일이 DB에 저장되고 이름의 경로가 떨어짐)
- `uv run ruff check .` → All checks passed, `uv run ruff format --check .` → 이상 없음
- OpenAPI(`/openapi.json`) 200, 업로드는 `multipart/form-data`
- 미검증: 브라우저(FE)에서 실제 파일 업로드, Postgres `BYTEA` 저장(T18)

