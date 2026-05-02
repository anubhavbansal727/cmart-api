# CMART — Action Items

## Pre-Build (Do Before Writing Any Code)

- [x] Apply for Pinecone Startup Program — avoids 3-week inactivity pause during build phase
- [x] Create Neon account + provision a `cmart` database
- [x] Create Upstash account + provision a Redis database
- [x] Get Google AI Studio API key (Gemini Flash 2.5)
- [x] Create OpenAI account + add payment method (embeddings, ~$1–2/mo at MVP scale)
- [x] Create Pinecone account + create a serverless index (`cmart-index`, us-east-1)
- [x] Copy `.env.example` → `.env` and fill in all API keys
- [x] Fix GC label inconsistency — changed `PARTIAL` → `PARTIALLY_SUPPORTED` in PRD + all code

---

## Phase 1 — Foundation + Ingest + Retrieval ✅ COMPLETE

### Week 1–2: Skeleton ✅ Done
- [x] `pyproject.toml`, `.gitignore`, `.env.example`, `docker-compose.yml`, `Dockerfile`
- [x] `config.py` — all env vars + threshold constants
- [x] `main.py` — FastAPI app, lifespan hooks, `/health`, exception handlers
- [x] `db/models.py` — `Account`, `QueryLog`, `Feedback`, `DocMeta`
- [x] `db/engine.py`, `db/repositories/`
- [x] `api/middleware.py` — request ID, timing headers, structlog
- [x] `utils/errors.py`, `utils/timing.py`
- [x] Route stubs (`/query`, `/ingest`, `/feedback`) returning 501
- [x] `alembic/versions/0001_initial.py` — run `uv run alembic upgrade head` against live DB
- [x] `scripts/create_account.py` — CLI to provision accounts + API keys
- [x] `tests/conftest.py`, placeholder test files
- [x] `.github/workflows/ci.yml` — lint + test on push
- [ ] Confirm CI passes on GitHub (push to repo, check Actions tab)

### Week 3–4: Ingest Pipeline ✅ Done
- [x] `services/embeddings/base.py` + `services/embeddings/openai.py` — OpenAI text-embedding-3-small, batched, dimensions driven by `PINECONE_VECTOR_DIM` config
- [x] `services/vector_store/base.py` + `services/vector_store/pinecone.py` — upsert, query, delete; namespace = `str(account.id)`
- [x] **Namespace isolation verified** — all 4 checks passed against live Pinecone index with 2 separate accounts
- [x] `services/chunker.py` — html2text + `RecursiveCharacterTextSplitter` (512 chars, 64 overlap)
- [x] `POST /ingest` — chunk → embed → upsert → write `DocMeta`; per-doc error isolation; idempotent re-ingest
- [x] `DELETE /ingest/{doc_id}` — Pinecone delete + DB soft-delete
- [x] `auth/api_key.py` — Bearer token auth with `hmac.compare_digest`
- [x] `schemas/ingest.py` — `IngestRequest`, `IngestResponse`, `DeleteResponse`
- [x] `db/repositories/doc_meta.py` — includes `upsert_doc_meta()`
- [x] Unit tests: `tests/unit/services/test_chunker.py` (9 tests)
- [x] Integration tests: `tests/integration/test_ingest_endpoint.py` (7 tests)

### Week 5–6: Retrieval + Stub Query ✅ Done
- [x] `schemas/query.py` — `QueryRequest`, `QueryResponse`, `DecisionType`, `RetrievedDoc`
- [x] `schemas/pipeline.py` — `PipelineContext` + signal enums (`RSSignal`, `QCSignal`, `GCSignal`, `SASignal`), `RetrievalResult`
- [x] `pipeline/stage1_intake.py` — normalizes query
- [x] `pipeline/stage3_retrieval.py` — embed → Pinecone top-5 → RS signal from config thresholds
- [x] `pipeline/orchestrator.py` — sequences stage1 → stage3
- [x] `rate_limit/redis_limiter.py` — sliding window 100 req/min per account
- [x] `services/session_store.py` — Redis CRUD: create / get / increment_round / delete
- [x] `POST /query` — auth → rate limit → pipeline → response (decision stubbed as ANSWER)
- [x] **Phase 1 exit criteria verified** — ingest doc → query → top chunk returned with correct score + metadata

---

## Phase 2 — LLM Integration + Pipeline Stages 1–5 (Weeks 7–10)

### Before Week 7
- [ ] Write and review system prompts for all three LLM stages:
      - Stage 2: Query Clarity (CLEAR / AMBIGUOUS / INCOMPLETE)
      - Stage 4: Answer Generation (grounded only, inline `[Source: doc_title]` citations)
      - Stage 5a: Grounding Check (FULLY_SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED)
      - Stage 5b: Source Agreement (AGREES / PARTIAL / CONFLICT)
- [ ] Decide Pinecone plan tier — free (100k vectors) enough for 3 design partners, or upgrade to Starter ($70/mo)?

### Week 7–8: LLM Client + Analysis + Generation ✅ Done
- [x] `services/llm/base.py` + `services/llm/gemini.py` — `GeminiClient` (`ChatGoogleGenerativeAI`, `temperature=0`); Pydantic v2 / LangChain structured output compatibility fix applied
- [x] `pipeline/stage2_analysis.py` — QC via structured output; failure → AMBIGUOUS (safe default)
- [x] `pipeline/stage4_generation.py` — grounded generation, mandatory `[Source: doc_title]` citations
- [x] `pipeline/stage5_validation.py` — GC + SA via `asyncio.gather()`; failures → NOT_SUPPORTED / CONFLICT
- [x] Extend `schemas/pipeline.py` — `AnalysisResult`, `GroundingResult`, `AgreementResult` (Pydantic), `GenerationResult`, `ValidationResult` (dataclasses); all wired into `PipelineContext`
- [x] `pipeline/orchestrator.py` — sequences all 5 stages
- [x] `api/routes/query.py` — returns real LLM answer, reason = `AWAITING_DECISION_ENGINE`
- [x] Live test passed: all 4 signals computed, grounded answer with citations returned

### Week 9–10: Feedback + Background Logging ✅ Done
- [x] `schemas/feedback.py` — `FeedbackRequest`, `FeedbackResponse`
- [x] `api/routes/feedback.py` — `POST /feedback` fully wired; verifies query ownership
- [x] `db/repositories/feedback.py` — `insert_feedback()`, `get_by_query_id()`
- [x] Background query logging via `BackgroundTasks` — all 4 signals + latency written post-response
- [x] `schemas/pipeline.py` extended — `DecisionResult`, full `PipelineContext` with session state
- [x] `api/routes/query.py` — real ANSWER/CLARIFY/ESCALATE response shaping

---

## Phase 3 — Decision Engine + Session Loop + Hardening (Weeks 11–14)

### Before Week 11
- [ ] Confirm escalation handoff approach — JSON payload only (MVP default) vs. per-account webhook URL
- [ ] Finalize `EscalationContext` schema (session history, retrieved docs, all 4 signals, reason code, timestamp)

### Week 11–12: Decision Engine + Session Loop ✅ Done
- [x] `pipeline/stage6_decision.py` — full rule table, pure function, no I/O
- [x] `tests/unit/pipeline/test_stage6_decision.py` — 14 tests, 100% branch coverage
- [x] `pipeline/stage7_response.py` — session side-effects + `_build_escalation_context()`
- [x] Wire stages 6 + 7 into `pipeline/orchestrator.py`; loads `clarify_rounds` from Redis before stage 6
- [x] ESCALATE path verified live; CLARIFY + ANSWER paths confirmed by unit tests

### Week 13–14: Production Hardening ← current
- [x] Stage 3 error handling: Pinecone/embedding failure → `RETRIEVAL_FAILURE` reason
- [x] `GET /health`: live DB + Redis ping (replaced startup-flag approach)
- [x] `Dockerfile` fixed: 3-stage build; package properly installed; `$PORT` support
- [x] `railway.toml`: health check + restart policy
- [x] `tests/load/locustfile.py`: Locust load test scaffold
- [ ] `uv sync --all-extras` to install locust dev dep
- [ ] Deploy to Railway staging: provision Postgres + Redis + set env vars
- [ ] Verify Phase 3 exit criteria:
      - [ ] All 3 decision paths work end-to-end (blocked: Gemini free tier quota 20 req/day)
      - [ ] Session clarification escalates after 2 rounds (`CLARIFICATION_LIMIT_REACHED`)
      - [ ] Kill Redis mid-request → pipeline escalates gracefully (no 500)
      - [ ] Two accounts → Pinecone results fully isolated

---

## Phase 4 — Evaluation + Tuning (Ongoing)

- [ ] Collect 50+ real queries from design partners → label expected decisions → `tests/evaluation/golden_dataset.json`
- [ ] Build `tests/evaluation/run_eval.py` — decision accuracy, answer precision, escalation rate, avg latency
- [ ] Add nightly evaluation run to GitHub Actions CI; alert on regression
- [ ] Set up Langfuse for LLM call tracing (latency, token costs per stage)
- [ ] Calibrate RS thresholds (0.82, 0.65) against real query log distribution
- [ ] Assess cheaper model for Stage 2 (query clarity is simpler than validation)

---

## Open Decisions

| Decision | Needed By | Status |
|---|---|---|
| Pinecone plan tier — free vs Starter ($70/mo) | Week 7 | Open |
| Escalation handoff — JSON payload only vs webhook | Week 11 | Open |
