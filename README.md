# CMART

**API-first AI support agent for B2B SaaS.** CMART autonomously resolves customer support queries using retrieval-augmented generation, with explicit risk management through four confidence signals and rule-based routing to answer, clarify, or escalate — never guesses.

---

## How It Works

Every query runs a 7-stage pipeline:

```
Query → Analysis → Retrieval → Generation → Validation → Decision → Response
```

| Stage | What it does |
|---|---|
| 1. Intake | Validates request, resolves session context |
| 2. Analysis | LLM classifies Query Clarity (QC): `CLEAR`, `AMBIGUOUS`, `INCOMPLETE` |
| 3. Retrieval | Pinecone vector search → top-k docs, computes Retrieval Strength (RS) |
| 4. Generation | LLM generates grounded answer with inline source citations |
| 5. Validation | LLM checks Grounding (GC) and Source Agreement (SA) in parallel |
| 6. Decision | Rule-based engine routes: `ANSWER`, `CLARIFY`, or `ESCALATE` |
| 7. Response | Shapes response payload, manages session state |

### Decision Engine (Rule-Based, No ML)

| Decision | Condition | Reason Code |
|---|---|---|
| `ANSWER` | RS=STRONG + GC=FULLY_SUPPORTED + QC=CLEAR + SA=AGREES | `HIGH_CONFIDENCE` |
| `CLARIFY` | QC=AMBIGUOUS or INCOMPLETE, or GC=PARTIALLY_SUPPORTED | `DEFAULT_SAFE` |
| `ESCALATE` | GC=NOT_SUPPORTED | `LOW_GROUNDING` |
| `ESCALATE` | SA=CONFLICT | `SOURCE_CONFLICT` |
| `ESCALATE` | RS=WEAK | `LOW_RETRIEVAL` |
| `ESCALATE` | Clarification rounds ≥ 2 | `CLARIFICATION_LIMIT_REACHED` |
| `ESCALATE` | Pinecone exception | `RETRIEVAL_FAILURE` |

**Core principle:** a wrong answer is worse than no answer. Default to `CLARIFY` on mixed signals, never fabricate.

---

## Tech Stack

```
Runtime:       Python 3.12
Framework:     FastAPI 0.111 + Uvicorn
LLM:           Google Gemini Flash 2.5 (langchain-google-genai)
Embeddings:    OpenAI text-embedding-3-small
Vector DB:     Pinecone (serverless, per-account namespace isolation)
Session Store: Redis 7.2 (TTL=30min, atomic round counters)
Database:      PostgreSQL 16 (SQLAlchemy 2.x async + asyncpg + Alembic)
Config:        pydantic-settings (.env)
Logging:       structlog (JSON)
Testing:       pytest + pytest-asyncio + httpx
Package mgr:   uv
Linting:       ruff + mypy (strict)
Deploy:        Railway
```

---

## Quickstart (Local)

**Prerequisites:** Docker Desktop, `uv`

```bash
# Clone and enter
git clone https://github.com/anubhavbansal727/cmart-api.git
cd cmart-api

# Configure environment
cp .env.example .env
# Fill in: GEMINI_API_KEY, OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME

# Start postgres + redis
docker compose up postgres redis -d

# Install dependencies
uv sync

# Run migrations
uv run python -m alembic upgrade head

# Provision an account + API key
uv run python scripts/create_account.py --name "My Account"

# Start the API
uv run python -m uvicorn cmart.main:app --reload --port 8000
```

API is live at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

---

## API Reference

All requests require `Authorization: Bearer <api-key>`.

### POST `/query`

Submit a support query. Returns one of three decision types.

**Request:**
```json
{
  "query": "How do I reset my password?",
  "user_id": "user_123",
  "session_id": null,
  "metadata": { "product_area": "auth" }
}
```

**Response — `answer`:**
```json
{
  "decision": "answer",
  "answer": "To reset your password, go to Settings → Security and click 'Reset Password'. [Source: Account Security Guide]",
  "sources": [{ "doc_id": "doc_001", "title": "Account Security Guide", "score": 0.63 }],
  "reason": "HIGH_CONFIDENCE",
  "latency_ms": 2840
}
```

**Response — `clarify`:**
```json
{
  "decision": "clarify",
  "clarification_question": "Which product or service are you trying to log into?",
  "session_id": "b019074f-2185-430c-b7c1-367a4c620d8a",
  "reason": "DEFAULT_SAFE",
  "latency_ms": 1120
}
```

Echo `session_id` back in follow-up requests. Pipeline escalates automatically after 2 clarification rounds.

**Response — `escalate`:**
```json
{
  "decision": "escalate",
  "escalation_context": {
    "reason": "LOW_GROUNDING",
    "signals": { "rs": "STRONG", "qc": "CLEAR", "gc": "NOT_SUPPORTED", "sa": "AGREES" },
    "query": "...",
    "retrieved_docs": [...]
  },
  "reason": "LOW_GROUNDING",
  "latency_ms": 3200
}
```

### POST `/ingest`

Ingest knowledge base documents by URL. CMART fetches the page, converts HTML to plain text, and chunks it for vector storage.

```json
{
  "documents": [
    {
      "doc_id": "doc_001",
      "title": "Account Security Guide",
      "url": "https://help.yourproduct.com/account-security"
    }
  ]
}
```

`source_url` defaults to `url` for attribution. Override it explicitly if the canonical URL differs from the fetch URL. Up to 50 documents per request. Per-document failures do not abort the batch — check the `failed` list in the response.

### DELETE `/ingest/{doc_id}`

Remove a document from the vector store and mark it deleted in DocMeta.

### POST `/feedback`

Submit agent feedback on a query decision.

```json
{
  "query_log_id": "...",
  "rating": "correct",
  "notes": "Answer was accurate and cited the right doc."
}
```

### GET `/health`

Returns `{ "status": "ok", "db": true, "redis": true }`. Runs live DB `SELECT 1` and Redis `PING` per call.

---

## Environment Variables

```bash
# LLM + Embeddings
GEMINI_API_KEY=...
OPENAI_API_KEY=...

# Vector store
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=cmart
PINECONE_ENVIRONMENT=us-east-1
PINECONE_VECTOR_DIM=1536

# Persistence
DATABASE_URL=postgresql+asyncpg://cmart:cmart@localhost:5432/cmart
REDIS_URL=redis://localhost:6379

# Retrieval thresholds (tuned for text-embedding-3-small + Pinecone cosine)
RS_STRONG_THRESHOLD=0.60
RS_MODERATE_THRESHOLD=0.45

# Session
SESSION_TTL_SECONDS=1800
MAX_CLARIFY_ROUNDS=2

# Rate limiting
RATE_LIMIT_PER_MINUTE=100
```

---

## Development

```bash
# Run tests
uv run pytest

# Type check
uv run mypy src/

# Lint
uv run ruff check src/ tests/

# Load test (against staging)
uv run locust -f tests/load/locustfile.py --host https://<host>
```

CI runs on every push: ruff → mypy → pytest (GitHub Actions).

---

## Project Structure

```
src/cmart/
├── api/             # FastAPI app, routes (/query, /ingest, /feedback, /health), middleware
├── auth/            # API key auth (Bearer token, hmac.compare_digest)
├── db/              # SQLAlchemy models, Alembic migrations, repositories
├── pipeline/        # Stages 1–7 (one file per stage) + orchestrator
├── rate_limit/      # Redis sliding-window rate limiter
├── schemas/         # Pydantic DTOs (query, ingest, pipeline, feedback)
├── services/        # LLM client (Gemini), vector store (Pinecone), chunker, session store, url_fetcher
└── utils/           # Errors, timing

tests/
├── unit/            # Pipeline stages, services
├── integration/     # Endpoint tests (ingest, query)
├── evaluation/      # Golden dataset for decision accuracy evaluation
└── load/            # Locust load test

scripts/
├── create_account.py           # Provision API key
└── test_namespace_isolation.py # Verify per-account Pinecone namespace isolation
```

---

## Deployment (Railway)

```bash
railway up
```

Pre-deploy command: `python -m alembic upgrade head`
Start command: `sh -c "python -m uvicorn cmart.main:app --host 0.0.0.0 --port ${PORT:-8080}"`

Set all env vars in Railway dashboard. Override RS thresholds to match your embedding model's cosine similarity range — default values assume `text-embedding-3-small` on Pinecone cosine (not the CLAUDE.md theoretical values).

---

## Confidence Signals

| Signal | Values |
|---|---|
| **Retrieval Strength (RS)** | `STRONG` (≥0.60), `MODERATE` (0.45–0.60), `WEAK` (<0.45) |
| **Grounding Check (GC)** | `FULLY_SUPPORTED`, `PARTIALLY_SUPPORTED`, `NOT_SUPPORTED` |
| **Query Clarity (QC)** | `CLEAR`, `AMBIGUOUS`, `INCOMPLETE` |
| **Source Agreement (SA)** | `AGREES`, `PARTIAL`, `CONFLICT` |

All four signals are logged for every query regardless of outcome. No single confidence score — each signal is independently observable and auditable.
