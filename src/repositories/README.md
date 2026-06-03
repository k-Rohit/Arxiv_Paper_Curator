# `src/repositories/` — Data access layer

The **only** place in the codebase that should query or mutate the database.
Everything above this layer (services, API, notebooks) goes through a
repository — they never construct SQLAlchemy queries directly.

This is the standard "Repository pattern": isolate persistence so the rest
of the app deals in domain objects and Pydantic schemas, not raw SQL.

---

## Files

```
repositories/
└── paper.py    ← PaperRepository
```

| File | Defines | What it manages |
|---|---|---|
| `paper.py` | `PaperRepository` | All CRUD + queries on the `papers` table |

---

## How it works

A repository is a thin class that takes a SQLAlchemy `Session` in its
constructor and exposes high-level methods (`create`, `get_by_arxiv_id`,
`upsert`, `get_processing_stats`, etc.) instead of raw query syntax.

```python
with database.get_session() as session:
    repo = PaperRepository(session)
    paper = repo.upsert(paper_create)        # PaperCreate → Paper
    stats = repo.get_processing_stats()      # → dict
```

The session is **passed in**, not created inside the repository. The
repository never owns the connection lifecycle — that's `database.get_session()`'s
job. This keeps the repository transactional: whatever called it controls
the surrounding transaction.

### The most important method: `upsert`

`upsert(paper_create) -> Paper` is the entry point used by the ingestion
pipeline. It implements "UPDATE if `arxiv_id` already exists, INSERT
otherwise":

```python
def upsert(self, paper_create: PaperCreate) -> Paper:
    existing = self.get_by_arxiv_id(paper_create.arxiv_id)
    if existing:
        for key, value in paper_create.model_dump(exclude_unset=True).items():
            setattr(existing, key, value)
        return self.update(existing)
    return self.create(paper_create)
```

This makes the write path **idempotent** — Airflow can re-run the DAG, the
pipeline can retry, the same paper can be fetched twice — and you always
end up with one row, never duplicates or unique-constraint crashes.

Note the `exclude_unset=True`: it only writes fields the caller actually
provided. So a fetch task that knows only the metadata won't overwrite
parsed `raw_text` that a later PDF-processing step put there.

### Read methods

A handful of named queries the rest of the app needs:

| Method | Purpose |
|---|---|
| `get_by_arxiv_id(arxiv_id)` | Lookup by external ID — used in upsert |
| `get_by_id(uuid)` | Lookup by internal primary key |
| `get_all(limit, offset)` | Paginated browse, newest published first |
| `get_count()` | Total row count |
| `get_processed_papers(...)` | Papers with `pdf_processed = True` |
| `get_unprocessed_papers(...)` | Papers without parsed content (work queue) |
| `get_papers_with_raw_text(...)` | Papers that have actual text content |
| `get_processing_stats()` | Aggregated counts + rates (for the daily report) |

These are SQLAlchemy 2.0-style queries (`select(Paper).where(...)`), wrapped
so callers never see SQLAlchemy directly.

---

## Dependencies

**Imports from:**

- `src.models.paper.Paper` — the ORM model it queries/mutates.
- `src.schemas.arxiv.paper.PaperCreate` — the Pydantic input it converts to
  ORM instances.
- External: `sqlalchemy`.

**Imported by:**

- `src.services.metadata_fetcher.MetadataFetcher` — the orchestrator that
  bulk-upserts after parsing.
- The Airflow `reporting.py` task — calls `get_processing_stats()` for the
  daily report.

---

## Why a repository at all?

Without it, every consumer would write `session.query(...)` or raw SQL,
duplicating logic and binding business code tightly to SQLAlchemy. With it:

- **One place** to change a query when the schema evolves.
- **Testable** — pass in a mock session.
- **Replaceable** — if you swap Postgres for another store later, only the
  repository changes.
- **Domain language** — `repo.upsert(paper)` reads naturally;
  `INSERT ... ON CONFLICT ... DO UPDATE` does not.

`BaseRepository` in [`src/db/interfaces/base.py`](../db/interfaces/base.py)
declares the abstract contract this pattern *should* satisfy, but
`PaperRepository` currently doesn't inherit from it — wire it up or delete
the abstract class when you decide which way to go.
