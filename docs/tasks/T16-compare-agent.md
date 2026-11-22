# T16 대조 에이전트

- 단계: 3단계 실제 AI · 예정: 11/22 낮(실제 Claude 첫 실행 목표 13:00) · 상태: 완료 · 이슈: #18 · PR: 없음

## 범위

- Claude Messages API 도구 루프(`docs/agent-design.md` 2.4): `get_transactions`, `get_evidence_regions`
- 구조화 출력: findings, AI 권장 자료
- `steps` 기록, 거절·시간 초과 처리
- 재사용 시 출처를 커밋 메시지에 기록(corebank `llm/claude.py` 재시도·비용 등)
- `agent/llm.py`: corebank `llm/claude.py`·`port.py`의 단가·비용 계산, 마감 안 재시도, 도구 결과 상한, `Usage`·`Deadline`을 가져온다(`docs/agent-design.md` 5·6절). 자동 캐시, thinking 파라미터 생략, effort `low` 명시, 서버측 fallback
- 도구 인자에 `reason`(조회 이유) 필수 → step `TOOL_CALL` `summary`로 표시
- 대조 결과 검증: 인용 원문 대조, 이 사건 소속·이번에 조회한 거래 ID만 인정(`docs/agent-design.md` 2.4)
- LangGraph 등 프레임워크는 쓰지 않는다(11/21 결정)
- 고정 목록(라벨)을 프롬프트에 넣고 같은 서류를 권하지 말라고 지시한다. 코드는 서류 종류로 거르지 않고 최대 3개로 자른다. 고정 항목과 같은 `docType`으로는 자동 충족되지 않는다(T08, 계약 v0.6.5 4.8)

## 제외

- 초안(T17)

## 완료 조건

- test01·test02 샘플로 실제 분석 → 결과 화면 데이터가 나옴

## 구현 계획

(11/22 작성, 사용자 확인 "진행")

### 바꿀 파일

| 파일 | 내용 |
|---|---|
| `pyproject.toml`·`uv.lock` | `uv add anthropic`(1.x) |
| `app/config.py` | `anthropic_model`(기본 `claude-opus-5-5`), `anthropic_effort`(기본 `low`) |
| `app/agent/llm.py` (새) | 외부 AI 호출 유일한 곳. corebank에서 가져옴: 단가표·`cost_micro_usd`, 재시도 상수, 마감 안 재시도 `_create`, `_retry_after`, `_tool_error`·`_tool_content`, `_usage`, `Usage`, `Deadline`(점유 시계 뺌). 새로 씀: `ClaudeClient.turn()` 한 번 = 요청 1회(`client.beta.messages.create`, `max_retries=0`, 최상위 `cache_control` 자동 캐시, thinking 생략, `output_config={effort, format}`, `betas=[server-side-fallback-2026-07-01]`·`fallbacks="default"`). `refusal`·`max_tokens` → `AgentRefused`(거절 분류 `stop_details.category`는 로그), 마감 → `AgentTimeout`. 사용자 글·도구 결과는 `MaskedText`만 받고 아니면 `TypeError` |
| `app/agent/masking.py` | `seal_payload(obj) -> MaskedText`: 딕셔너리를 JSON으로 묶되 글자 값은 `MaskedText`이거나 코드가 만든 칸(`evidenceId`·`docType`·`transactionId`·`occurredAt`·`direction` 등)만 허용. 첫 메시지·도구 결과를 이걸로 만든다(원칙 4를 코드로 보장) |
| `app/agent/compare.py` (새) | `ClaudeAnalyzer`: ② 대조 도구 루프. 도구 2개(`get_transactions`, `get_evidence_regions`, `reason` 필수, `strict`). 첫 메시지 = 가린 사연 + 사용자가 말한 입금(유형·금액·날짜) + 서류 목록(`evidenceId`, 종류, 쪽 수, 앞 5줄) + 고정 체크리스트 라벨(같은 서류 권하지 말라고). 상한: 도구 8회·결과 60,000자, 요청 최대 10번. 넘으면 "지금까지 본 자료로 답하라" 오류 결과. 도구마다 step `TOOL_CALL`(summary = reason + " → N건"), 결과 뒤 `FINDING`·`CONFLICT` step. 프롬프트는 한국어로 새로 씀(판정·가능성 문장 쓰지 말라, 금액·날짜 계산하지 말라) |
| `app/agent/verify.py` (새) | 저장 전 코드 검증: ① `transactionId`가 이번 실행에서 도구가 실제로 돌려준 것인지(아니면 근거 빼고 step `VERIFY`) ② `evidenceId`·`regionIndex`가 이 사건 서류의 실제 줄인지(아니면 뺌), `page`는 AI가 아니라 그 줄에서 코드가 채움 ③ 글자 수 상한으로 자름. 인용 대조(`verified`)와 근거 없는 MATCH→UNKNOWN은 지금처럼 `services/results.py`가 한다 |
| `app/agent/output.py` | `AnalysisOutput`에 `model`, `usage`(토큰·비용) 칸 |
| `app/agent/runner.py` | `select_analyzer("claude")` → `ClaudeAnalyzer` |
| `app/services/analysis.py` | 실행 끝에 `analysis_runs.model`·`prompt_version`, `usage_events` 토큰·비용 채움 |

출력 스키마(`output_config.format`): agent-design 2.4 그대로. `evidenceId`·`transactionId`는 이 사건 값만 `enum`으로 묶는다(다른 사건 ID는 형식상 못 냄). 판정 필드(해제 가능성, 수용 여부 등)는 없다.

### 테스트 (API를 부르지 않는 가짜 클라이언트로)

계약 관련(승인 필요):
- **T16-a 판정 필드 부재**: 출력 스키마의 모든 키가 허용 목록 안에 있다(`possibility`·`verdict`·`risk` 같은 키 없음)
- **T16-b 사건 간 근거 교차 차단**: AI가 도구가 돌려주지 않은 거래 ID나 다른 사건 서류를 근거로 대면 그 근거가 빠지고, 남은 자료 근거가 없으면 `MATCH`가 `UNKNOWN`이 된다(결과 API까지 확인)

그 밖(바로 씀): 도구 `reason`이 `TOOL_CALL` step에 남음 / 9번째 도구 호출은 오류 결과 / `refusal` → `AGENT_REFUSED` / `MaskedText` 아닌 글은 `llm.py`가 거부 / 비용 계산 / `page`를 코드가 채움

### 실제 확인(수동, 비용 듦)
- Docker OCR 이미지(`proofy-ocr-check`)에서 `AGENT_LLM=claude`로 test01·test02 실제 분석 1회씩 → 결과 API에 대조 항목·근거·AI 권장 자료가 나오는지, test01에 채팅 12번 줄 금액 어긋남(CONFLICT)이 나오는지. 예상 비용 건당 $0.1 안팎, 시간 30~60초

### 정할 것
1. claude 모드의 ③ 초안 단계(T17 전까지): **추천 A 초안 비움**(step "초안은 준비 중"). 가짜 초안을 쓰면 문장이 가짜 대조 항목 번호를 가리켜 실제 대조 결과와 엉뚱하게 연결된다. T17이 바로 다음 작업
2. AI에 주는 거래 ID: **추천 `t1`·`t2` 키 그대로**(저장 전이라 DB ID가 없음, 짧아 토큰 절약)
3. 거절·시간 초과 시 샘플 대체 결과: **T11에서**. T16은 `AGENT_REFUSED`·`AGENT_TIMEOUT`로 실패 처리만
4. 실제 확인 2회 실행(약 $0.2) 진행해도 되는지

## 결정

11/22 사용자 "진행": 정할 것 1~4 추천안대로.

1. claude 모드 ③ 초안은 T17 전까지 비운다(step `DRAFT` "준비 중")
2. AI에 주는 거래 ID는 `t1`·`t2` 키
3. 거절·시간 초과 시 샘플 대체 결과는 T11. T16은 `AGENT_REFUSED`·`AGENT_TIMEOUT` 실패만
4. 실제 확인 2회 진행

구현 중 바꾼 것:
- 계획의 "`evidenceId`·`transactionId`를 스키마 `enum`으로 묶기"는 하지 않았다. 구조화 출력은 새 스키마마다
  첫 요청에 컴파일 시간이 들고 같은 스키마는 24시간 캐시되는데, 사건마다 ID가 달라 매번 새 스키마가 된다.
  같은 사건·조회한 거래 확인은 `verify.py`가 코드로 한다(T16-b)
- 가린 글 보장: `masking.seal_payload`(글자 값은 `MaskedText` 또는 코드 값 칸만), `mask_regions`가
  `maskedText`를 `MaskedText`로 두고 거래상대 칸도 `masked_part`로 타입을 잇는다
- 실패한 실행도 비용을 남긴다(runner가 오류에 출력을 붙여 서비스가 `usage_events`에 기록)
- corebank에서 가져온 상수 중 요청 시간 제한 120→90초, 시도 6→4회, 호출 전 여유 20→10초(이 실행 마감이
  150초라서). 모르는 모델 단가는 Opus 대신 더 비싼 값(10/50)으로 센다. Sonnet 5.5 캐시 읽기 단가 0.1로 고침
- 테스트는 실제 API를 부르지 않는다: `tests/conftest.py`가 `anthropic.Anthropic` 생성을 막고,
  `tests/fake_claude.py` 가짜 SDK로 도구 루프를 돌린다. T13·T14·T15의 claude 모드 테스트도 가짜를 쓴다

## 결과

- `app/agent/llm.py`(외부 AI 호출 유일한 곳), `compare.py`(도구 2개·루프·프롬프트 `t16-v1`), `verify.py`(후검증),
  `masking.seal_payload`, `runner.select_analyzer("claude")`, `services/analysis.py` 모델·토큰·비용 기록.
  의존성 `anthropic` 2.12.0
- 테스트: `uv run python -m pytest -q` 147 passed·2 skipped, `uv run ruff check .` 통과.
  T16-a·T16-b(계약), 도구 reason step·요청 설정·AI 권장 항목·비용 기록, 도구 9번째 오류, 거절 시 실패+비용 기록,
  `MaskedText` 아닌 글 거부, 쪽 번호 코드가 채움, T14에 "AI에 보낸 글에 원래 이름·번호 없음" 추가
- 실제 Claude 확인(11/22, Docker `proofy-ocr-check`, `claude-opus-5-5` effort low):
  - test01 GOODS: 성공 39.9초, 도구 3회, 입력 11,378·출력 1,832 토큰, $0.072. 대조 4개(일치 2·어긋남 1·사연에만
    1). 어긋남 = 대화 12번 줄 "3개 12만원에 할게요"(AMOUNT), 모든 인용 `verified: true`. AI 권장 "택배 송장
    또는 배송 조회 내역"(SHIPPING)
  - test02 UNEXPECTED: 성공 22.3초, 도구 2회, 입력 9,830·출력 1,712 토큰, $0.062. 대조 5개(일치 2·어긋남 1·사연에만
    2). 협박 문자 3번 줄 일치. 어긋남 = 사연 "11월 11일" vs 거래내역 입금 2026-11-12(DATE) — 가짜 분석과
    같은 의도된 장면(계약 4.3.1)
  - AI 권장 항목: test02는 0개(통지서·피해 신고 기록은 고정 항목에 있어 권하지 않음)
- 남은 것: 배포 서버 `AGENT_LLM=claude` 전환 전 Render $7(무료 서버 OCR 82초 + 대조 30~40초면 150초 마감에
  가까움). Claude 크레딧 차감은 Console Billing으로 확인

