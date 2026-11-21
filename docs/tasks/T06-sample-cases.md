# T06 체험 계정(샘플 사건)

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 완료 · 이슈: #8 · PR: #38

## 범위

- `POST /cases/sample`(계약 4.3.1): `GOODS`·`UNEXPECTED`, 사연·입금·오늘 기준 상대 날짜·증빙이 채워진 사건, `isSample`, `sampleScenario`
- `GET /samples` 내려받기 목록과 파일 제공
- 서류는 자리표시 파일(실물은 T12)

## 제외

- `SALARY` 샘플(P1)
- 샘플 대체 결과(T11)

## 완료 조건

- 계약 테스트 6 통과

## 구현 계획

> 계약 v0.6.2 4.3.1·6절 체험 계정 표 기준. 서류 내용은 자리표시이고 실물은 T12에서 같은 파일 이름으로 바꾼다(코드 수정 없이).

### 파일

| 파일 | 내용 |
|---|---|
| `app/samples/goods/`, `app/samples/unexpected/` | 자리표시 서류(작은 PDF·PNG, "SYNTHETIC PLACEHOLDER" 표시). 표준 라이브러리만으로 만든다(Pillow 안 씀) |
| `app/services/samples.py` | 시나리오 정의(사연·입금·날짜·서류 목록), 샘플 사건 만들기, 내려받기 목록 |
| `app/schemas/sample.py` | `SampleCaseCreate`(`scenario`), `SamplesResponse` |
| `app/api/samples.py` | `POST /cases/sample`, `GET /samples`, `GET /samples/{scenario}/{fileName}` |
| `tests/test_t06_samples.py` | 아래 테스트 |

### 시나리오 내용

| | `GOODS`(test01) | `UNEXPECTED`(test02) |
|---|---|---|
| 입금 | `GOODS`, 150,000원, 입금일 2026-11-08 | `UNEXPECTED`, 100,000원, 입금일 2026-11-11(사연 기준) |
| 통지일·공고일 | 오늘 − 6일, 오늘 − 4일 | 같음 |
| 과거 이력 | 없음(`false`) | 없음(`false`) |
| 사연 | 계약 4.5 예시: "온라인 쇼핑몰을 운영하는 개인사업자입니다. 거래처 소매점에 가죽 지갑 3개를 15만 원에 납품하기로 하고 11월 8일 대금을 계좌로 받았습니다. 물건은 다음 날 택배로 보냈습니다." | 초안: "모르는 사람이 11월 11일 제 계좌로 10만 원을 보냈습니다. 며칠 뒤 계좌가 지급정지됐다는 통지를 받았고, 문자로 '20만 원 보내면 신고 취하해 줄게'라는 연락이 왔습니다. 저는 보낸 사람을 모르고, 받은 돈은 쓰지 않고 그대로 두었습니다. 바로 은행에 알렸습니다." |
| 서류 | 거래내역서 PDF(`TRANSACTION_RECORD`), 대화내역 PNG(`CHAT`), 사업자등록증명 PNG(`BUSINESS_REG`) | 거래내역서 PDF(`TRANSACTION_RECORD`), 협박 문자 PNG(`CHAT`) |
| 대조에서 보일 것(T08·T12) | 대화 속 합의 금액 12만 원 ↔ 입금 15만 원 | 사연의 입금일 11/11 ↔ 거래내역 11/12 |

- test02 사연은 상담 안내 표현 목록(통장 대여·송금 대행 등)에 걸리지 않게 썼다

### 동작

- `POST /cases/sample` `{ "scenario": "GOODS" | "UNEXPECTED" }` → 201, `POST /cases`와 같은 모양(`caseId`·`caseToken`·`case`). `isSample: true`, `sampleScenario`, 사연·입금·날짜·증빙이 채워진 상태
- 서류는 사건마다 **복사본**을 `evidence`(`isSample: true`)·`evidence_files`에 넣는다. 그래서 일반 서류처럼 지우기·분석·24시간 삭제가 같게 동작하고, 여러 사람이 같은 체험 계정을 눌러도 섞이지 않는다
- 만든 직후 `inputVersion` = 1, `sample_input_version` = 1("샘플 그대로" 판단 기준, T11)
- `SALARY`는 P1이라 400 `VALIDATION_ERROR`(`details.fields.scenario`). 그 밖의 값도 400
- `GET /samples`(인증 없음): 시나리오별 `{ name, docType, url }`. `url`은 `/api/v1/samples/goods/transaction_record.pdf` 같은 상대 경로(FE가 API 주소를 붙인다)
- `GET /samples/{scenario}/{fileName}`: 정의된 파일만 내려준다(목록에 없는 이름 → 404 `NOT_FOUND`, 경로 조작 불가). Content-Type은 파일 형식대로
- IP당 생성 제한(일반 사건과 함께 셈)은 T11

### 테스트

| # | 내용 | 승인 |
|---|---|---|
| 6 | `POST /cases/sample` `GOODS`·`UNEXPECTED` → 서류가 채워진 채 생기고 바로 분석 가능한 상태(사연 20자 이상, 거래내역서 항목 `SATISFIED`, `isSample`·`sampleScenario`, `evidenceCount` 3·2, 서류 `isSample: true`) | 11/21 승인됨 |
| T06-a | 같은 시나리오를 두 번 만들면 사건·토큰·서류 ID가 모두 다르고, 한쪽 서류를 지워도 다른 쪽은 그대로 | 승인 필요 |
| T06-b | `GET /samples` 목록 모양, 목록의 `url`로 받은 파일이 200·올바른 Content-Type, 없는 파일 404, `SALARY` 샘플 요청 400 | 승인 필요 |

### 정할 것

- **날짜:** 통지일·공고일만 오늘 기준 상대 날짜로 하고, **입금일과 사연·서류 속 날짜는 고정**(2026-11-08, 11-11·11-12)으로 둔다. 서류(PDF·PNG)는 고정 파일이라 날짜를 매일 바꿀 수 없고, 입금일까지 상대로 하면 사연·서류와 어긋나 대조 장면이 깨지기 때문이다. 심사 기간(~12/7)에도 입금일이 통지일보다 앞서므로 자연스럽다
- **test02 사연 문구**(위 초안)

## 결정

- 11/21 사용자 승인: 계획, 날짜 방식(통지일·공고일만 상대, 입금일·사연·서류 날짜 고정), test02 사연 초안, 테스트 T06-a·b
- 11/21 계약 v0.6.3: 4.3.1에 날짜 규칙, `SALARY` 400, 서류 복사본을 보충(FE 코드 영향 없음). FE에는 "샘플 서류 미리보기는 T12 전까지 자리표시"를 따로 알린다(사용자)
- 11/21 자리표시 서류는 표준 라이브러리로 만듦(PDF: 영문 글자 3줄에 날짜·금액, PNG: 옅은 회색 단색 + 설명 메타데이터). Pillow를 쓰지 않음
- 11/21 사건·증빙 만들기를 `stage_case`·`stage_evidence`(커밋 없이 세션에 넣기)로 나눠 샘플 사건을 한 번에 커밋
- 11/21 증빙 `created_at`이 Windows 시계 해상도 때문에 같아져 순서가 섞임 → 같거나 이전 값이면 1마이크로초씩 밀어 항상 커지게(`app/services/evidence.py` `_now`)
- 11/21 샘플 파일은 `Content-Disposition: inline`으로 내려 브라우저에서 바로 열린다
  - 11/22 T09에서 `attachment`(내려받기)로 바꿈: FE(Cloudflare)와 BE 출처가 달라 `<a download>`가 무시되고, inline이면 같은 탭이 파일 화면으로 바뀌었다(사용자 확인)

## 결과

- `uv run python -m pytest -q` → 51 passed(3회 연속). T06 6개: 계약 테스트 6(`GOODS`·`UNEXPECTED`), T06-a·b, 알 수 없는 시나리오 400, 샘플 사연이 상담 안내 표현을 피함
- `uv run ruff check .` → All checks passed, `uv run ruff format --check .` → 이상 없음
- 미검증: 서류 내용이 자리표시라 대조 장면(금액·날짜 어긋남)은 T12 실물 서류 이후 확인. IP당 생성 제한은 T11

