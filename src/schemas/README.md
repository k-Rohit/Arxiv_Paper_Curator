# `src/schemas/` — Pydantic data shapes (validation & boundaries)

This folder defines **in-memory data structures** using Pydantic. They live
at the boundaries of the system — anywhere data enters from outside (arxiv
API, environment variables, parsed PDFs) or moves between layers.

They are **not** database tables. ORM/database table definitions live in
[`src/models/`](../models/). The two folders look similar but have different jobs:

- **`models/`** — what's stored in Postgres (SQLAlchemy)
- **`schemas/`** — what's validated/passed around in code (Pydantic)

A Pydantic schema guarantees that "by the time this object exists, its
fields have the right types and required values." It also auto-generates
JSON serialization for FastAPI responses.

---

## Layout

```
schemas/
├── arxiv/
│   └── paper.py        ← arxiv API + create-paper shapes
├── database/
│   └── config.py       ← PostgreSQL connection settings
└── pdf_parser/
    └── models.py       ← parsed-PDF shapes
```

| Sub-folder | Defines | Purpose |
|---|---|---|
| `arxiv/paper.py` | `ArxivPaper`, `PaperBase`, `PaperCreate` | Inputs and intermediate types for the paper ingestion flow |
| `database/config.py` | `PostgreSQLSettings` | Strongly-typed DB connection settings (host, pool, echo) |
| `pdf_parser/models.py` | `ParserType`, `PaperSection`, `PaperFigure`, `PaperTable`, `PdfContent`, `ArxivMetadata`, `ParsedPaper` | Structured representation of a parsed PDF |

---

## How each schema is used

### `arxiv/paper.py` — the three paper shapes

These three classes form the pipeline:

```
ArxivPaper      ← parsed straight from the arxiv API XML
    ↓ (combined with parsed PDF content)
PaperCreate     ← what the repository accepts for upsert
    ↓
Paper (ORM)     ← what's written to Postgres
```

- **`ArxivPaper`** — what `ArxivClient.fetch_papers()` returns. Plain
  metadata: id, title, authors, abstract, categories, dates, pdf_url.
- **`PaperBase`** — the shared core fields between API input and what gets
  stored. Pydantic inheritance hierarchy.
- **`PaperCreate`** — extends `PaperBase` with optional parsed-content
  fields (`raw_text`, `sections`, `references`, `parser_used`). This is
  what `MetadataFetcher` builds up before calling `repo.upsert(...)`.

Why split? Because metadata is fetched first; parsed content is added
later. `PaperCreate` makes the parsed fields **optional** so a paper can
be stored before its PDF is processed (and updated later).

### `database/config.py` — typed DB settings

Wraps the connection parameters in a Pydantic settings class so the DB
factory can't be called with the wrong shape:

```python
PostgreSQLSettings(
    database_url=settings.postgres_database_url,
    echo_sql=settings.postgres_echo_sql,
    pool_size=settings.postgres_pool_size,
    max_overflow=settings.postgres_max_overflow,
)
```

Built once inside `make_database()` from the central `Settings` object.

### `pdf_parser/models.py` — parsed-PDF structure

The PDF parser doesn't return a string; it returns a **structured** object:

- `PdfContent` — the whole parsed paper (the most important type here).
  Holds `raw_text`, `sections`, `figures`, `tables`, `parser_metadata`.
- `PaperSection`, `PaperFigure`, `PaperTable` — the structural pieces.
- `ParserType` — an `Enum` (currently only `DOCLING`).
- `ArxivMetadata`, `ParsedPaper` — used at the boundary between the parser
  and the metadata fetcher.

Why structured instead of plain text? Because RAG benefits from knowing
section boundaries, table locations, etc. — you can search "give me the
'Method' section of papers about X."

---

## Dependencies

**Imports from:** Pydantic only. **Nothing internal.** This is the
foundation layer; everything depends on it, it depends on nothing.

**Imported by:**

- `src.repositories.paper` — uses `PaperCreate` as the input type for
  `create` / `upsert`.
- `src.db.factory` — uses `PostgreSQLSettings`.
- `src.db.interfaces.postgresql` — uses `PostgreSQLSettings`.
- `src.services.arxiv.client` — produces `ArxivPaper` instances.
- `src.services.metadata_fetcher` — consumes all three sub-schemas.
- `src.services.pdf_parser.parser` and `.docling_parser` — produce
  `PdfContent`.

---

## Why schemas as a separate folder

Three reasons:

1. **Single source of truth.** When the arxiv input changes shape (a new
   field), you update one Pydantic class. Every consumer is type-checked
   against it.
2. **No SQLAlchemy/Pydantic mixing.** Models do DB. Schemas do everything
   else. Don't be tempted to add `Column(...)` to a Pydantic class.
3. **Free serialization for FastAPI.** Pydantic models are JSON-serializable
   out of the box. When you add an API endpoint that returns papers, you
   return a `PaperCreate` (or a slim response variant) and FastAPI handles
   the JSON encoding.

---

## Where to put new schemas

Group by **domain**, not by where in code they're used:

- Arxiv-related shapes → `schemas/arxiv/`
- Database/settings shapes → `schemas/database/`
- PDF-parsing shapes → `schemas/pdf_parser/`
- OpenSearch (when you need it) → make `schemas/opensearch/`

Avoid one giant `schemas.py` — split by domain so each file stays small
and changes are localized.
