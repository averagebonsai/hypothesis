# Production Dockerfile for Hypothesis FastAPI Simulation Backend
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency specifications first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY src/ ./src/
COPY experiment_requests/ ./experiment_requests/

# Install the project packages
RUN uv pip install --no-deps -e .

EXPOSE 8000

# Healthcheck for container orchestrators
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT}/api/health || exit 1

# Start Uvicorn bound to Render's dynamic $PORT
CMD ["sh", "-c", "uv run uvicorn web.app:app --host 0.0.0.0 --port ${PORT}"]
