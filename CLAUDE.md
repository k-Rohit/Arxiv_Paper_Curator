# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## How to explain things to the user (important)

The user is learning. When explaining ANY concept, follow these rules — strictly:

- **Simple language.** Plain English, not jargon. If you must use a technical term, define it in one sentence.
- **Always include a concrete example.** Code snippet, before/after comparison, real-world analogy, or a worked-through case. Never explain a concept abstractly without showing it.
- **Crisp and short.** Aim for ~30-50 lines per explanation. Cut anything that isn't the core point.
- **No exhaustive surveys.** If there are 5 options, pick ONE recommendation and explain it. Don't list all 5 unless asked.
- **Use tables sparingly** — only when comparing 2-3 things side-by-side adds real value.
- **No fluff phrases** like "as we discussed," "great question," or filler intros. Start with the answer.

Bad: "Dependency injection is a design pattern where dependencies are provided to a class rather than created within it. There are several forms including constructor injection, setter injection, and interface injection. Each has its own tradeoffs..."

Good: "DI = pass the thing in instead of building it inside. Example: `Search(opensearch=client)` instead of `Search()` then `self.opensearch = OpenSearchClient(host='...')` inside. Win: you can swap `client` for a fake in tests."

## Start here

Before doing anything substantial, read these two files — they're the canonical map of the codebase:

1. [PROJECT_MAP.md](PROJECT_MAP.md) — layered architecture, full dependency graph, per-file import/imported-by reference, gotchas.
2. The per-folder README inside whichever area you're touching (`src/db/README.md`, `src/repositories/README.md`, `src/schemas/README.md`, `src/services/README.md` and each sub-service's README, etc.).

The READMEs explain how each folder's files connect to each other and to the outside. Don't re-derive that from scratch — read them.

## What this project is

An end-to-end RAG (retrieval-augmented generation) pipeline for arxiv papers. The user is following the [jamwithai/production-agentic-rag-course](https://github.com/jamwithai/production-agentic-rag-course) repo as a reference. Each week of the course is tagged (`week2.0`, `week3.0`, `week4.0`, …). When comparing this codebase to "the course," fetch files at the relevant tag, e.g.:

```
https://raw.githubusercontent.com/jamwithai/production-agentic-rag-course/week4.0/<path>
```

The user's local code often refactors what the course ships as a single file into per-concern files (e.g. course's `airflow/dags/arxiv_ingestion/tasks.py` is split here into `common.py`, `fetching.py`, `reporting.py`, `setup.py`, `indexing.py`).

## Common commands

The Makefile lifecycle targets bring up the **entire** docker-compose stack (Postgres, Airflow, OpenSearch + Dashboards, Redis, Langfuse, ClickHouse, MinIO). That's a lot for most tasks:

```
make start    # docker compose up --build -d  (ALL services)
make stop     # docker compose down
make status   # docker compose ps
make logs     # tail combined logs
```

For the common case of "just run the DAG," the user prefers starting only the two services Airflow actually needs:

```
docker compose up -d --build postgres airflow     # then http://localhost:8080  (admin / admin)
docker compose stop postgres airflow
```

For OpenSearch experimentation alone:

```
docker compose up -d opensearch opensearch-dashboards   # OS API at http://localhost:9200 (HTTP, not HTTPS — security disabled)
                                                        # Dashboards UI at http://localhost:5601
```

### Python tooling

The project uses **`uv`** (`uv.lock` present). Python is pinned to `>=3.12,<3.13`.

```
uv sync                          # install deps
uv run python -m py_compile <f>  # quick syntax check (used often after edits — see Gotchas)
uv run pytest                    # tests/  directory exists but is currently empty
uv run ruff check src tests      # linter — only import-sort rule ("I") is enabled
uv run ruff format src tests     # format (line-length 130)
```

`make test`, `make lint`, `make format`, `make test-cov`, `make setup`, `make clean` are listed in `.PHONY` but **not implemented** — running them is a no-op.

### Airflow CLI from the container

The DAG ID is `arxiv_paper_ingestion` (note: NOT the filename `arxiv_paper_ingestion_and_indexing.py`).

```
docker exec rag-airflow airflow dags list                                       # see what loaded
docker exec rag-airflow airflow dags list-import-errors                         # diagnose parse failures
docker exec rag-airflow airflow dags unpause arxiv_paper_ingestion              # new DAGs are paused by default
docker exec rag-airflow airflow dags trigger arxiv_paper_ingestion              # manual run (defaults to today's execution date)
docker exec rag-airflow airflow dags trigger arxiv_paper_ingestion --exec-date "2026-05-29T06:00:00+00:00"   # backfill one day
docker exec rag-airflow airflow dags backfill arxiv_paper_ingestion --start-date 2026-05-20 --end-date 2026-05-28
docker exec rag-airflow airflow dags list-runs -d arxiv_paper_ingestion         # see runs
```

## Architecture (the big picture)

Dependencies flow **downward**. Foundation modules at the bottom know nothing about layers above them.

```
ENTRYPOINTS         src/main.py (FastAPI, just a /health stub today)
                    airflow/dags/arxiv_paper_ingestion_and_indexing.py
                    airflow/dags/arxiv_ingestion/{common,fetching,setup,reporting,indexing}.py
       ↓
ORCHESTRATOR        src/services/metadata_fetcher.py   ← the hub
       ↓
SERVICES            src/services/arxiv/         (arxiv API + PDF download)
                    src/services/pdf_parser/    (Docling-backed parsing)
                    src/services/opensearch/    (BM25 + hybrid search) — NOT YET WIRED INTO PIPELINE
       ↓
DATA ACCESS         src/repositories/paper.py (PaperRepository — idempotent `upsert`)
                    src/db/factory.py, src/db/interfaces/{base,postgresql}.py
                    src/models/paper.py (SQLAlchemy ORM `Paper`)
       ↓
FOUNDATION          src/config.py        (env-driven Pydantic Settings)
                    src/exceptions.py    (all domain exception types)
                    src/schemas/{arxiv,database,pdf_parser}/   (Pydantic input/output shapes)
```

### Key patterns to know before editing

- **Service factories.** Every service has `<service>/factory.py` with `@lru_cache(maxsize=1) def make_<service>()`. Same pattern everywhere; copy it for new services. `make_pdf_parser_service` is the most expensive to construct (Docling downloads ~1GB of model weights on first call) — never bypass the cache.
- **Airflow `common.py` builds singletons once.** `airflow/dags/arxiv_ingestion/common.py` has `@lru_cache get_cached_services()` returning a tuple of `(arxiv_client, pdf_parser, database, metadata_fetcher)`. Every task pulls from there. If you add a service (e.g. opensearch), uncomment the line, return a 5-tuple, and update every unpack site.
- **Repository owns DB queries; nothing else.** Never write `session.query(...)` or raw SQL in services or DAG tasks. Always go through `PaperRepository`. The session is injected by the caller — the repo doesn't own connection lifecycle.
- **Async fans out from a single Airflow task.** `MetadataFetcher.fetch_and_process_papers` uses `asyncio.gather` + semaphores to download/parse PDFs concurrently. The DAG task is sync (Airflow needs sync), so `fetching.py` bridges with `asyncio.run(...)`. This is why all the methods are `async def`.
- **Settings split: `config.py` vs `schemas/database/config.py`.** `config.py` is the **single env loader** for the whole app. Per-domain `*Settings` classes (currently just `PostgreSQLSettings`) are the **typed contracts** that components accept. The factory translates one to the other.

## Critical gotchas (things that bite repeatedly in this codebase)

1. **ORM table registration order.** `Base = declarative_base()` lives in `src/db/interfaces/postgresql.py`. `Paper` only attaches to `Base.metadata` when `models/paper.py` is imported. Always:
   ```python
   from src.models.paper import Paper       # MUST come first
   from src.db.factory import make_database
   db = make_database()                     # now create_all sees Paper
   ```
   This bites in notebooks every time.

2. **Indentation bugs disguised as logic bugs.** Multiple files in this repo have had `return` statements wrongly nested inside `if` blocks, methods detached from their class (defined at module level), and dict-comprehension code stuck inside loops. After any non-trivial edit run `python -m py_compile <file>` — it compiles cleanly even when the logic is wrong, but it catches the syntax issues. Then **read the indentation carefully**, especially around `if`/`try`/`for` blocks. Past examples: `setup.py` 5-vs-4-tuple unpack, `opensearch/factory.py` `return` inside `if settings is None:`, multiple `_search_*` methods returning early on the first iteration.

3. **Arxiv rate limiting (HTTP 429).** Arxiv enforces ~1 req per 3s. The client respects it within a run, but **cumulative requests across runs in a short window** (notebook tests + DAG triggers) will get you banned for several minutes. Don't auto-retry harder — wait and try again later.

4. **PDF cache.** Configured as `./data/arxiv_pdfs` (relative to CWD). Inside the Airflow container that resolves to `/opt/airflow/data/arxiv_pdfs/`. The host's `./data` is mounted there in `docker-compose.yml` so PDFs persist on the host and survive container rebuilds.

5. **OpenSearch service exists but isn't wired into the pipeline yet.** `src/services/opensearch/` is built (client, factory, query builder, index config), but `metadata_fetcher.py` doesn't call it and `airflow/dags/arxiv_ingestion/indexing.py` is a 0-byte stub. The DAG file imports `setup_environment`, `fetch_daily_papers`, `generate_daily_report` only — no indexing task. Wiring it in is the next integration step.

6. **OpenSearch is plain HTTP**, no auth. The compose sets `DISABLE_SECURITY_PLUGIN=true`. So `curl http://localhost:9200` works; `https://` will fail. Use `http://localhost:9200` explicitly in browsers (modern browsers default to HTTPS).

7. **`indexing.py` is empty** but the DAG file does NOT import from it, so it doesn't cause an error. Don't be surprised when nothing references it yet.

## Where things live (one-line map)

- **Code reviews and feature work**: `src/services/`, `src/repositories/`. Read the relevant folder README first.
- **DB schema changes**: `src/models/paper.py` (ORM) + `src/schemas/arxiv/paper.py` (Pydantic). They must stay in sync.
- **New env vars / settings**: `src/config.py` (the loader). Per-domain `*Settings` classes get their own file under `src/schemas/<domain>/config.py` if they grow beyond ~5 fields (see `PostgreSQLSettings` for the pattern).
- **Airflow DAG changes**: top-level wiring in `airflow/dags/arxiv_paper_ingestion_and_indexing.py`. Task implementations in `airflow/dags/arxiv_ingestion/<concern>.py`.
- **Docker / infra**: `docker-compose.yml`, `airflow/Dockerfile`, `airflow/entrypoint.sh`.

## Credentials (local dev — committed in the repo, do not reuse anywhere real)

| Service | URL | Username | Password |
|---|---|---|---|
| Airflow UI | http://localhost:8080 | `admin` | `admin` |
| Postgres | `localhost:5432` / db `rag_db` | `rag_user` | `rag_password` |
| OpenSearch | http://localhost:9200 | (no auth — security disabled) | — |
| OpenSearch Dashboards | http://localhost:5601 | (no auth) | — |
