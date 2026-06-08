# Arxiv Paper Curator

A production-style **retrieval-augmented generation (RAG) pipeline for arXiv research papers** — fetch new papers daily, parse them with a structure-aware PDF model, store metadata in Postgres, chunk + embed each paper, and serve hybrid (BM25 + vector) semantic search via OpenSearch.

Built as a hands-on learning project, closely following the [`jamwithai/production-agentic-rag-course`](https://github.com/jamwithai/production-agentic-rag-course) curriculum (currently at **week 4** territory), with some intentional deviations (OpenAI embeddings instead of Jina, per-concern file split in the Airflow DAG, etc.).

---

## What it does (end-to-end)

```
arxiv API  ─▶  fetch metadata (daily)
           ─▶  download PDF                              ┐
           ─▶  parse with Docling (text + sections)      │  Airflow DAG
           ─▶  upsert into Postgres                      │  (scheduled, idempotent)
           ─▶  chunk paper (section-aware, 600-word)     │
           ─▶  embed chunks (OpenAI text-embedding-3)    │
           ─▶  bulk-index chunks into OpenSearch         ┘
                       │
                       ▼
        Search API  ──▶  BM25  ┐
                    ──▶  Vector ├─▶  RRF fusion  ─▶  ranked chunks
                    ──▶  Hybrid ┘
```

One Airflow DAG orchestrates the write path. A FastAPI service (forthcoming) will expose the search endpoints.

---

## Status

| Layer | Status |
|---|---|
| Config, schemas, exceptions | ✅ |
| Postgres + SQLAlchemy ORM + Repository pattern | ✅ |
| arXiv API client (rate-limited, async) | ✅ |
| Docling PDF parser (sections, tables, figures) | ✅ |
| `MetadataFetcher` orchestrator (async fan-out) | ✅ |
| Airflow DAG: setup → fetch → report → cleanup | ✅ |
| OpenSearch client (BM25 + vector + hybrid + RRF) | ✅ |
| Section-aware text chunker | ✅ |
| OpenAI embeddings client (auto-batched, async) | ✅ |
| Hybrid indexing service (chunker + embeddings + OpenSearch) | 🚧 in progress |
| Airflow indexing task (wire indexing into the DAG) | 🚧 in progress |
| FastAPI `/search` endpoint | ⏳ planned |
| Agentic layer (multi-step retrieval, reranking) | ⏳ planned |
| Eval harness | ⏳ planned |

End-to-end pipeline verified via [`notebooks/end-to-end-pipeline.ipynb`](notebooks/end-to-end-pipeline.ipynb) — runs every stage against a real paper in ~1 minute.

---

## Architecture (the 30-second view)

```
ENTRYPOINTS         FastAPI app  ·  Airflow DAGs  ·  Notebooks
       ↓
ORCHESTRATOR        src/services/metadata_fetcher.py  (the hub)
       ↓
SERVICES            arxiv/  ·  pdf_parser/  ·  opensearch/  ·  embeddings/  ·  indexing/
       ↓
DATA ACCESS         repositories/PaperRepository  ·  db/PostgreSQLDatabase
       ↓
FOUNDATION          config.py  ·  exceptions.py  ·  models/  ·  schemas/
```

Dependencies flow **downward** — foundation modules know nothing about the layers above. Every service has a `factory.py` with `@lru_cache`d singleton construction; nothing wires itself up except the entrypoints.

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
| API | FastAPI |
| Orchestration | Apache Airflow 2 (LocalExecutor) |
| Database | PostgreSQL 16 (SQLAlchemy 2.0 ORM) |
| Search | OpenSearch 2.19 (BM25 + k-NN with HNSW) |
| PDF parsing | [Docling](https://github.com/DS4SD/docling) (IBM) |
| Embeddings | OpenAI `text-embedding-3-small` (1024 dims) |
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

# 4. Or bring up everything (Postgres + Airflow + OpenSearch + Dashboards + Redis + Langfuse stack)
make start
```

### Run the DAG

```bash
# Airflow UI: http://localhost:8080  (admin / admin)
# Unpause the DAG and trigger it:
docker exec rag-airflow airflow dags unpause arxiv_paper_ingestion
docker exec rag-airflow airflow dags trigger arxiv_paper_ingestion
```

### Or run end-to-end in a notebook

```bash
docker compose up -d postgres airflow opensearch
uv run jupyter notebook notebooks/end-to-end-pipeline.ipynb
```

The notebook exercises every service in order: fetch → parse → store → chunk → embed → index → search (BM25, vector, hybrid).

### Useful URLs

| Service | URL | Auth |
|---|---|---|
| Airflow UI | http://localhost:8080 | `admin` / `admin` |
| OpenSearch | http://localhost:9200 | none (security plugin disabled) |
| OpenSearch Dashboards | http://localhost:5601 | none |
| Postgres | `localhost:5432` (db `rag_db`) | `rag_user` / `rag_password` |

⚠️ Local dev credentials only — checked in for convenience. Don't reuse anywhere real.

---

## Deviations from the source course

This repo isn't a clone — a few intentional changes:

| Aspect | Course | This repo |
|---|---|---|
| Embeddings provider | Jina (1024-dim via API) | OpenAI `text-embedding-3-small` (1024 dims, configurable) |
| Airflow DAG layout | Single `tasks.py` with all task functions | Split per concern: `common.py`, `fetching.py`, `setup.py`, `reporting.py`, `indexing.py` |
| Settings split | Mostly inline | `OpenAIEmbeddingsSettings` as a typed sub-config under `Settings` |
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

- [`jamwithai/production-agentic-rag-course`](https://github.com/jamwithai/production-agentic-rag-course) — the curriculum this repo follows. Code reference at week tags (`week2.0`, `week3.0`, `week4.0`, …).
- [Docling](https://github.com/DS4SD/docling) — IBM's structure-aware PDF parser.
- [OpenSearch](https://opensearch.org/) — the search engine with native hybrid + RRF support.

---

## License

MIT — see [LICENSE](LICENSE) (to be added).
