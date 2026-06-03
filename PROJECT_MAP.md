# Project Map — Arxiv Paper Curator

A mind map of the `src/` codebase: what each file does, what it imports, and
what imports it. Use this to trace dependencies when a change in one file
ripples into others.

> Mental model: dependencies flow **downward**. Foundation modules at the
> bottom know nothing about the layers above them. The orchestrator at the top
> (`metadata_fetcher.py`) wires everything together.

---

## 0. Per-folder deep dives

For a focused explanation of one area, jump straight to its README. Each
covers: what the folder does, file-by-file roles, internal connections,
and dependencies in/out.

| Folder | What it owns | Doc |
|---|---|---|
| `src/db/` | Database connection lifecycle, SQLAlchemy `Base` | [db/README](src/db/README.md) |
| `src/models/` | ORM table definitions | [models/README](src/models/README.md) |
| `src/repositories/` | Data access (the only place that queries Postgres) | [repositories/README](src/repositories/README.md) |
| `src/schemas/` | Pydantic data shapes for validation and boundaries | [schemas/README](src/schemas/README.md) |
| `src/services/` | Business logic + external integrations (top-level + 3 sub-services) | [services/README](src/services/README.md) |
| `src/services/arxiv/` | arxiv API client + PDF download with rate limiting | [services/arxiv/README](src/services/arxiv/README.md) |
| `src/services/pdf_parser/` | Docling-backed PDF parsing | [services/pdf_parser/README](src/services/pdf_parser/README.md) |
| `src/services/opensearch/` | Search index client, BM25 + hybrid search, query builder deep dive | [services/opensearch/README](src/services/opensearch/README.md) |

---

## 1. Layered architecture (who depends on whom)

```
┌─────────────────────────────────────────────────────────────┐
│ ENTRYPOINTS                                                   │
│   src/main.py (FastAPI app)                                   │
│   airflow/dags/arxiv_paper_ingestion_and_indexing.py          │
│   airflow/dags/arxiv_ingestion/{common,fetching,…}.py         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR                                                  │
│   src/services/metadata_fetcher.py   ← the hub                │
│     MetadataFetcher + make_metadata_fetcher()                 │
└─────────────────────────────────────────────────────────────┘
        │                  │                    │
┌─────────────────────┐ ┌────────────────┐ ┌─────────────────┐
│ SERVICES            │ │ REPOSITORIES   │ │ DB              │
│ arxiv/client        │ │ repositories/  │ │ db/factory      │
│ pdf_parser/         │ │   paper.py     │ │ db/interfaces/  │
│   parser, docling   │ │ (PaperRepo)    │ │   base,         │
│ opensearch/         │ │                │ │   postgresql    │
│   client,           │ │                │ │                 │
│   query_builder,    │ │                │ │                 │
│   index_config      │ │                │ │                 │
└─────────────────────┘ └────────────────┘ └─────────────────┘
        │                  │                    │
┌─────────────────────────────────────────────────────────────┐
│ FOUNDATION (imported widely, import nothing internal)         │
│   src/config.py        — settings (Arxiv, PDFParser, DB, OS)  │
│   src/exceptions.py    — all custom exception types           │
│   src/models/paper.py  — SQLAlchemy ORM table `Paper`         │
│   src/schemas/arxiv/paper.py       — ArxivPaper, PaperCreate  │
│   src/schemas/pdf_parser/models.py — PdfContent, ParsedPaper… │
│   src/schemas/database/config.py   — PostgreSQLSettings       │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Dependency graph (mermaid — renders in GitHub/VS Code)

```mermaid
graph TD
    main[main.py<br/>FastAPI]
    MF[services/metadata_fetcher.py<br/>MetadataFetcher]

    AC[services/arxiv/client.py<br/>ArxivClient]
    AF[services/arxiv/factory.py]
    PP[services/pdf_parser/parser.py<br/>PDFParserService]
    DP[services/pdf_parser/docling_parser.py<br/>DoclingParser]
    PF[services/pdf_parser/factory.py]

    REPO[repositories/paper.py<br/>PaperRepository]
    DBF[db/factory.py<br/>make_database]
    PG[db/interfaces/postgresql.py<br/>PostgreSQLDatabase, Base]
    DBASE[db/interfaces/base.py<br/>BaseDatabase, BaseRepository]

    MODEL[models/paper.py<br/>Paper ORM]
    SARX[schemas/arxiv/paper.py<br/>ArxivPaper, PaperCreate]
    SPDF[schemas/pdf_parser/models.py<br/>PdfContent, ParsedPaper]
    SDB[schemas/database/config.py<br/>PostgreSQLSettings]
    CFG[config.py<br/>get_settings, Settings]
    EXC[exceptions.py]

    MF --> REPO
    MF --> AC
    MF --> PP
    MF --> SARX
    MF --> SPDF
    MF --> CFG
    MF --> EXC

    AF --> AC
    AF --> CFG
    AC --> CFG
    AC --> EXC
    AC --> SARX

    PF --> PP
    PF --> CFG
    PP --> DP
    PP --> EXC
    PP --> SPDF
    DP --> EXC
    DP --> SPDF

    REPO --> MODEL
    REPO --> SARX

    DBF --> CFG
    DBF --> DBASE
    DBF --> PG
    DBF --> SDB
    PG --> DBASE
    PG --> SDB
    MODEL --> PG
```

---

## 3. Per-file reference: imports ↓ / imported-by ↑

Foundation files first (most depended-on), orchestrator last.

### `src/config.py`  — settings
- **Defines:** `Settings`, `ArxivSettings`, `PDFParserSettings`, `get_settings()`
- **Imports (internal):** none
- **Imported by:** `db/factory`, `services/arxiv/client`, `services/arxiv/factory`, `services/pdf_parser/factory`, `services/metadata_fetcher`

### `src/exceptions.py`  — error types
- **Defines:** all `*Exception` / `*Error` classes (Arxiv, PDF, Repository, Metadata…)
- **Imports (internal):** none
- **Imported by:** `services/arxiv/client`, `services/pdf_parser/parser`, `services/pdf_parser/docling_parser`, `services/metadata_fetcher`

### `src/schemas/arxiv/paper.py`  — arxiv data shapes
- **Defines:** `ArxivPaper`, `PaperBase`, `PaperCreate`
- **Imports (internal):** none
- **Imported by:** `repositories/paper`, `services/arxiv/client`, `services/metadata_fetcher`

### `src/schemas/pdf_parser/models.py`  — parsed-PDF shapes
- **Defines:** `ParserType`, `PaperSection`, `PaperFigure`, `PaperTable`, `PdfContent`, `ArxivMetadata`, `ParsedPaper`
- **Imports (internal):** none
- **Imported by:** `services/pdf_parser/parser`, `services/pdf_parser/docling_parser`, `services/metadata_fetcher`

### `src/schemas/database/config.py`  — DB settings
- **Defines:** `PostgreSQLSettings`
- **Imports (internal):** none
- **Imported by:** `db/factory`, `db/interfaces/postgresql`

### `src/db/interfaces/base.py`  — DB abstractions
- **Defines:** `BaseDatabase` (ABC), `BaseRepository` (ABC)
- **Imports (internal):** none
- **Imported by:** `db/interfaces/postgresql`, `db/factory`

### `src/db/interfaces/postgresql.py`  — Postgres impl + ORM Base
- **Defines:** `PostgreSQLDatabase`, `Base` (`declarative_base()`)
- **Imports:** `db/interfaces/base` (`BaseDatabase`), `schemas/database/config` (`PostgreSQLSettings`)
- **Imported by:** `db/factory`, `models/paper` (for `Base`)

### `src/models/paper.py`  — ORM table
- **Defines:** `Paper(Base)`
- **Imports:** `db/interfaces/postgresql` (`Base`)
- **Imported by:** `repositories/paper`
- ⚠️ See gotcha #1 below — `Paper` must be imported before `create_all` runs.

### `src/db/factory.py`  — DB constructor
- **Defines:** `make_database() -> BaseDatabase`
- **Imports:** `config`, `db/interfaces/base`, `db/interfaces/postgresql`, `schemas/database/config`
- **Imported by:** (entrypoints / notebooks)

### `src/repositories/paper.py`  — data access
- **Defines:** `PaperRepository`
- **Imports:** `models/paper` (`Paper`), `schemas/arxiv/paper` (`PaperCreate`)
- **Imported by:** `services/metadata_fetcher`

### `src/services/arxiv/client.py`  — arxiv API client
- **Defines:** `ArxivClient`
- **Imports:** `config` (`ArxivSettings`), `exceptions`, `schemas/arxiv/paper` (`ArxivPaper`)
- **Imported by:** `services/arxiv/factory`, `services/metadata_fetcher`

### `src/services/arxiv/factory.py`
- **Defines:** `make_arxiv_client() -> ArxivClient`
- **Imports:** `config`, `.client`
- **Imported by:** (entrypoints)

### `src/services/pdf_parser/docling_parser.py`  — Docling backend
- **Defines:** `DoclingParser`
- **Imports:** `exceptions`, `schemas/pdf_parser/models`
- **Imported by:** `services/pdf_parser/parser`

### `src/services/pdf_parser/parser.py`  — parser facade
- **Defines:** `PDFParserService`
- **Imports:** `exceptions`, `schemas/pdf_parser/models` (`PdfContent`), `.docling_parser` (`DoclingParser`)
- **Imported by:** `services/pdf_parser/factory`, `services/metadata_fetcher`

### `src/services/pdf_parser/factory.py`
- **Defines:** `make_pdf_parser_service() -> PDFParserService`
- **Imports:** `config`, `.parser`
- **Imported by:** `airflow/dags/arxiv_ingestion/common.py`

### `src/services/opensearch/index_config_hybrid.py`  — index schema + RRF pipeline
- **Defines:** `ARXIV_PAPERS_CHUNKS_INDEX`, `ARXIV_PAPERS_CHUNKS_MAPPING`, `HYBRID_RRF_PIPELINE`
- **Imports (internal):** none — pure data dicts
- **Imported by:** `services/opensearch/client`

### `src/services/opensearch/query_builder.py`  — BM25 query DSL builder
- **Defines:** `QueryBuilder` (`.build()` produces the OpenSearch search body dict)
- **Imports (internal):** none — pure dict-building logic
- **Imported by:** `services/opensearch/client`

### `src/services/opensearch/client.py`  — OpenSearch wrapper
- **Defines:** `OpenSearchClient` (setup, index, search, delete; BM25/vector/hybrid)
- **Imports:** `config.Settings`, `.index_config_hybrid` (`ARXIV_PAPERS_CHUNKS_MAPPING`, `HYBRID_RRF_PIPELINE`), `.query_builder` (`QueryBuilder`)
- **Imported by:** `services/opensearch/factory`

### `src/services/opensearch/factory.py`
- **Defines:** `make_opensearch_client()` (cached singleton) and `make_opensearch_client_fresh()`
- **Imports:** `config`, `.client`
- **Imported by:** `airflow/dags/arxiv_ingestion/common.py` (once wired in)

### `src/services/metadata_fetcher.py`  — ★ ORCHESTRATOR
- **Defines:** `MetadataFetcher`, `make_metadata_fetcher(...)`
- **Imports:** `config`, `exceptions`, `repositories/paper` (`PaperRepository`), `schemas/arxiv/paper`, `schemas/pdf_parser/models`, `services/arxiv/client` (`ArxivClient`), `services/pdf_parser/parser` (`PDFParserService`)
- **Imported by:** `airflow/dags/arxiv_ingestion/common.py` (via `make_metadata_fetcher`)

### `src/main.py`  — FastAPI entrypoint
- **Defines:** `app`, `health()`
- **Imports (internal):** none yet (just `fastapi`)

---

## 4. Runtime data flow (the happy path)

```
arxiv API ──> ArxivClient ──> ArxivPaper schema
                                   │
PDF file ──> PDFParserService ──> DoclingParser ──> PdfContent / ParsedPaper
                                   │
                                   ▼
                          MetadataFetcher  (combines metadata + parsed content)
                                   │
                                   ▼
                          PaperRepository.create(PaperCreate)
                                   │
                                   ▼
                          PostgreSQLDatabase ──> papers table (Paper ORM)
```

The `factory.py` files (`make_*`) exist so callers build a fully-wired object
without knowing its dependencies — the standard construction seam for this repo.

---

## 5. Gotchas worth remembering

1. **ORM table registration order.** `Base` lives in
   `db/interfaces/postgresql.py`; the `Paper` table only attaches to that
   `Base` when `models/paper.py` is imported. So you must
   `from src.models.paper import Paper` *before* calling `create_all` /
   `make_database()`, or the `papers` table won't exist. (This is the exact
   issue seen in the arxiv-integration notebook.)

2. **All package directories now have `__init__.py`.** Earlier versions
   relied on namespace-package behavior for `services/`, `services/arxiv/`,
   `services/pdf_parser/`, and `schemas/arxiv/`. They've all been given
   empty `__init__.py` files, so the project now packages cleanly for
   installation tools and avoids subtle pytest collection issues.

3. **Airflow DAG files: mostly populated, one still empty.**
   `common.py`, `fetching.py`, `setup.py`, `reporting.py` all have content
   and wire into the DAG `arxiv_paper_ingestion_and_indexing.py`.
   `indexing.py` is still a 0-byte stub — the OpenSearch indexing task
   isn't wired into the DAG yet, even though `services/opensearch/` is
   built.

4. **OpenSearch isn't in the runtime pipeline yet.** `services/opensearch/`
   exists end-to-end (client, factory, query builder, index config), but
   `metadata_fetcher.py` doesn't call it, and the Airflow DAG doesn't
   include an indexing task. Wiring it in is the next integration step:
   uncomment the `opensearch_client` line in
   `airflow/dags/arxiv_ingestion/common.py`, fill in `indexing.py`, and
   add `index_task` to the DAG between `fetch` and `report`.

---
*Regenerate this map after adding modules or changing import wiring.*
