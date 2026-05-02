# Stage 1: install external dependencies (cached as long as pyproject.toml is unchanged)
FROM python:3.12-slim AS deps

WORKDIR /build
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN mkdir -p src/cmart && touch src/cmart/__init__.py
RUN uv sync --no-dev --no-install-project

# Stage 2: install the cmart package itself (invalidated when src changes)
FROM deps AS builder

COPY src/ ./src/
RUN uv sync --no-dev --no-editable

# Stage 3: minimal runtime image
FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY alembic.ini ./
COPY alembic/ ./alembic/

ENV PATH="/app/.venv/bin:$PATH"

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

# PORT is injected by Railway; default to 8080 for local Docker runs
CMD ["sh", "-c", "python -m uvicorn cmart.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
