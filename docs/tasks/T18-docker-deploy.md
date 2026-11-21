# T18 Docker·배포

- 단계: 4단계 배포·마무리 · 예정: 11/22 저녁 · 상태: 대기 · 이슈: #20 · PR: 없음

## 범위

- Dockerfile(Tesseract 한국어, poppler 포함)
- 배포 환경 결정과 배포, Postgres, 환경변수(키는 환경변수로만)
- FE 배포 주소 CORS 등록
- Alembic 도입: 배포 시점의 스키마를 첫 변경 파일로 만들고, 이후 스키마 변경은 변경 파일로 배포 DB에 반영. 서버 시작 시 `create_all` 대신 마이그레이션 적용
- 배포 DB에 증빙 파일이 들어가므로(`evidence_files`) 용량 확인. 서버 디스크에 영구 저장을 기대하지 않는다
- CORS: FE Cloudflare 고정 도메인만(미리보기 주소 제외), 개발·운영 서버 주소를 FE에 공유
- 환경변수: `IP_HASH_SECRET`, 한도 3종(T11), `CORS_ORIGINS`, `ANTHROPIC_API_KEY`

## 제외

- 없음

## 완료 조건

- 공개 주소에서 `/health` 응답, 체험 계정으로 처음부터 끝까지 동작
- 배포 DB에 Alembic 첫 변경 파일이 적용됨

## 구현 계획

(작업 시작 때 작성하고 확인받는다)

## 결정

## 결과

