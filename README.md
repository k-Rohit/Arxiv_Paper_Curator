# PaperPilot

*Agentic research assistant for arXiv papers.*

An end-to-end production RAG system for arXiv papers. Daily Airflow ingestion pipeline, section-aware chunking, hybrid BM25+HNSW retrieval with RRF fusion, FastAPI Q&A endpoint with Redis caching, and an agentic layer on LangGraph with guardrails, document grading, query-rewrite retry loop, Postgres-checkpointed conversational memory, and a live arXiv fetch tool the agent can call mid-conversation to pull in papers outside the indexed corpus. Runs on Docker Compose. Traced with LangSmith. Quality is measured with a DeepEval suite (5 LLM-as-judge metrics over a synthetic golden set), which was also used to validate a migration from OpenSearch to Pinecone hybrid search — see [Evaluation](#evaluation).

Built as a hands-on learning project, closely following the [`jamwithai/production-agentic-rag-course`](https://github.com/jamwithai/production-agentic-rag-course) curriculum , with some intentional deviations (OpenAI in place of Jina + Ollama, LangSmith in place of Langfuse, a hand-built chat UI in place of Gradio, per-concern file split in the Airflow DAG, etc.).

---

## Architecture

<img width="3278" height="1664" alt="Arxiv_Paper_Curator" src="https://github.com/user-attachments/assets/f33e59bf-215a-4704-b5aa-f5d65451957b" />


One Airflow DAG owns the write path. A FastAPI service (`/api/v1/health`, `/api/v1/hybrid-search`, `/api/v1/ask`, `/api/v1/agentic_ask`) owns the read path. Redis caches `/ask` responses with graceful degradation; LangSmith traces every LLM call in the agentic flow. A built-in chat UI (sidebar + conversation history, agent trace panel) is served at `/` by the same FastAPI process.

The agentic graph (`/agentic_ask`) is checkpointed in Postgres per `thread_id`, so it remembers prior turns in a conversation (condensing follow-ups into standalone queries before retrieval). A `tool_router_node` first classifies each query as either a normal retrieval question or a request to go fetch papers arXiv doesn't have indexed yet — the latter drives a `translate_query_node → live_fetch_call_node` path that queries the arXiv API live, downloads + parses + chunks + indexes the results through the same pipeline the Airflow DAG uses, then retrieves and answers from what it just fetched.

---

## Status

| Layer | Status |
|---|---|
| Config, schemas, exceptions | ✅ |
| Postgres + SQLAlchemy ORM + Repository pattern | ✅ |
| arXiv API client (rate-limited, async) | ✅ |
| Docling PDF parser (sections, tables, figures) | ✅ |
| `MetadataFetcher` orchestrator (async fan-out) | ✅ |
| Airflow DAG: setup → fetch → index → report | ✅ |
| OpenSearch client (BM25 + vector + hybrid + RRF) | ✅ |
| Section-aware text chunker | ✅ |
| OpenAI embeddings client (auto-batched, async) | ✅ |
| Hybrid indexing service (chunker + embeddings + OpenSearch) | ✅ |
| OpenAI LLM (chat-completion) client + RAG prompt builder | ✅ |
| FastAPI app: lifespan, dependencies, middleware, OpenAPI | ✅ |
| `/api/v1/health` health-check endpoint (reports Postgres + OpenSearch status) | ✅ |
| `/api/v1/hybrid-search/` retrieval endpoint | ✅ |
| `/api/v1/ask` RAG Q&A endpoint (retrieve → LLM → answer) | ✅ |
| Redis exact-match cache for `/ask` (with graceful degrade) | ✅ |
| **Agentic RAG service** — LangGraph nodes (condense follow-up, guardrail, tool router, retrieve, grade, rewrite, translate query, live fetch, generate, out_of_scope), Context DI, compiled graph | ✅ |
| **Postgres-checkpointed conversational memory** (`AsyncPostgresSaver`, per-`thread_id` history, follow-up condensing) | ✅ |
| **Live arXiv fetch tool** — agent decides to fetch papers outside the corpus, indexes them through the same chunk/embed/index pipeline as the DAG, then answers from them | ✅ |
| **LangSmith tracing / observability** (auto-traces every LangGraph node + LLM call) | ✅ |
| **`/api/v1/agentic_ask` endpoint** (rich sources + reasoning steps in response, `thread_id`-scoped memory) | ✅ |
| **Chat UI** — sidebar with per-browser conversation history (localStorage, keyed to `thread_id`), visual agent trace panel, citation cards | ✅ |
| Per-service test notebooks (`notebooks/services/01-09`) | ✅ |
| **Eval suite** — DeepEval synthetic goldens + 5 LLM-as-judge metrics (retriever + generator), Markdown reports | ✅ |
| **Pinecone hybrid retrieval** (dense OpenAI + normalized sparse vectors, α-weighted) — evaluated at parity with OpenSearch | ✅ |
| Switch API / agent / ingestion from OpenSearch to Pinecone | ⏳ in progress |
| Production ingestion via scheduled GitHub Actions (replacing Airflow in prod) | 🗓️ planned |

End-to-end pipeline verified via [`notebooks/end-to-end-pipeline.ipynb`](notebooks/end-to-end-pipeline.ipynb) — runs every stage against a real paper in ~1 minute.

---

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 (`uv` for dep management) |
| API | FastAPI (lifespan + typed `Annotated[T, Depends(...)]` DI) |
| Orchestration | Apache Airflow 2 (LocalExecutor) |
| Database | PostgreSQL 16 (SQLAlchemy 2.0 ORM) |
| Search | OpenSearch 2.19 (BM25 + k-NN with HNSW, RRF fusion) → migrating to **Pinecone** serverless (dense + `pinecone-sparse-english-v0`, `dotproduct`) |
| PDF parsing | [Docling](https://github.com/DS4SD/docling) (IBM) |
| Embeddings | OpenAI `text-embedding-3-small` (1024 dims via Matryoshka) |
| LLM | OpenAI `gpt-4o-mini` (chat completion + structured Pydantic outputs) |
| Agent framework | LangGraph (StateGraph + Context DI + ToolNode + conditional edges, 2 tools: retrieve + live-fetch) |
| Conversational memory | `AsyncPostgresSaver` (LangGraph's native Postgres checkpointer), keyed by `thread_id` |
| Agent tracing | LangSmith (auto-instruments every LangGraph node + LLM call via `LANGCHAIN_TRACING_V2=true`) |
| Evaluation | DeepEval (Synthesizer for goldens; `gpt-4.1-mini` as judge) |
| Cache | Redis 7 (exact-match, normalized-query key, 6h TTL) |
| Chat UI | Vanilla HTML/CSS/JS (`src/static/`, served via `StaticFiles`) — sidebar + localStorage conversation history, visual agent trace panel, no framework, no build step |
| Container runtime | Docker Compose |
| Linting | Ruff (I, F, E, W, B, RET, SIM, UP) |

---

## Quick start

### Prerequisites

- Docker Desktop
- `uv` ([install](https://docs.astral.sh/uv/getting-started/installation/))
- An OpenAI API key

### Setup

```bash
# 1. Install Python dependencies
uv sync

# 2. Configure secrets — copy and edit
cp .env.example .env       # (create one from your existing if missing)
# Set:
#   OPENAI_API_KEY=sk-...
#   LANGCHAIN_TRACING_V2=true       # enable LangSmith auto-tracing
#   LANGCHAIN_API_KEY=lsv2_pt_...   # from smith.langchain.com
#   LANGCHAIN_PROJECT=paperpilot

# 3. Bring up the infrastructure (Postgres + Airflow only — most common dev mode)
docker compose up -d --build postgres airflow

# 4. Or bring up the full read path (search + cache + LLM)
docker compose up -d postgres opensearch redis api

# 5. Or bring up everything (Postgres + Airflow + OpenSearch + Dashboards + Redis + API)
make start
```

### Run the DAG (write path)

```bash
# Airflow UI: http://localhost:8080  (admin / admin)
# Unpause the DAG and trigger it:
docker exec rag-airflow airflow dags unpause arxiv_paper_ingestion
docker exec rag-airflow airflow dags trigger arxiv_paper_ingestion
```

### Hit the API (read path)

```bash
# Health-check
curl http://localhost:8000/api/v1/health

# Hybrid retrieval
curl -X POST http://localhost:8000/api/v1/hybrid-search/ \
  -H 'Content-Type: application/json' \
  -d '{"query": "what is multi-head attention?", "size": 5, "use_hybrid": true}'

# RAG Q&A (first call slow, second call cached)
curl -X POST http://localhost:8000/api/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "what is multi-head attention?", "top_k": 5, "use_hybrid": true}'

# Agentic Q&A (guardrail + tool router + retrieve/grade/rewrite loop + generate; memory + tracing
# keyed by thread_id — required, since the graph is checkpointed)
curl -X POST http://localhost:8000/api/v1/agentic_ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "how does BERT differ from GPT?", "thread_id": "demo-1"}'

# Follow-up in the SAME thread — condensed against prior turns before retrieval
curl -X POST http://localhost:8000/api/v1/agentic_ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "which one came out first?", "thread_id": "demo-1"}'

# Ask for something outside the indexed corpus — the router sends this to the live-fetch
# path: query arXiv -> download/parse/chunk/index -> retrieve -> answer (~30-40s)
curl -X POST http://localhost:8000/api/v1/agentic_ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "find recent papers on diffusion models and summarize the key idea", "thread_id": "demo-2"}'

# Inspect Redis cache
docker exec rag-redis redis-cli KEYS 'exact_cache:*'
```

OpenAPI docs at `http://localhost:8000/docs`.

### Or run end-to-end in a notebook

```bash
docker compose up -d postgres airflow opensearch
uv run jupyter notebook notebooks/end-to-end-pipeline.ipynb
```

The notebook exercises every service in order: fetch → parse → store → chunk → embed → index → search (BM25, vector, hybrid).

### Useful URLs

| Service | URL | Auth |
|---|---|---|
| **Chat UI** | http://localhost:8000/ | none |
| FastAPI OpenAPI docs | http://localhost:8000/docs | none |
| Airflow UI | http://localhost:8080 | `admin` / `admin` |
| OpenSearch | http://localhost:9200 | none (security plugin disabled) |
| OpenSearch Dashboards | http://localhost:5601 | none |
| Postgres | `localhost:5432` (db `rag_db`) | `rag_user` / `rag_password` |
| Redis | `localhost:6379` | none |

⚠️ Local dev credentials only — checked in for convenience. Don't reuse anywhere real.

---

## Evaluation

The `evals/` folder (outside `src/`, so it never ships in the API image) measures RAG quality with [DeepEval](https://github.com/confident-ai/deepeval) in three steps:

```
generate_goldens  →  generate_evaluation_dataset  →  evaluate_rag_app
 (questions +          (run each question through      (LLM judge scores
  expected answers)     retrieval + generation)          every answer)
```

| Step | What it does |
|---|---|
| **Goldens** | `Synthesizer.generate_goldens_from_contexts` writes questions + expected answers from real indexed chunks (5 papers × 3 chunks × 2 questions = **30 goldens**), evolved for harder reasoning / constrained / concrete variants. Committed so every run uses the same questions. |
| **Evaluation dataset** | Mirrors `/ask` (embed → hybrid search → LLM) without the cache, filling each golden's `actual_output` and `retrieval_context`. The retriever (`opensearch` or `pinecone`) is a config switch. |
| **Metrics** | Retriever: Contextual Recall, Precision, Relevancy. Generator: Faithfulness, Answer Relevancy. Judge `gpt-4.1-mini`, pass threshold 0.65. Results saved as a Markdown report per run. |

### Results: OpenSearch vs Pinecone

Same 30 goldens, same chunks, same LLM — only the vector store changes. Average scores:

| Metric | OpenSearch (BM25 + vector, RRF) | Pinecone (sparse + dense, α=0.6) |
|---|---|---|
| Contextual Recall | 1.000 | 0.987 |
| Contextual Precision | 0.928 | **0.973** |
| Contextual Relevancy | 0.883 | 0.870 |
| Faithfulness | 0.949 | 0.942 |
| Answer Relevancy | 0.971 | 0.973 |
| Test cases passing all 5 metrics | 27 / 30 | 26 / 30 |

**Takeaway:** quality held (Δ ≤ 0.013 on four metrics, within LLM-judge noise at n=30) and ranking improved (precision +0.045), so the migration trades no measurable quality for much simpler deployment. Full per-question reports with judge reasoning: [`evals/reports/`](evals/reports/).

Getting here surfaced one real bug: Pinecone simply *adds* dense and sparse dot products, and its sparse weights are unscaled (a chunk scored ~1098 against itself vs ≤ 1 for dense), so keyword matches drowned out meaning regardless of α. L2-normalizing sparse vectors on both upsert and query fixed it.

### Run it

```bash
docker compose up -d postgres opensearch          # needed for goldens + the OpenSearch retriever
uv run python -m evals.data.generate_goldens      # once; review + commit the JSON

DEEPEVAL__RETRIEVER=pinecone uv run python -m evals.data.generate_evaluation_dataset
DEEPEVAL__RETRIEVER=pinecone uv run python -m evals.evaluate_rag_app            # all 5 metrics
DEEPEVAL__RETRIEVER=pinecone uv run python -m evals.evaluate_rag_app retriever  # or one component
```

---

## Deviations from the source course

This repo isn't a clone — a few intentional changes:

| Aspect | Course | This repo |
|---|---|---|
| Embeddings provider | Jina (1024-dim via API) | OpenAI `text-embedding-3-small` (1024 dims, configurable) |
| LLM | Ollama (local, e.g. `llama3.2`) | OpenAI `gpt-4o-mini` (Mac can't run local models comfortably) |
| Observability | Langfuse (self-hosted; 5 docker services) | LangSmith (hosted; 2 env vars, zero infra, auto-traces LangGraph via `LANGCHAIN_TRACING_V2=true`) |
| Airflow DAG layout | Single `tasks.py` | Split per concern: `common.py`, `fetching.py`, `setup.py`, `reporting.py`, `indexing.py` |
| Settings split | Mostly inline | Per-domain `*Settings` classes (`OpenAIEmbeddingsSettings`, `OpenAIClientSettings`, `RedisSettings`) as typed sub-configs under `Settings` |
| Per-folder READMEs | None | Every `src/` subfolder has a README explaining files + connections |
| Project map | None | [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) (local-only, gitignored) |
| Conversational memory | Not covered | `AsyncPostgresSaver` checkpointer on the LangGraph agent — per-`thread_id` history, follow-up condensing node |
| Live paper fetch | Not covered | Agent-invoked tool that queries arXiv live, then downloads/parses/chunks/indexes on demand for papers outside the corpus, routed by a dedicated `tool_router_node` |

The course is the authoritative reference for the curriculum. This repo's refactors are personal preferences for navigation and modularity.

---

## Development workflow

```bash
# Run linter
uv run ruff check src

# Auto-fix what can be fixed
uv run ruff check src --fix

# Format
uv run ruff format src

# Quick syntax check after any non-trivial edit
uv run python -m py_compile src/path/to/file.py
```

Tests live in `tests/` (currently empty — pytest set up, fixtures TBD).

---

## Credits

- [`jamwithai/production-agentic-rag-course`](https://github.com/jamwithai/production-agentic-rag-course) — the curriculum this repo follows. Code reference at week tags (`week2.0`, `week3.0`, …, `week7.0`).
- [Docling](https://github.com/DS4SD/docling) — IBM's structure-aware PDF parser.
- [OpenSearch](https://opensearch.org/) — the search engine with native hybrid + RRF support.
- [Pinecone](https://www.pinecone.io/) — serverless vector database used for sparse + dense hybrid retrieval.
- [DeepEval](https://github.com/confident-ai/deepeval) — golden synthesis and LLM-as-judge RAG metrics.

---

## License

MIT — see [LICENSE](LICENSE) (to be added).
