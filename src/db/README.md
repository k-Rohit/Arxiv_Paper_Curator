# `src/db/` — Database layer

The bottom of the dependency stack. Owns the database connection lifecycle
(connect / get sessions / shut down) and provides the SQLAlchemy `Base` that
ORM models attach to.

Everything that talks to Postgres goes through this folder.

---

## Files

```
db/
├── factory.py
└── interfaces/
    ├── base.py         ← BaseDatabase (ABC), BaseRepository (ABC, unused)
    └── postgresql.py   ← PostgreSQLDatabase, Base (declarative_base())
```

| File | Defines | Purpose |
|---|---|---|
| `interfaces/base.py`       | `BaseDatabase` (ABC), `BaseRepository` (ABC) | The abstract contract: any DB impl must provide `startup`, `teardown`, `get_session` |
| `interfaces/postgresql.py` | `PostgreSQLDatabase`, `Base = declarative_base()` | Concrete Postgres implementation + the SQLAlchemy `Base` ORM models inherit from |
| `factory.py`               | `make_database() -> BaseDatabase` | One-liner constructor that reads config, builds the Postgres impl, and starts it |

---

## How it works

### 1. The interface (`base.py`)

`BaseDatabase` defines what *any* database backend must do:

```python
class BaseDatabase(ABC):
    @abstractmethod
    def startup(self) -> None: ...      # open connection pool
    @abstractmethod
    def teardown(self) -> None: ...     # close everything
    @abstractmethod
    def get_session(self) -> ContextManager[Session]: ...   # one transaction
```

Today only Postgres implements it, but the abstraction is here so you could
add SQLite or another backend later without touching callers.

`BaseRepository` is declared but **not used anywhere** — `PaperRepository`
doesn't inherit from it. Either delete it or wire it in later.

### 2. The Postgres implementation (`postgresql.py`)

`PostgreSQLDatabase`:

- `startup()` — builds the SQLAlchemy engine + sessionmaker from
  `PostgreSQLSettings`, then calls `Base.metadata.create_all(engine)` to
  create any tables that don't exist yet.
- `get_session()` — yields a session inside a context manager, auto-commits
  on success, rolls back on exception.

`Base = declarative_base()` — **this is the single registry that all ORM
models attach to.** When `src/models/paper.py` does `class Paper(Base):`,
that Paper class gets registered in `Base.metadata`. `create_all` then
sees it and issues the `CREATE TABLE papers (...)`.

### 3. The factory (`factory.py`)

`make_database()` wires everything together:

```
get_settings()                       ← from src.config
    → PostgreSQLSettings(...)        ← from src.schemas.database.config
    → PostgreSQLDatabase(config)     ← from .interfaces.postgresql
    → database.startup()             ← connects + create_all
    → return database
```

Callers never construct `PostgreSQLDatabase` directly — they call
`make_database()`. That's the single seam where "the app starts using the
DB."

---

## Dependencies

**This folder imports from:**

- `src.config.get_settings` — to read DB URL, pool size, etc.
- `src.schemas.database.config.PostgreSQLSettings` — the Pydantic settings
  type the factory builds from `get_settings()` output.
- External: `sqlalchemy`.

**This folder is imported by:**

- `src.models.paper` — imports `Base` so `Paper` can attach to it.
- `src.repositories.paper` — indirectly, via the `Session` it receives.
- `airflow/dags/arxiv_ingestion/common.py` — calls `make_database()` in the
  service factory.
- Notebooks — call `make_database()` to interact with the DB directly.

---

## The "import Paper before make_database" gotcha

`Base` only knows about `Paper` if `models/paper.py` has been imported.
If you call `make_database()` (which runs `create_all`) before importing
`Paper`, the `papers` table won't get created. Always:

```python
from src.models.paper import Paper       # ← attaches Paper to Base.metadata
from src.db.factory import make_database

db = make_database()                     # now create_all sees Paper
```

This bites every time someone opens a notebook fresh. Worth remembering.
