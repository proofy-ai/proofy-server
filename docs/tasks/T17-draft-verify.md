# T17 초안 작성 + 후검증

- 단계: 3단계 실제 AI · 예정: 11/22 오후 · 상태: 대기 · 이슈: #19 · PR: 없음

## 범위

- Claude 1회 호출로 초안 문장 + 근거 번호
- 후검증: 인용 원문 대조, 이번 실행에서 조회한 거래 ID만 인정, 같은 사건 소속 확인, 문장 속 숫자 대조, 판정성 표현
- 실패 문장은 지우지 않고 확인 필요
- 초안 문장마다 `section`(입금 경위 → 가담하지 않았다는 설명 → 피해 경위, 계약 v0.5 `DraftSection`)
- `NUMBER_MISMATCH`·`JUDGMENT_EXPRESSION` 문장만 AI가 1회 고쳐 쓰고 재검증, 또 걸리면 원래 문장 + 확인 필요(`docs/agent-design.md` 2.6). step `VERIFY`
- 방식 참고: corebank `worker.py` 인용 대조, DonWorry `narrative.py` 근거 번호 enum·숫자 검사(코드는 새로 작성)
- 인용 대조 기준은 마스킹한 글: 서류는 `regions_json[].maskedText`, 사연은 `masked_narrative`(ERD v1.1 3.7)

## 제외

- 없음

## 완료 조건

- 사건 간 근거 교차 차단·인용 검증 계약 테스트 통과(목록은 구현 계획에서 승인)

## 구현 계획

(11/22 작성, 확인 대기)

### 흐름 (`ClaudeAnalyzer.draft`, 대조와 같은 `ClaudeClient`라 비용이 이어서 쌓임)
1. **초안 1회 호출**(도구 없음): 검증을 거친 대조 항목을 번호(0부터)로 준다. 항목마다 주장·상태·설명·어긋남과
   근거 요약(인용, 거래 날짜·금액·가린 거래상대). 가린 사연, 입금 유형, 올린 서류 종류도 준다.
   출력 `sentences[] = {section, text, findingIndexes[]}`, `findingIndexes`는 **준 번호만 enum**(agent-design 2.5)
2. **코드 검사**(문장마다):
   - `NUMBER_MISMATCH`: 문장 속 금액·날짜가 연결한 항목의 근거(인용 글, 거래 행 금액·날짜)나 사용자가 입력한 입금
     금액·날짜에 없음. 금액·날짜 읽기는 `services/drafts.py`의 `amounts`·`month_days`를 `app/agent/numbers.py`로
     옮겨 같이 쓴다
   - `JUDGMENT_EXPRESSION`: "해제될", "풀릴", "확실", "틀림없", "승인", "받아들여질", "수용될", "문제없",
     "무조건", "가능성이 높", "유리", "불리" 등 목록
3. **1회 고쳐 쓰기**: 2에 걸린 문장이 있고 마감까지 40초 이상 남았으면 그 문장만 사유와 함께 다시 보내 고치게 한다
   (같은 `findingIndexes`). 다시 검사해 통과하면 고친 문장, 또 걸리면 **원래 문장 + 사유**(지우지 않음)
4. step: `DRAFT` "초안 문장 N개(입금 경위 a · 가담 안 함 b · 피해 경위 c)", `VERIFY` "근거와 다른 숫자 1개를 AI가
   고쳐 다시 확인했습니다" / "확인 필요로 남긴 문장 1개"

AI가 쓴 글(대조 항목 설명, 고쳐 쓸 문장)을 다시 보낼 때는 `mask_text`를 한 번 더 거쳐 `MaskedText`로 보낸다
(가린 글에서 나온 글이라 새 개인정보는 없지만, 원칙 4를 타입으로 지킨다).

### 확인 필요 사유 (저장할 때 `services/drafts.py`, 계약 순서대로 앞의 것 하나)
`CONFLICT` → `NO_SOURCE` → `QUOTE_NOT_FOUND`(연결한 항목에 원문에서 못 찾은 인용이 있음, 새로 추가) →
`NUMBER_MISMATCH`·`JUDGMENT_EXPRESSION`(AI 단계가 넘긴 사유, 새로 추가). `SOURCE_UNREAD`는 쓰지 않는다
(못 읽은 서류는 T16에서 근거가 될 수 없어 생길 일이 없음).

### 바꿀 파일
| 파일 | 내용 |
|---|---|
| `app/agent/drafting.py` (새) | 초안·고쳐 쓰기 스키마·프롬프트(`t17-v1`), 숫자·판정 표현 검사 |
| `app/agent/numbers.py` (새) | `amounts`·`month_days`(drafts.py에서 옮김) |
| `app/agent/compare.py` | `draft()`가 drafting을 부름, 비용 다시 기록 |
| `app/agent/output.py` | `DraftSentence.check_reason`(AI 단계 검사 사유) |
| `app/services/drafts.py`·`results.py` | `QUOTE_NOT_FOUND`, AI 단계 사유 반영, `FindingInfo`에 인용 못 찾음 여부 |

### 테스트 (가짜 Claude)
계약 관련(승인 필요):
- **T17-a 인용 검증**: 사연에 없는 인용을 근거로 단 항목에 연결된 문장은 `needsCheck`·`QUOTE_NOT_FOUND`
- **T17-b 근거 교차 차단(초안)**: 없는 항목 번호(다른 실행·범위 밖)를 단 문장은 그 연결이 빠지고 `NO_SOURCE`
- **T17-c 1회 고쳐 쓰기**: 근거에 없는 금액 문장 → 고친 문장이 통과하면 고친 문장(`needsCheck` 없음),
  또 틀리면 원래 문장 + `NUMBER_MISMATCH`. 판정 표현도 같은 방식(`JUDGMENT_EXPRESSION`)

그 밖(바로 씀): 숫자·판정 표현 검사 단위 테스트, 마감 40초 미만이면 고쳐 쓰지 않음, 묶음 순서

### 실제 확인
- test01·test02 각 1회(약 $0.2, 대조+초안). 초안 문장·확인 필요 표시, 전체 시간

### 정할 것
1. 초안 속 상대방 이름(AI는 `김*수`만 앎): **추천 프롬프트로 "거래처", "입금한 사람"처럼 관계로 쓰게 하고, 그래도
   남은 `김*수`는 그대로 둠**(사용자가 탭 C에서 고침). 서버가 원래 이름으로 되돌리는 안은 하지 않음
2. 별지 제4호 셋째 요구("증빙자료 내용"): **추천 코드 문장을 따로 만들지 않고**, 프롬프트에 올린 서류 종류를 주고
   입금 경위 마지막 문장에서 "거래내역서와 대화내역을 함께 제출합니다"처럼 쓰게 함
3. 시간: 로컬 예상 대조 40초 + 초안 15~20초(+고쳐 쓰기 10초). 배포(무료 서버 OCR 82초)에선 150초를 넘길 수
   있음 → **추천 지금은 마감 그대로, T19 리허설에서 $7 서버로 재고 필요하면 그때 조정**

## 결정

## 결과

