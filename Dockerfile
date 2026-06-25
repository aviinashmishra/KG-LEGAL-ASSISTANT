FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps (build tools for any wheels that need them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# build the graph + indexes at image build (optional; also runs at startup)
RUN python scripts/ingest_seed.py || true

# Cloud platforms (Render, Railway, Fly, Heroku) inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1

# shell form so ${PORT} is expanded at runtime
CMD uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
