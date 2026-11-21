# T13 글자 추출

- 단계: 3단계 실제 AI · 예정: 11/22 오전~낮 · 상태: 진행 중 · 이슈: #15 · PR: 없음

## 범위

- 텍스트 PDF는 OCR 없이 추출, 이미지·스캔 PDF는 Tesseract OCR
- 줄 단위 영역 저장, 신뢰도 낮은 영역 수, 못 읽은 서류는 `FAILED`로 두고 계속
- 추출기는 인터페이스로(배포에서 OCR이 막히면 교체)
- 가져오는 코드: corebank `preprocess.py` 전체, `ocr.py`(Tesseract 실행·`parse_tsv` 등). 범위·바꿀 점은 `docs/agent-design.md` 6절. 커밋 메시지에 원본 파일·범위 기록
- 텍스트 PDF 추출(`pypdf`)은 새로 작성

## 제외

- 거래 행 추출(T15)

## 완료 조건

- T12 서류에서 글자가 나옴

## 구현 계획

### 할 일

| # | 내용 | 파일 |
|---|---|---|
| 1 | **corebank 코드 가져오기**(커밋을 따로 나누고 메시지에 원본·범위 기록). `preprocess.py` 전체(1~140행), `ocr.py`의 `detect_format`·`OcrError`·`OcrEngine`·`TesseractEngine`·`parse_tsv`·`_child_env`·`_binary`·`count_low_confidence`. 바꿀 점: 줄 길이 100, corebank 서버 계약 주석 제거, 프로그램 경로를 설정으로, 영역에 `page` 추가(ERD 3.3 `regions_json` 모양) | `app/agent/extract/preprocess.py`, `app/agent/extract/ocr.py` |
| 2 | **텍스트 PDF 추출(새로 작성).** `pypdf`로 쪽마다 글자를 뽑아 줄마다 영역 하나 `{index, page, text, bbox: null, confidence: null}`. 글자가 거의 없는 PDF(공백 빼고 20자 미만)는 스캔본으로 보고 OCR로 넘긴다 | `app/agent/extract/pdf_text.py` |
| 3 | **추출 입구.** 파일 하나 → `Extraction`(방식 `PDF_TEXT`·`OCR`, 영역, 전체 글, 흐린 줄 수, 실패 사유). 형식은 매직 바이트로 판단. 못 읽으면 예외를 올리지 않고 실패 결과를 돌려준다(그 서류만 `FAILED`, 분석은 계속) | `app/agent/extract/__init__.py` |
| 4 | **분석 실행에 연결.** ① 단계에서 코드가 서류마다 추출하고 결과를 바로 DB에 저장: `extract_status` `PROCESSING`→`READY`/`FAILED`, `extract_method`, `extracted_text`, `regions_json`, `low_confidence_regions`, `extract_error`, `extracted_at`. 이미 `READY`인 서류는 다시 읽지 않는다(다시 분석이 빨라짐). 서류마다 step `OCR`("거래내역서_샘플.pdf 읽기" → "글자가 든 PDF라 OCR 없이 읽었습니다. 12줄", 실패면 `FAILED` 상태와 사유). 파일 내용 읽기·저장은 서비스 계층이 맡고, runner는 넘겨받은 저장소로만 접근한다(지금 step 기록과 같은 방식) | `app/agent/runner.py`, `app/services/analysis.py` |
| 5 | 설정: `TESSERACT_CMD`·`PDFTOPPM_CMD`(비우면 PATH에서 찾음), `OCR_LANG=kor+eng`. README 환경변수 표, `.env.example` | `app/config.py`, README |
| 6 | `pillow`·`pypdf`를 실행 의존성으로 옮김 | `pyproject.toml`, `uv.lock` |
| 7 | 확인용 명령: `uv run python -m app.agent.extract 파일` → 방식과 줄을 출력(T12 서류 확인, 배포 뒤 점검) | `app/agent/extract/__main__.py` |

### 테스트(계약 테스트 아님. 계약의 `extractStatus`·`lowConfidenceRegions` 값이 채워지는지만 봄)

| # | 내용 |
|---|---|
| a | T12 거래내역서 PDF 두 개가 `PDF_TEXT`로 읽히고, 거래 행이 한 줄 = 한 영역(`2026-11-08 … 150,000 … 김민수`), 흐린 줄 0 |
| b | 글자 없는 PDF(이미지만)는 OCR 경로로 가고, Tesseract가 없으면 `FAILED`와 사유. 예외로 분석이 멈추지 않음 |
| c | `parse_tsv`: 고정 TSV 예시로 줄 묶기·신뢰도 평균·흐린 줄 수 |
| d | `AGENT_LLM=claude`로 샘플 사건을 분석하면 서류 목록 API에서 PDF는 `READY`·`lowConfidenceRegions: 0`, PNG는 Tesseract 유무에 따라 `READY` 또는 `FAILED`. 결과 `unreadEvidence`에 `FAILED` 서류가 나옴 |
| e | Tesseract가 있을 때만(없으면 건너뜀): `chat.png`에서 "12만원", `threat_message.png`에서 "신고 취하" 글자가 나옴 |

### 정할 것

1. **가짜 분석(`AGENT_LLM=scripted`)에서는 글자를 읽지 않는다**(추천). 실제 추출은 `claude`일 때만 돈다. 가짜 분석은 테스트·FE 연동·AI 실패 대비 결과에 쓰는데, Tesseract가 없는 PC에서 돌리면 PNG가 `FAILED`가 되어 "읽지 못한 서류"가 생기고 정해 둔 결과와 어긋나기 때문이다. Claude 분석기는 T16에서 붙으므로, 그 전에는 `AGENT_LLM=claude`로 두면 **추출은 실제, 대조·초안은 가짜**로 돈다(T13 확인용으로 좋음)
2. **언제 읽나: 분석 시작 때**(추천, `docs/agent-design.md` ① 단계 그대로). 업로드 때 읽으면 3번 화면에서 상태를 미리 보일 수 있지만 스레드가 하나 더 생긴다
3. **텍스트 PDF의 `bbox`는 비워 둔다**(추천). 화면이 영역 위치를 쓰지 않고(계약에 없음), 인용 대조는 글자만 본다
4. **PNG OCR 확인 방법.** 이 PC에 Tesseract가 없다. (가) **Docker Desktop을 켜고 컨테이너에서 Tesseract로 T12 PNG를 읽어 본다**(추천, 배포와 같은 리눅스 환경이고 레포에는 아무것도 안 남김) (나) Windows에 Tesseract 설치(winget, 한글 데이터 따로, 애플리케이션 제어에 막힐 수 있음) (다) 배포(T18)까지 미룸. 대화 PNG의 "3개 12만원에 할게요"가 test01 금액 불일치 장면의 근거라 늦게 확인하면 위험하다
5. **시간 상한:** 2시간

## 결정

- 11/22 사용자 "진행하자": 정할 것 1~5 추천안대로. ① 실제 추출은 `AGENT_LLM=claude`일 때만 ② 분석 시작 때 읽음 ③ 텍스트 PDF `bbox` 비움 ④ PNG OCR은 Docker Desktop 컨테이너에서 확인(레포에 남기지 않음) ⑤ 2시간

## 결과

- 구조: `app/agent/extract/`(`__init__` 입구·`Extraction`, `pdf_text` 새로 작성, `ocr`·`preprocess` corebank에서 가져옴, `__main__` 확인 명령). runner ① 단계가 `AGENT_LLM=claude`일 때 서류마다 읽고 `DbEvidenceStore`로 바로 저장. 이미 `READY`면 다시 쓰고, 가짜 분석기는 실제 추출 step이 있으면 흉내 step을 남기지 않음
- `AnalysisOutput.extractions`(evidenceId → 추출 결과)에 담아 다음 단계(T14 마스킹, T15 거래 행, T16 대조)가 쓴다
- **Docker 컨테이너(python:3.12-slim + tesseract 5.5.0 kor + poppler) 확인(11/22):** 대화 PNG 18줄, 12번 줄 = "3개 12만원에 할게요"(0.94) / 협박 문자 7줄, 3번 줄 = "20만 원 보내면 신고 취하해 줄게"(0.95) / 사업자등록증명 15줄. 전처리 덕에 전처리 없는 tesseract보다 오인식이 적음(빼·샘플로 정확). 빨간 띠의 흰 글씨("합성 데이터")는 일부 틀리게 읽힘(대조에 안 쓰는 줄). 시간: 대화 4.2초, 사업자등록증명 2.1초, 협박 2.9초, PDF 0.0초
- 테스트 `tests/test_t13_extraction.py`(계획 a~e): 이 PC `uv run python -m pytest -q` 110 passed·2 skipped(OCR 테스트, Tesseract 없음), 컨테이너에서 112 passed. `uv run ruff check .` 통과
- 미검증: 배포 환경(Render)의 OCR 속도, 휴대폰 사진(기울기·조명) 실물

