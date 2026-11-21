# T09 초안 API

- 단계: 2단계 가짜 분석 · 예정: 11/22 오후 · 상태: 완료 · 이슈: #11 · PR: 없음

## 범위

- `drafts` 테이블, 가짜 분석기가 초안 문장 생성
- `GET/PUT /cases/{id}/draft`(계약 4.12): 버전 충돌 409, 글이 바뀐 문장 `confirmed` 해제, 새 문장 `origin: USER`
- 확인 필요 규칙: CONFLICT 연결 문장, 진술 값 일치 자동 연결, 연결 안 된 CONFLICT `warnings`, `unconfirmedCount`

## 제외

- 실제 AI 초안·후검증(T17)

## 완료 조건

- 확인 필요 규칙이 계약대로 동작(테스트 목록은 구현 계획에서 승인)

## 구현 계획

### 할 일

| # | 내용 | 파일 |
|---|---|---|
| 1 | `drafts` 테이블(ERD 3.9, 사건당 1행). "저장한 적 있음"을 위해 `edited_at` 추가(ERD v1.3) | `app/models/draft.py`, `app/models/__init__.py` |
| 2 | 가짜 분석기가 초안 문장을 만든다. 분석기 출력에 `draft_sentences`(묶음, 글, 연결할 대조 항목 번호) 추가. `GOODS`는 계약 4.12 예시 문장, `UNEXPECTED`는 세 묶음(피해 경위 포함), 그 밖은 사연 기반 짧은 문장. 4번 화면 `DRAFT` 단계 문구를 "초안 문장 N개 작성"으로 | `app/agent/output.py`, `app/agent/scripted.py` |
| 3 | 저장할 때 서버가 확인 필요 규칙 적용(아래) | `app/services/drafts.py`(새), `app/services/results.py` |
| 4 | `GET /cases/{id}/draft`: 가장 최근 성공 실행의 초안. 없으면 `404 NOT_FOUND`. `unconfirmedCount`·`fullText`는 읽을 때 계산 | `app/api/draft.py`(새), `app/schemas/draft.py`(새) |
| 5 | `PUT /cases/{id}/draft`: 버전 확인(`409 VERSION_CONFLICT`, `details.currentVersion`), 글 바뀐 문장 `edited`·`confirmed` 처리, 새 문장 `USER`, 빠진 문장 삭제, `section` 무시 | 같은 파일 |
| 6 | 결과 API(`GET /result`)의 `draft`와 `summary.sentencesNeedingCheck` 채우기 | `app/services/results.py` |
| 7 | 다시 분석: 고친 초안이 있으면 `409 DRAFT_HAS_EDITS`, `overwriteEditedDraft: true`면 새 초안으로 덮기(지금은 항상 "없음"인 자리) | `app/services/analysis.py` |
| 8 | **샘플 서류를 "내려받기"(`Content-Disposition: attachment`)로.** FE와 BE 출처가 달라 `<a download>`가 무시되고 같은 탭이 파일로 바뀌던 문제(11/22 사용자 확인). T06 결정 변경 기록 | `app/api/samples.py`, `docs/tasks/T06-sample-cases.md` |

### 확인 필요 규칙(서버, 계약 4.12)

1. 연결된 대조 항목 중 `CONFLICT`가 있으면 `needsCheck: true`, 사유 `CONFLICT`
2. 문장 속 금액·날짜가 어떤 `CONFLICT` 항목의 진술 값(`conflict.statement`)과 같으면, 분석기가 연결하지 않았어도 서버가 그 항목을 `findingIds`에 붙이고 1번 적용(예: "150,000원")
3. 연결된 항목이 없거나 모두 `STATEMENT_ONLY`·`UNKNOWN`이면 `needsCheck: true`, 사유 `NO_SOURCE`
4. 어느 문장에도 연결되지 않은 `CONFLICT` 항목은 `warnings`에 `CONFLICT_NOT_IN_DRAFT`
5. 사유가 겹치면 계약 2절 `NeedsCheckReason` 순서로 앞의 것 하나. 나머지 사유(인용 못 찾음, 숫자 불일치, 판정 표현, 못 읽은 서류)는 T17 후검증
- `findingIds`는 같은 실행의 대조 항목만 들어간다(분석기는 번호로만 가리키고 서버가 ID로 바꿈, 원칙 3)

### 계약 테스트(승인 필요)

| # | 내용 |
|---|---|
| T09-a | `GOODS` 샘플 분석 뒤 `GET /draft` 응답 모양(4.12 필드 전부), 묶음 순서, "150,000원" 문장에 `CONFLICT` 자동 연결, `NO_SOURCE` 문장, `unconfirmedCount`, `fullText`의 묶음 사이 빈 줄 |
| T09-b | `PUT` 규칙: 글을 바꾸면 `edited: true`·`confirmed: false`, 같은 요청에서 `confirmed: true`면 `true`, 새 문장은 `origin: USER`·`section: null`·`needsCheck: false`, 빠진 문장 삭제, `version` +1, `expectedVersion`이 다르면 `409 VERSION_CONFLICT`와 `currentVersion` |
| T09-c | 다시 분석: 저장한 적 있는 초안이면 `409 DRAFT_HAS_EDITS`, `overwriteEditedDraft: true`면 새 초안 |
| T09-d | 결과 API의 `draft`가 `GET /draft`와 같고 `summary.sentencesNeedingCheck`가 맞음. 다른 사건 토큰으로 초안 조회·저장하면 401 |

그 밖(계약 테스트 아님): 샘플 파일 응답이 `attachment`인지.

### 정할 것

1. **글을 바꾼 문장의 `confirmed`:** 계약 4.12 문장이 앞뒤가 엇갈린다("보낸 값과 관계없이 `false`" vs "같은 요청에서 `true`면 `true`"). 추천: **글이 바뀐 문장은 `confirmed`를 생략하면 `false`, 같은 요청에 `true`를 보내면 `true`**(FE가 "고치고 바로 확인"을 한 번에 저장할 수 있게)
2. **다시 분석한 뒤 `version`:** 1로 되돌리지 않고 이어서 +1. 옛 화면이 들고 있던 버전으로 새 초안을 덮어쓰지 못하게(되돌리면 옛 버전 1과 새 버전 1이 같아짐)
3. **"고친 초안"의 기준(`DRAFT_HAS_EDITS`):** 한 번이라도 `PUT`으로 저장한 초안. "직접 확인했어요" 체크만 한 경우도 포함(다시 분석하면 그 체크도 사라지므로 묻는 게 맞음)
4. **`PUT` 잘못된 값:** 이 초안에 없는 `sentenceId`, 빈 글(공백만)은 `400 VALIDATION_ERROR`(`details.fields`에 몇 번째 문장인지). 문장을 지우려면 배열에서 빼면 된다
5. **시간 상한:** 2시간

## 결정

- 11/22 사용자: "기존 계약대로 완성한 뒤 개선안은 FE와 토의". 계약 문서(v0.6.5)와 응답 모양을 바꾸지 않는다. 계획 표의 "계약 v0.7.2"는 뺐다. 계약 테스트 T09-a~d는 이 지시로 진행
- 정할 것 1~5는 추천안대로(모두 계약 문장의 해석 범위): ① 글이 바뀐 문장은 같은 요청에 `confirmed: true`가 있을 때만 `true` ② 다시 분석해도 `version`은 이어서 +1 ③ `PUT`으로 한 번이라도 저장한 초안 = `DRAFT_HAS_EDITS` ④ 없는 `sentenceId`·중복·빈 글은 `400 VALIDATION_ERROR`(계약 1.1 "필드 형식·필수값 오류") ⑤ 2시간
- 문장 ID는 UUID(계약 1절 "ID 전부 UUID", 예시의 `s1`은 줄임)
- `summary.sentencesNeedingCheck` = `needsCheck: true` 문장 수(확인 여부와 무관). 확인 안 한 수는 `draft.unconfirmedCount`
- "저장한 적 있음"은 `drafts.edited_at`(ERD v1.3)으로 판단. `utc_now()`가 초 단위라 `updated_at`·`created_at` 비교로는 구분이 안 된다

## 결과

- 구현: `app/models/draft.py`(ERD v1.3 `edited_at`), `app/services/drafts.py`(확인 필요 규칙·GET·PUT·다시 분석 판단), `app/api/draft.py`, `app/schemas/draft.py`. 가짜 분석기가 초안 문장을 낸다(GOODS 3문장·2묶음, UNEXPECTED 5문장·3묶음, 그 밖 2문장). 결과 API의 `draft`·`summary.sentencesNeedingCheck` 채움. `DRAFT_HAS_EDITS` 연결. 샘플 서류는 `attachment`
- 계약 문서·응답 모양 변경 없음(v0.6.5 그대로). ERD v1.3(`drafts.edited_at`)
- 테스트: `tests/test_t09_draft.py`(T09-a~d + 동작 확인 7개). T08 테스트의 `draft is None` 단정을 `is not None`으로. `uv run python -m pytest -q` → 99 passed(3회), `uv run ruff check .` 통과
- 미검증: 실제 서버·FE 화면 연동(탭 C·6번 확인창), Postgres에서 `drafts` 테이블 생성
