# Arxiv Paper Curator

A production-style **retrieval-augmented generation (RAG) pipeline for arXiv research papers** — fetch new papers daily, parse them with a structure-aware PDF model, store metadata in Postgres, chunk + embed each paper, serve hybrid (BM25 + vector) semantic search via OpenSearch, and answer questions over the corpus with a cached LLM-backed Q&A endpoint.

Built as a hands-on learning project, closely following the [`jamwithai/production-agentic-rag-course`](https://github.com/jamwithai/production-agentic-rag-course) curriculum (currently at **week 6** territory — cache + LLM Q&A done; Langfuse, agentic RAG, and UI next), with some intentional deviations (OpenAI for both embeddings and chat in place of Jina + Ollama, per-concern file split in the Airflow DAG, etc.).

---

## What it does (end-to-end)

```
arxiv API  ─▶  fetch metadata (daily)
           ─▶  download PDF                              ┐
           ─▶  parse with Docling (text + sections)      │  Airflow DAG
           ─▶  upsert into Postgres                      │  (scheduled, idempotent)
           ─▶  chunk paper (section-aware, ~500-word)    │
           ─▶  embed chunks (OpenAI text-embedding-3)    │
           ─▶  bulk-index chunks into OpenSearch         ┘
                       │
                       ▼
      FastAPI  ─▶  /hybrid_search  ──▶  BM25 + vector + RRF  ─▶  ranked chunks
               ─▶  /ask            ──▶  Redis exact-match cache  ──▶  HIT? return
                                                                 ──▶  MISS? retrieval + LLM
                                                                              │
                                                                              ▼
                                                            "what is multi-head attention?"
                                                                              │
                                                                              ▼
                                                       prompt = question + top-K chunks
                                                       OpenAI gpt-4o-mini
                                                       answer + arxiv_id sources
```

One Airflow DAG owns the write path. A FastAPI service (`/api/v1/ping`, `/api/v1/hybrid_search`, `/api/v1/ask`) owns the read path, with a Redis cache layer and graceful degradation if Redis is unavailable. Observability (Langfuse), agentic retrieval, and a Gradio chat UI are next.

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
| `/api/v1/ping` health-check endpoint | ✅ |
| `/api/v1/hybrid_search` retrieval endpoint | ✅ |
| `/api/v1/ask` RAG Q&A endpoint (retrieve → LLM → answer) | ✅ |
| Redis exact-match cache for `/ask` (with graceful degrade) | ✅ |
| **Langfuse tracing / observability** | ⏳ planned (course week 6) |
| **Agentic RAG (LangGraph: grade → rewrite → guardrails)** | ⏳ planned (course week 7) |
| **Gradio chat UI** for "talk to the papers" | ⏳ planned (course week 5/7) |
| Telegram bot interface | ⏳ optional (course week 7) |
| Eval harness (RAG quality + LLM-as-judge) | ⏳ planned |

End-to-end pipeline verified via [`notebooks/end-to-end-pipeline.ipynb`](notebooks/end-to-end-pipeline.ipynb) — runs every stage against a real paper in ~1 minute.

---

## Architecture (the 30-second view)

```
ENTRYPOINTS         FastAPI app (src/main.py)  ·  Airflow DAGs  ·  Notebooks
       ↓
ROUTERS             routers/ping  ·  routers/hybrid_search  ·  routers/ask
       ↓
DI LAYER            dependencies.py  (typed Annotated aliases — SessionDep, OpenSearchDep, LLMDep, CacheDep…)
       ↓
ORCHESTRATOR        src/services/metadata_fetcher.py  (the ingestion hub)
       ↓
SERVICES            arxiv/  ·  pdf_parser/  ·  opensearch/  ·  embeddings/  ·  indexing/  ·  openai_/  ·  cache/
       ↓
DATA ACCESS         repositories/PaperRepository  ·  db/PostgreSQLDatabase
       ↓
FOUNDATION          config.py  ·  exceptions.py  ·  middlewares.py  ·  models/  ·  schemas/
```

Dependencies flow **downward** — foundation modules know nothing about the layers above. Every service has a `factory.py` with `@lru_cache`d (or course-style explicit) singleton construction. Services are built **once** at startup in the FastAPI `lifespan` and stored on `app.state`; routers receive them via typed `*Dep` aliases.

For the full picture (per-file imports/imported-by, mermaid graph, gotchas) see **[PROJECT_MAP.md](PROJECT_MAP.md)**. For a focused tour of one folder, each has its own README:

- [`src/db/README.md`](src/db/README.md)
- [`src/models/README.md`](src/models/README.md)
- [`src/repositories/README.md`](src/repositories/README.md)
- [`src/schemas/README.md`](src/schemas/README.md)
- [`src/services/README.md`](src/services/README.md)
  - [`arxiv/`](src/services/arxiv/README.md) · [`pdf_parser/`](src/services/pdf_parser/README.md) · [`opensearch/`](src/services/opensearch/README.md) · [`embeddings/`](src/services/embeddings/README.md)

---

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 (`uv` for dep management) |
| API | FastAPI (lifespan + typed `Annotated[T, Depends(...)]` DI) |
| Orchestration | Apache Airflow 2 (LocalExecutor) |
| Database | PostgreSQL 16 (SQLAlchemy 2.0 ORM) |
| Search | OpenSearch 2.19 (BM25 + k-NN with HNSW, RRF fusion) |
| PDF parsing | [Docling](https://github.com/DS4SD/docling) (IBM) |
| Embeddings | OpenAI `text-embedding-3-small` (1024 dims via Matryoshka) |
| LLM | OpenAI `gpt-4o-mini` (chat completion) |
| Cache | Redis 7 (exact-match, normalized-query key, 6h TTL) |
| Observability | Langfuse (planned) |
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
# Set OPENAI_API_KEY=sk-...

# 3. Bring up the infrastructure (Postgres + Airflow only — most common dev mode)
docker compose up -d --build postgres airflow

# 4. Or bring up the full read path (search + cache + LLM)
docker compose up -d postgres opensearch redis api

# 5. Or bring up everything (Postgres + Airflow + OpenSearch + Dashboards + Redis + Langfuse stack)
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
curl http://localhost:8000/api/v1/ping

# Hybrid retrieval
curl -X POST http://localhost:8000/api/v1/hybrid_search \
  -H 'Content-Type: application/json' \
  -d '{"query": "what is multi-head attention?", "top_k": 5, "use_hybrid": true}'

# RAG Q&A (first call slow, second call cached)
curl -X POST http://localhost:8000/api/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "what is multi-head attention?", "top_k": 5, "use_hybrid": true}'

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
| FastAPI app | http://localhost:8000 | none |
| FastAPI OpenAPI docs | http://localhost:8000/docs | none |
| Airflow UI | http://localhost:8080 | `admin` / `admin` |
| OpenSearch | http://localhost:9200 | none (security plugin disabled) |
| OpenSearch Dashboards | http://localhost:5601 | none |
| Postgres | `localhost:5432` (db `rag_db`) | `rag_user` / `rag_password` |
| Redis | `localhost:6379` | none |

⚠️ Local dev credentials only — checked in for convenience. Don't reuse anywhere real.

---

## Deviations from the source course

This repo isn't a clone — a few intentional changes:

| Aspect | Course | This repo |
|---|---|---|
| Embeddings provider | Jina (1024-dim via API) | OpenAI `text-embedding-3-small` (1024 dims, configurable) |
| LLM | Ollama (local, e.g. `llama3.2`) | OpenAI `gpt-4o-mini` (Mac can't run local models comfortably) |
| Airflow DAG layout | Single `tasks.py` | Split per concern: `common.py`, `fetching.py`, `setup.py`, `reporting.py`, `indexing.py` |
| Settings split | Mostly inline | Per-domain `*Settings` classes (`OpenAIEmbeddingsSettings`, `OpenAIClientSettings`, `RedisSettings`) as typed sub-configs under `Settings` |
| Per-folder READMEs | None | Every `src/` subfolder has a README explaining files + connections |
| Project map | None | [`PROJECT_MAP.md`](PROJECT_MAP.md) at the root |

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

---

## License

MIT — see [LICENSE](LICENSE) (to be added).
