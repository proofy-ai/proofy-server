# Proofy 서버 배포 이미지(T18). 파이썬 3.12 + Tesseract(한국어)·poppler + 실행 의존성만.
# 키·DB 주소는 이미지에 넣지 않고 호스팅의 환경변수로 받는다(원칙 5).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# 그림·스캔 PDF 글자 인식(T13): tesseract + 한국어 데이터, PDF 쪽 이미지는 poppler(pdftoppm)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

WORKDIR /app
# 의존성 먼저(코드만 바뀌면 이 층은 캐시를 쓴다)
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app

RUN useradd --create-home --uid 10001 proofy
USER proofy
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
# 호스팅이 주는 PORT를 쓰고 없으면 8080. 작업자는 1개(분석 스레드·사건 잠금이 프로세스 1개 전제).
# 프록시 뒤라 실제 접속 IP는 X-Forwarded-For에서 읽는다(한도 계산, T11)
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
