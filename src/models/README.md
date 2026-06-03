# `src/models/` — ORM (database table) definitions

SQLAlchemy models. Each class in this folder is a **Python representation of
a Postgres table**. This is *persistence* — what's actually stored on disk —
as opposed to `schemas/` which is in-memory data shapes for validation and
API responses.

---

## Files

```
models/
└── paper.py    ← class Paper(Base)
```

| File | Defines | Maps to table |
|---|---|---|
| `paper.py` | `Paper(Base)` | `papers` |

---

## How it works

A SQLAlchemy ORM model is a class that inherits from `Base` (the shared
declarative registry defined in [`src/db/interfaces/postgresql.py`](../db/interfaces/postgresql.py)).
Each `Column(...)` attribute on the class becomes a column in the table.

```python
class Paper(Base):
    __tablename__ = "papers"
    id = Column(UUID(...), primary_key=True, ...)
    arxiv_id = Column(String, unique=True, ...)
    title = Column(String, ...)
    abstract = Column(Text, ...)
    raw_text = Column(Text, ...)
    sections = Column(JSON, ...)         # parsed PDF sections
    pdf_processed = Column(Boolean, default=False)
    ...
```

When `Base.metadata.create_all(engine)` runs (inside `make_database()`),
SQLAlchemy looks at every class registered against `Base` and issues
`CREATE TABLE IF NOT EXISTS papers (...)` for each.

Each ORM instance is a **row**. Read rows by querying the model class,
mutate them by setting attributes, persist them by adding to a session and
committing.

---

## Dependencies

**Imports from:**

- `src.db.interfaces.postgresql.Base` — required, this is what registers
  the model in the metadata.
- External: `sqlalchemy`.

**Imported by:**

- `src.repositories.paper.PaperRepository` — the only place that should
  read/write `Paper` instances directly.
- Notebooks — when working with the DB directly.

---

## Models vs. schemas (the confusing pair)

| | `src/models/` | `src/schemas/` |
|---|---|---|
| Library | SQLAlchemy | Pydantic |
| Represents | A **database table** (persistence) | A **data shape** (validation / API I/O) |
| Lifetime | Lives in Postgres | Lives in memory for one request/operation |
| Example | `Paper` (the `papers` table) | `PaperCreate` (validated input dict from arxiv) |

The flow is: `ArxivPaper` (schema) → `PaperCreate` (schema) →
`Paper(**paper_create.model_dump())` (model) → committed to DB. The
repository does this conversion.

Never mix them — never put validation rules on a model, never put DB types
on a schema. They each have one job.

---

## The import-order gotcha (worth repeating)

For Paper to actually become a table:

1. The `Paper` class definition must execute (`from src.models.paper import Paper`).
2. *Then* `make_database()` runs `create_all`, sees `Paper` in
   `Base.metadata`, and issues the DDL.

If you flip the order — call `make_database()` before importing `Paper` —
the table won't exist. The notebooks and Airflow common.py both import
`Paper` before calling `make_database()` for this reason.
