# 📚 Proofy 문서 안내

어떤 문서를 언제 읽으면 되는지 정리했습니다. 프로젝트 소개와 실행 방법은 [루트 README](../README.md)에 있습니다.

---

## 처음 보는 분이라면

1. [`screen-flow.md`](screen-flow.md): 사용자가 어떤 화면을 어떤 순서로 지나가는지
2. [`agent-design-v2.md`](agent-design-v2.md): AI 에이전트가 무엇을 어떻게 하고, 무엇을 코드가 지키는지
3. [`architecture.md`](architecture.md): 코드 폴더가 각각 무엇을 맡고, 분석 한 번이 어떤 파일을 거치는지
4. [`proposals/v0.8-agent-interview.md`](proposals/v0.8-agent-interview.md): AI가 의견을 내고 질문하도록 바꾼 이유(인터뷰형 에이전트 제안서)

---

## 정본 문서 (구현과 다르면 구현을 고친다)

- 🔌 **[`contract.md`](contract.md) — FE–BE API 계약**
  - 엔드포인트, 요청·응답 필드, 오류 코드, D-day 계산 규칙
  - FE와 BE가 같이 보는 기준. 바꿀 때는 이 파일을 먼저 고치고 맨 아래 변경 이력에 적는다
- 🗄️ **[`erd.md`](erd.md) — 데이터 모델**
  - 테이블·컬럼, 관계도, 상태와 버전 규칙
  - 결정의 이유는 [`erd-review.md`](erd-review.md)
- 🤖 **[`agent-design-v2.md`](agent-design-v2.md) — AI 에이전트 설계**
  - 에이전트 4요소, 쓴 기법과 쓰지 않은 기법, 단계별 설계, 검증 규칙
  - v1([`agent-design.md`](agent-design.md))의 가져온 코드 목록과 세부 근거는 그대로 유효

---

## 목적별로 찾기

- **화면과 흐름이 궁금하다** → [`screen-flow.md`](screen-flow.md)
- **API 필드 이름·타입을 확인한다** → [`contract.md`](contract.md) 4절(엔드포인트), 2절(코드값)
- **오류 코드가 무슨 뜻인가** → [`contract.md`](contract.md) 1.1절
- **AI가 어디까지 정하고 어디서부터 코드가 정하나** → [`agent-design-v2.md`](agent-design-v2.md) 2절
- **이 기능의 코드가 어느 폴더·파일에 있나** → [`architecture.md`](architecture.md)
- **AI가 쓴 글을 어떻게 검증하나** → [`agent-design-v2.md`](agent-design-v2.md) 4.3·4.5절
- **DB에 무엇이 저장되나(개인정보 포함)** → [`erd.md`](erd.md) 1절 원칙, 3절 테이블
- **배포하거나 배포 서버를 다룬다** → [`deploy.md`](deploy.md)
- **법령 원문과 출처** → [`legal/README.md`](legal/README.md)
- **작업 진행 상태** → [`tasks/README.md`](tasks/README.md)

---

## 폴더 구성

- `contract.md` · `erd.md` · `erd-review.md`: API와 데이터 정본
- `agent-design-v2.md` · `agent-design.md`: AI 에이전트 설계(v2가 정본)
- `screen-flow.md`: 화면과 사용자 흐름
- `architecture.md`: 코드 구조(폴더별 역할, 호출 방향)
- `deploy.md`: 배포 안내(Render + Neon)
- `legal/`: 법령 원문과 출처
- `proposals/`: 큰 변경을 정하기 전에 쓴 제안서
- `tasks/`: 작업(T00~T25)별 범위·구현 계획·결정·결과. 진행 상태는 `tasks/README.md`
