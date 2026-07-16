FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INJECTGUARD_DISABLE_TRANSFORMERS=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --extra server --no-dev

EXPOSE 10000

CMD ["sh", "-c", ".venv/bin/uvicorn injectguard.server:app --host 0.0.0.0 --port ${PORT:-10000}"]
