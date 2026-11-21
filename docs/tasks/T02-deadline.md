# T02 D-day 계산

- 단계: 1단계 사건·증빙 · 예정: 11/21 밤 · 상태: 완료 · 이슈: #4 · PR: #23

## 범위

- DB 없이 동작하는 함수: 공고일·오늘 날짜 → `deadline` 객체(계약 4.4, 5절)
- 오늘 날짜는 한국 시간 기준, 테스트에서 주입 가능하게

## 제외

- 공휴일 순연(계약 5절 4번, P0 제외)

## 완료 조건

- 계약 테스트 1·2·3 통과

## 구현 계획

### 파일

- `app/schemas/deadline.py`: `Deadline` 응답 모델(CamelModel) — `state`, `deadlineDate`, `daysLeft`, `label`, `basis`, `notice`(계약 4.4)
- `app/services/deadline.py`
  - `compute_deadline(public_notice_date: date | None, today: date) -> Deadline`: 순수 함수, DB·시계 없음
  - `today_kst() -> date`: 한국 날짜. 한국은 서머타임이 없어 고정 UTC+9로 계산한다(Windows에서 `zoneinfo`가 `tzdata` 패키지를 따로 요구하는 문제도 피함)
- `tests/test_t02_deadline.py`
- API 연결은 하지 않는다. T03 사건 응답에서 이 함수를 부른다

### 계산 (계약 5절 그대로)

1. 공고일 없음 → `state=UNKNOWN_NOTICE_DATE`, `deadlineDate=null`, `daysLeft=null`, `label="공고일 확인 필요"`, `basis=null`
2. 시작일 `S = 공고일 + 1일`. `S`의 2개월 뒤 같은 날짜가 있으면 그 전날, 없으면 그 달 말일이 마지막 날
3. `daysLeft = 마지막 날 − 오늘`. `label`: 양수 `D-n`, 0 `D-DAY`, 음수 `기한 지남`
4. `state`: `daysLeft > 7` `OK`, `0~7` `URGENT`, 음수 `EXPIRED`
5. `basis`: `"공고일(2026-11-17) 기준 2개월, 참고 계산"`
6. `notice`: 공고일 유무와 관계없이 항상 `"정확한 기한은 계좌가 있는 은행에 꼭 확인하세요."`(공휴일 순연을 하지 않으므로, 계약 5절 4번)

### 테스트 (계약 테스트 1·2·3, 11/21 목록 승인됨)

| # | 입력 | 기대 |
|---|---|---|
| 1 | 공고일 없음 | `UNKNOWN_NOTICE_DATE`, `deadlineDate`·`daysLeft`·`basis` null, `label` "공고일 확인 필요" |
| 2 | 공고일 2026-11-17 / 11-30 / 12-30 / 2027-12-29 / 2027-12-30 | 2027-01-17 / 2027-01-31 / 2027-02-28(평년) / 2028-02-29(윤년) / 2028-02-29(윤년) |
| 3 | 공고일 2026-11-17(마지막 날 2027-01-17), 오늘 1/9·1/10·1/17·1/18 | `D-8` `OK` / `D-7` `URGENT` / `D-DAY` `URGENT` / `기한 지남` `EXPIRED` |
| 3+ | 같은 결과의 JSON 키 | `state, deadlineDate, daysLeft, label, basis, notice`(camelCase), 날짜는 `"2027-01-17"` 문자열 |

### 정할 것

- 공고일이 없을 때 `basis`는 `null`, `notice`는 평소와 같은 문구로 둔다. 계약에 이 경우의 `basis`·`notice` 값이 적혀 있지 않아서 정한 것이다(FE는 `label`과 `notice`만 보여 주면 된다)

## 결정

- 11/21 구현 계획 승인. FE 합의 전이지만 서버 내부 계산이라 먼저 진행(사용자 확인)
- 11/21 공고일이 없으면 `basis`는 `null`, `notice`는 평소 문구(계약에 값이 없어 정함). FE 담당자에게 보낼 메시지에 한 줄 추가하기로 함

## 결과

- `uv run ruff check .` → All checks passed / `uv run ruff format --check .` → 통과
- `uv run python -m pytest -q` → 15 passed (T02 11개: 계약 테스트 1 1개, 2 5개, 3 4개, JSON 모양 1개 + T01 4개)
- CI: PR #23에서 GitHub Actions `test` 통과(10초)
