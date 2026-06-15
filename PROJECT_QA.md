# Project Interview Q&A — Comprehensive Edition

> 150+ questions an interviewer could ask about this project, with detailed answers.
> Format: **Q → What / Why / How / Example / Senior follow-up**.
> Drill these. Cover the answer, recite the interview line out loud.

---

## TABLE OF CONTENTS

1. [Project Overview](#1-project-overview)
2. [Python Language](#2-python-language)
3. [Async Python](#3-async-python)
4. [Type Hints & Pydantic](#4-type-hints--pydantic)
5. [FastAPI](#5-fastapi)
6. [Databases & SQLAlchemy](#6-databases--sqlalchemy)
7. [Design Patterns](#7-design-patterns)
8. [OpenSearch & Search](#8-opensearch--search)
9. [Embeddings & Vectors](#9-embeddings--vectors)
10. [Chunking](#10-chunking)
11. [RAG](#11-rag)
12. [Agentic AI](#12-agentic-ai)
13. [Airflow & Orchestration](#13-airflow--orchestration)
14. [arXiv & PDF Parsing](#14-arxiv--pdf-parsing)
15. [Docker & Infrastructure](#15-docker--infrastructure)
16. [System Design & Scaling](#16-system-design--scaling)
17. [Trade-offs & Design Choices](#17-trade-offs--design-choices)
18. [Production & Operations](#18-production--operations)

---

# 1. Project Overview

## Q1.1: Walk me through your project end-to-end

**60-second pitch:**
> "I built an end-to-end production RAG pipeline for arXiv research papers. A daily Apache Airflow DAG fetches new papers, parses them with Docling for structured sections, chunks them section-aware (~500 words with 100-word overlap), embeds with OpenAI text-embedding-3-small reduced to 1024 dimensions, and indexes each chunk into OpenSearch with both text and vector fields. Search is hybrid — BM25 + k-NN fused via native RRF pipeline. A FastAPI service exposes `/search` and `/ask` endpoints; the `/ask` runs a LangGraph agent that retrieves top-K chunks and grounds an LLM with them, returning answers with citations. Tech: Python 3.12, async I/O throughout, SQLAlchemy + Postgres as source of truth, Docker Compose for the stack, idempotent upserts for retry safety."

## Q1.2: What problem does this solve?

ChatGPT works for one PDF but breaks at scale: 10,000 papers, daily updates, cost per query, no citations. RAG solves all four — pre-index documents once, retrieve only relevant chunks per query, ground the LLM with them. Cost drops 100×, every answer has verifiable citations, the system stays fresh via daily ingestion.

## Q1.3: Who would use this?

Researchers who need to stay current across thousands of papers, biotech R&D labs searching scientific literature, internal tooling at any company with proprietary documents. The pattern generalizes far beyond arxiv — legal contracts (Harvey), medical literature (OpenEvidence), customer support (Decagon).

## Q1.4: What was the hardest part?

Honestly: **indentation-disguised-as-logic bugs**. Multiple files had `return` statements wrongly nested inside `for` or `if` blocks, methods defined at module level instead of inside the class, etc. Each compiled cleanly but produced wrong results at runtime. Fix: enabled stricter ruff rules (`B`, `RET`, `SIM`, `UP`), and `python -m py_compile` after non-trivial edits.

## Q1.5: What would you change if you redid it?

1. **Add pyright** from day one — catches "method at module level" bugs ruff misses.
2. **Set up tests** earlier — empty `tests/` folder is a regret.
3. **Pick ONE embeddings provider** earlier and stick with it (I bounced between Jina and OpenAI mid-build).
4. **Use Alembic for migrations** instead of `create_all()` — better for schema evolution.
5. **Separate Settings vs ConfigDict pattern** uniformly across all settings classes from day one.

## Q1.6: How did you decide what to build first?

Followed a layered architecture: foundation (config, schemas, exceptions) → DB/repos → services (arxiv, pdf_parser, opensearch, embeddings) → orchestrator (metadata_fetcher) → Airflow tasks → FastAPI routes → agent layer. Each layer depends only on what's below. The order ensures I never had to mock missing dependencies.

## Q1.7: How is your code organized?

Layered architecture, dependencies flow downward only:
```
Entrypoints (FastAPI, Airflow DAGs)
    ↓
Orchestrators (metadata_fetcher, hybrid_indexer)
    ↓
Services (arxiv, pdf_parser, opensearch, embeddings)
    ↓
Data access (repositories, db)
    ↓
Foundation (config, exceptions, models, schemas)
```
Every service has a factory.py with `@lru_cache` singletons. Every folder has a README. Cross-cutting view is in PROJECT_MAP.md.

---

# 2. Python Language

## Q2.1: What is a class?

A blueprint for creating objects. Bundles data (attributes) and behavior (methods). Instances share the blueprint but each has their own data.

**Example:** `OpenSearchClient(host="localhost")` creates an instance. The class defines what `search_papers` does; the instance holds its specific host and connection.

## Q2.2: What is `self`?

The current instance, passed implicitly when calling methods. `self.x` reads from this specific instance; `x` would be a local variable.

```python
class Search:
    def __init__(self, client):
        self.client = client       # store on this instance
    def do(self):
        self.client.search(...)    # use this instance's client
```

## Q2.3: What is `__init__`?

The constructor — runs when you create an instance. Used to set initial attributes.

```python
class Paper:
    def __init__(self, arxiv_id, title):
        self.arxiv_id = arxiv_id
        self.title = title

p = Paper("...", "...")    # __init__ runs here
```

## Q2.4: What is a decorator?

A function that wraps another function to add behavior. Used with `@decorator_name`.

```python
@lru_cache(maxsize=1)
def make_client(): ...

# equivalent to:
make_client = lru_cache(maxsize=1)(make_client)
```

## Q2.5: What is `@lru_cache`?

Memoizes function results by arguments. First call runs the function; later calls with same args return the cached result.

**Why:** For no-arg factories = singleton. For arg-taking functions = avoid recomputation.

```python
@lru_cache(maxsize=1)
def make_pdf_parser():        # singleton — Docling loads ~1GB once
    return PDFParserService()
```

## Q2.6: What does `maxsize=1` mean in lru_cache?

The cache holds at most 1 result. Beyond that, the least-recently-used entry is evicted. For a no-arg function, this means singleton behavior.

## Q2.7: What is `__name__ == "__main__"`?

A guard that runs code only when the file is executed directly, not when imported. Lets a file work both as a library and a script.

```python
def helper(): ...
if __name__ == "__main__":
    helper()    # only runs via `python file.py`, not on import
```

## Q2.8: What is a generator?

A function that yields values lazily instead of returning a list. Memory-efficient for large sequences.

```python
def stream_papers():
    for paper in db.query(Paper):
        yield paper    # one at a time, not all in memory
```

## Q2.9: What is a context manager (`with` statement)?

An object that defines setup and teardown. `with` ensures teardown runs even on exception.

```python
with db.get_session() as session:
    session.add(paper)
    session.commit()    # session auto-closes after this block
```

Defined via `__enter__` / `__exit__` or `@contextmanager`.

## Q2.10: What is `*args` and `**kwargs`?

- `*args` = variable positional arguments (tuple).
- `**kwargs` = variable keyword arguments (dict).

```python
def trigger(*args, **kwargs):
    print(args)     # ("a", "b")
    print(kwargs)   # {"key": "val"}

trigger("a", "b", key="val")
```

## Q2.11: What's the difference between `==` and `is`?

- `==` compares **values**.
- `is` compares **identity** (same object in memory).

```python
a = [1, 2]
b = [1, 2]
a == b   # True (same values)
a is b   # False (different objects)
```

## Q2.12: What's the difference between a list and a tuple?

- **List:** mutable. `[1, 2, 3]`. Use for collections that change.
- **Tuple:** immutable. `(1, 2, 3)`. Use for fixed records, return values, dict keys.

```python
papers_data = [paper1, paper2]              # list — can append
chunk_id = (arxiv_id, chunk_index)          # tuple — fixed identity
```

## Q2.13: What is a dict comprehension?

Compact syntax to build dicts from iterables.

```python
sections_dict = {s.title: s.content for s in parsed.sections}
```
Equivalent to a for-loop + `result[key] = value`.

## Q2.14: Why the trailing underscore in `from_`?

`from` is a Python keyword. Can't be a variable name. Trailing underscore avoids the clash; `alias="from"` in Pydantic maps to the JSON name.

```python
from_: int = Field(0, alias="from")
```

## Q2.15: Why the leading underscore in `_client`?

Convention: "this is internal — don't access from outside the class." Not enforced by Python, but IDE autocomplete hides them and linters flag external access.

## Q2.16: What is namespace package vs regular package?

- **Regular package:** folder with `__init__.py`. Old-school.
- **Namespace package:** folder *without* `__init__.py`. Works in Python 3.3+ but can cause issues with packaging tools.

Recommendation: always add empty `__init__.py` for consistency.

## Q2.17: What is `sys.path`?

A list of directories Python searches when you import a module. Notebooks often need `sys.path.insert(0, project_root)` to find `src/`.

## Q2.18: What does `if __name__ != "__main__"` enable?

Lets your module **only export** its definitions when imported but **also be runnable** as a script (e.g., for quick CLI testing).

## Q2.19: What is `Optional[X]`?

Shorthand for `Union[X, None]` — "either X or None." Used for params that have a meaningful "absent" value.

```python
categories: Optional[List[str]] = None
```

## Q2.20: What is `Annotated`?

Type hint that attaches metadata to a type. Used by FastAPI for dependency injection.

```python
OpenSearchDep = Annotated[OpenSearchClient, Depends(get_opensearch_client)]
```
`Annotated[X, meta]` reads as "X, with this extra info." FastAPI inspects the metadata.

---

# 3. Async Python

## Q3.1: What is async/await?

Python's syntax for **I/O-bound concurrency without threads**. `async def` marks a coroutine; `await` yields control during I/O so the event loop can run other tasks.

```python
async def fetch(url):
    return await httpx.get(url)
```

## Q3.2: How does async actually work?

Single thread, single event loop. When you `await` an I/O operation, the coroutine pauses and the loop switches to other ready coroutines. When the I/O completes, the original coroutine resumes.

## Q3.3: When does async help and when doesn't it?

- **Helps:** I/O-bound code (network, disk, DB). While waiting, other tasks run.
- **Doesn't help:** CPU-bound code (math, parsing in pure Python). One thread = no parallelism.

For CPU-bound parallelism, use `multiprocessing` or libraries that release the GIL (NumPy, etc.).

## Q3.4: What is `asyncio.gather`?

Runs multiple coroutines concurrently, waits for all to finish, returns results in order.

```python
results = await asyncio.gather(
    fetch(url1), fetch(url2), fetch(url3),
)   # all 3 run in parallel
```

## Q3.5: What is `asyncio.Semaphore`?

Throttle for concurrent operations. "At most N coroutines may hold this at once."

```python
sem = asyncio.Semaphore(5)         # max 5 concurrent
async def download(url):
    async with sem:
        return await httpx.get(url)
```
Our PDF downloader uses this to cap concurrent arxiv requests.

## Q3.6: What is `asyncio.run` and when can't you use it?

`asyncio.run(coroutine)` runs a coroutine in a fresh event loop. **Cannot** be called from inside an already-running event loop (Jupyter, FastAPI routes). Use `await` directly instead.

## Q3.7: Why must `embed_text` be `async def`?

It calls `self._client.embeddings.create(...)`, which is a coroutine. Calling a coroutine without `await` doesn't run it — just creates a coroutine object. To `await` something, the calling function must be `async`.

## Q3.8: How does Airflow handle async tasks?

Airflow PythonOperator expects **sync** callables. To call async code, wrap with `asyncio.run`:

```python
def fetch_daily_papers(**context):
    results = asyncio.run(run_paper_ingestion_pipeline(...))
```
The sync task creates an event loop for the async pipeline.

## Q3.9: Why does our embed_batch use sequential `await` in a `for` loop instead of `asyncio.gather`?

Because OpenAI rate-limits per API key. Parallelizing within one client doesn't help — you hit the limit faster. Sequential batching keeps us within the rate limit while still doing one network call per batch.

## Q3.10: What's the cost of `await`?

`await` itself is cheap (~microseconds). The cost is the actual I/O it waits for. The win is during that wait, other coroutines run instead of the thread blocking.

---

# 4. Type Hints & Pydantic

## Q4.1: Are type hints enforced at runtime?

**No.** Python ignores them at runtime. Tools (mypy, pyright, Pydantic, FastAPI) use them. So `def f(x: int)` won't crash if you pass a string — unless the function logic itself fails or you have Pydantic validation.

## Q4.2: What is Pydantic?

Data validation library. Define a class with type-hinted fields; Pydantic validates on construction. Raises `ValidationError` for invalid data.

```python
class AskRequest(BaseModel):
    query: str
    top_k: int = Field(5, ge=1, le=10)
```

## Q4.3: BaseModel vs BaseSettings?

- **BaseModel:** plain data validation. For HTTP request bodies, parsed PDFs, internal types.
- **BaseSettings:** also reads from env vars / `.env`. For app configuration.

## Q4.4: ConfigDict vs SettingsConfigDict?

Same pair:
- **ConfigDict** for `BaseModel`.
- **SettingsConfigDict** for `BaseSettings` (adds `env_file`, `env_prefix`, `case_sensitive`, etc.).

## Q4.5: What is `model_config`?

Pydantic v2's way to configure model behavior (validation, serialization, schema). Replaces v1's inner `class Config`.

```python
class AskRequest(BaseModel):
    query: str
    model_config = ConfigDict(json_schema_extra={"example": {...}})
```

## Q4.6: What is `json_schema_extra`?

Adds example values to the auto-generated JSON schema. FastAPI uses this for the `/docs` "Try it out" page.

## Q4.7: What is `env_prefix`?

Namespace for env-var loading in BaseSettings. `env_prefix="OPENSEARCH__"` means Pydantic looks for `OPENSEARCH__HOST` to populate `host`.

## Q4.8: What is `extra="ignore"`?

Tells Pydantic to silently drop unknown fields. Used for shared `.env` files where each settings class only owns a subset of variables.

## Q4.9: What is `frozen=True`?

Makes the model immutable after construction. Attempting to set an attribute raises an error. Guardrail for settings.

## Q4.10: What is `Field(...)`?

Pydantic's way to add validation rules to a field: `min_length`, `max_length`, `ge`, `le`, `default`, `description`, `examples`, `alias`.

```python
top_k: int = Field(5, ge=1, le=10)
```

## Q4.11: How does FastAPI know to validate request bodies?

It inspects the route function's signature. If a parameter is a Pydantic model, FastAPI deserializes the JSON body into that type and validates it before calling your function.

```python
@app.post("/ask")
def ask(req: AskRequest):  # FastAPI validates here
    ...
```

## Q4.12: What is `populate_by_name`?

Pydantic option that lets you construct a model using either the field name OR its alias. Without it, only alias works.

```python
SearchRequest(from_=10)       # works (Python name)
SearchRequest(**{"from": 10}) # works (alias)
```

## Q4.13: What is `model_dump`?

Pydantic v2 method that serializes a model to a dict. v1 called this `dict()`.

```python
req.model_dump()              # {"query": "...", "top_k": 5}
req.model_dump_json()         # JSON string
req.model_dump(by_alias=True) # use aliases for keys
```

## Q4.14: What is `model_validate`?

Pydantic v2 method to validate raw data (dict, JSON) into a model instance. v1 called this `parse_obj` / `parse_raw`.

```python
req = AskRequest.model_validate({"query": "hello"})
```

## Q4.15: What is `exclude_unset` in `model_dump`?

Returns only the fields the user explicitly set, not defaults. Critical for PATCH-style updates where you don't want defaults to overwrite existing data.

```python
paper_create.model_dump(exclude_unset=True)
# only fields actually passed by the caller
```

---

# 5. FastAPI

## Q5.1: What is FastAPI?

Modern Python web framework. Type-hint driven, auto-generates OpenAPI docs, validates requests/responses via Pydantic, async-native.

## Q5.2: Why FastAPI over Flask?

- Native async (Flask is sync-first; async is bolted on).
- Auto-validation via Pydantic.
- Auto-generated `/docs` UI.
- Better performance (Starlette + uvicorn).
- Type hints make routes self-documenting.

## Q5.3: What is uvicorn?

ASGI server that runs FastAPI apps. ASGI is the async equivalent of WSGI.

```bash
uvicorn src.main:app --reload
```

## Q5.4: What is `--reload`?

Auto-restart on file changes. Dev-only. Don't use in production.

## Q5.5: What is the FastAPI lifespan?

A context manager that runs at app startup and shutdown. Replacement for the older `@app.on_event("startup")` / `"shutdown"` decorators.

```python
@asynccontextmanager
async def lifespan(app):
    # startup
    app.state.db = make_database()
    yield
    # shutdown
    app.state.db.teardown()
```

## Q5.6: What is `app.state`?

Per-app storage that survives across requests. Set in `lifespan`, read on every request via `request.app.state.x`. Standard place for singletons (DB, OpenSearch client).

## Q5.7: What is dependency injection in FastAPI?

Pattern where routes declare what services they need as parameters; FastAPI injects them automatically via `Depends()`.

```python
def search(opensearch: OpenSearchDep):  # FastAPI injects
    ...
```

## Q5.8: How does `Depends()` work internally?

When FastAPI processes a request, it inspects route parameters. For each `Annotated[X, Depends(getter)]`, it calls `getter()` and passes the result as that parameter. Caches per-request.

## Q5.9: What does `dependencies.py` do in this project?

Centralizes DI:
1. Getter functions pull services off `app.state`.
2. `Annotated` type aliases (`OpenSearchDep`) let routes declare cleanly.
3. Routes import the aliases and use them as parameters.

## Q5.10: What is middleware?

Code that runs before/after every request. Cross-cutting concerns — logging, auth, timing, error handling.

```python
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        logger.info(f"{request.method} {request.url.path} ({(time.perf_counter()-start)*1000:.1f}ms)")
        return response

app.add_middleware(RequestLoggingMiddleware)
```

## Q5.11: What is a router?

A modular collection of routes. Split a large API into multiple files; mount them via `app.include_router(...)`.

```python
# routers/search.py
router = APIRouter()
@router.post("/search")
def search(...): ...

# main.py
app.include_router(router, prefix="/api/v1")
```

## Q5.12: What is OpenAPI?

Machine-readable description of an HTTP API. FastAPI auto-generates it. Tools (Swagger UI, Postman, SDK generators) consume it.

## Q5.13: What does FastAPI's `/docs` page do?

Renders the OpenAPI spec as an interactive UI. Lets you see endpoints, request shapes, response shapes, and "Try it out" — send real requests from the browser.

## Q5.14: What is `response_model=`?

Tells FastAPI what shape to validate/serialize the response as. Strips extra fields, validates types, generates docs.

```python
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    ...
```

## Q5.15: How do you handle errors in FastAPI?

`raise HTTPException(status_code=404, detail="Not found")` → returns 404 with JSON body. For broader error handling, use middleware or `@app.exception_handler(...)`.

## Q5.16: What's the difference between path, query, and body params?

```python
@app.get("/papers/{arxiv_id}")          # path param: arxiv_id
def get_paper(
    arxiv_id: str,                       # in URL path
    include_chunks: bool = False,        # query param: ?include_chunks=true
    body: SomeBody,                      # request body (JSON)
):
```
FastAPI infers from type annotation and presence in path.

## Q5.17: How does FastAPI handle async route functions?

Routes can be `def` (sync) or `async def`. Async routes run on the event loop natively. Sync routes run in a threadpool so they don't block the loop.

## Q5.18: What is CORS?

Cross-Origin Resource Sharing. Browser security feature that blocks requests from a different origin (domain/port). Fix: add CORS middleware specifying allowed origins.

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
```

## Q5.19: How would you secure these endpoints?

- API keys via `Depends` that checks a header.
- OAuth2 / JWT via FastAPI's security utilities.
- Rate limiting via middleware (e.g., slowapi).

Today this project is unauthenticated — fine for local dev, not for production.

## Q5.20: How does FastAPI compare to Django REST Framework?

| | FastAPI | DRF |
|---|---|---|
| Style | Type-hint driven | Class-based views |
| Async | Native | Bolted-on |
| Validation | Pydantic | DRF serializers |
| ORM coupling | None (works with any) | Tightly tied to Django ORM |
| Speed | Faster | Slower |
| Maturity | Newer | Mature, batteries-included |

---

# 6. Databases & SQLAlchemy

## Q6.1: What is SQLAlchemy?

Python's most popular library for working with SQL databases. Two layers: Core (low-level query builder) and ORM (object mapper).

## Q6.2: What is an ORM?

Object-Relational Mapper. Maps Python classes to SQL tables. You work with objects; the ORM generates SQL.

## Q6.3: What is a session?

SQLAlchemy's unit of work. A workspace where you stage changes before committing. Auto-rollback on exception.

```python
with db.get_session() as session:
    session.add(paper)
    session.commit()    # SQL issued here
```

## Q6.4: What is a transaction?

A group of DB operations treated as one atomic unit. Either all succeed (commit) or all undo (rollback). Sessions manage transactions.

## Q6.5: What are ACID properties?

- **Atomicity:** all-or-nothing.
- **Consistency:** valid state to valid state.
- **Isolation:** concurrent transactions don't see each other's partial state.
- **Durability:** committed data survives crashes.

Postgres provides all four; OpenSearch is weaker on consistency/isolation.

## Q6.6: What is `Base = declarative_base()`?

SQLAlchemy registry. Every model class that inherits from `Base` gets added to `Base.metadata`. `create_all` reads metadata to issue CREATE TABLE statements.

## Q6.7: What is the import-order gotcha?

`Paper` only attaches to `Base.metadata` when its file is imported. If you call `create_all` before importing `Paper`, the `papers` table won't get created.

**Fix:** always import models before calling `make_database()`.

## Q6.8: What is `Column`?

Defines a database column on an ORM model. Type + constraints + indexes.

```python
arxiv_id = Column(String, unique=True, nullable=False, index=True)
```

## Q6.9: What is a primary key?

Unique identifier for a row. SQL enforces uniqueness. In our `Paper` model: `id = Column(UUID, primary_key=True)`.

## Q6.10: What is `unique=True` vs `primary_key=True`?

- **Primary key:** one per table, identifies the row. Auto-creates an index.
- **Unique:** can have many, just enforces no duplicates. Also creates an index.

Our `Paper` has `id` (PK) and `arxiv_id` (unique). PK is internal; arxiv_id is the external identifier.

## Q6.11: What is the repository pattern?

A class that owns all DB operations for one entity. Services call repo methods instead of writing SQL.

```python
class PaperRepository:
    def upsert(self, paper_data): ...
    def get_by_arxiv_id(self, arxiv_id): ...
```

## Q6.12: Why repository pattern over direct queries in services?

- **Single source of truth** for queries.
- **Testable** — mock the repo.
- **Decouples** business logic from SQL.
- **Reusable** across multiple services/DAGs.

## Q6.13: What is upsert?

"Update if exists, insert if not." Single idempotent operation. Critical for pipelines that retry.

```python
def upsert(paper_data):
    existing = get_by_arxiv_id(paper_data.arxiv_id)
    if existing: update(existing, paper_data)
    else: create(paper_data)
```

## Q6.14: Why is upsert important for Airflow pipelines?

Airflow retries failed tasks. Same input can run twice. With INSERT only, the retry crashes on a unique-key collision. With upsert, the retry produces the same end state safely.

## Q6.15: What is a connection pool?

A set of pre-opened DB connections shared across requests. Avoids the ~10-50ms cost of opening a new connection per request.

```python
PostgreSQLSettings(pool_size=20, max_overflow=0)
# 20 connections kept ready; no overflow allowed
```

## Q6.16: What's the difference between `pool_size` and `max_overflow`?

- **pool_size:** persistent connections always available.
- **max_overflow:** extra connections allowed beyond pool_size during peak load. Closed when load drops.

## Q6.17: What is N+1 query problem?

Loading a list of objects, then making a separate query for each object's related data. N=1 list query + N child queries = bad scaling.

**Fix:** eager loading (`joinedload`, `selectinload`) or batch fetches.

## Q6.18: How would you migrate the schema?

Alembic — SQLAlchemy's migration tool. Generates migration scripts from model changes. Applied in order, reversible.

Our current code uses `Base.metadata.create_all()` which only creates *new* tables — won't alter existing ones. For production, Alembic.

## Q6.19: What is `session.refresh(obj)`?

After commit, re-read the row from the DB to populate server-generated columns (auto-incrementing IDs, timestamps).

```python
session.add(paper)
session.commit()
session.refresh(paper)    # now paper.id is populated
```

## Q6.20: What's the difference between `session.add()` and `session.merge()`?

- **add:** stages a new INSERT.
- **merge:** combines the given object with whatever is in the session (handles "is this already tracked?").

We use `add` because our repo explicitly checks existence first.

---

# 7. Design Patterns

## Q7.1: What is the singleton pattern?

One instance per app. Use for: connection pools, ML models, configs.

**Python idiom:** `@lru_cache(maxsize=1)` on a factory function.

## Q7.2: What is the factory pattern?

A function that constructs and configures an object. Callers don't know about settings, defaults, wiring.

```python
def make_opensearch_client():
    settings = get_settings()
    return OpenSearchClient(host=settings.opensearch.host)
```

## Q7.3: What is dependency injection?

Pass dependencies in instead of constructing them inside. Makes code testable, swappable, single-responsibility.

```python
class Search:
    def __init__(self, opensearch):   # injected
        self.opensearch = opensearch
```

## Q7.4: What is the repository pattern?

One class per entity owning all DB operations. Services use the repo; never write SQL directly.

## Q7.5: What is the adapter pattern?

A wrapper that translates one interface to another. Your `OpenAIEmbeddingsClient` is an adapter — it translates `embed_text(str) -> List[float]` to OpenAI SDK calls. Could swap for `JinaEmbeddingsClient` with the same interface.

## Q7.6: What is the facade pattern?

A single class that hides complexity behind a simple interface. `PDFParserService` is a facade over `DoclingParser` — callers just see `parse_pdf()`.

## Q7.7: What is composition vs inheritance?

- **Composition:** "has-a." Object contains another. Flexible.
- **Inheritance:** "is-a." Subclass extends parent. Tightly coupled.

`PDFParserService` *has* a `DoclingParser` (composition). `PostgreSQLDatabase` *is-a* `BaseDatabase` (inheritance).

Modern advice: prefer composition.

## Q7.8: What is SOLID?

Five OOP principles:
- **S**ingle responsibility: one reason to change.
- **O**pen/closed: open to extension, closed to modification.
- **L**iskov substitution: subclasses substitutable for base.
- **I**nterface segregation: small focused interfaces.
- **D**ependency inversion: depend on abstractions, not concretions.

Our project follows S (clear layers), D (services depend on `BaseDatabase`, not `PostgreSQLDatabase`).

## Q7.9: Where in this project do you see SRP (Single Responsibility)?

Every layer:
- Repository: only DB queries.
- Service: business logic, no DB or HTTP.
- Route: HTTP I/O, no business logic.
- Settings: only config loading.

## Q7.10: How does DI improve testability?

```python
# Test
fake_client = MockOpenSearchClient()
search = Search(opensearch=fake_client)   # pass fake
search.do()
assert fake_client.was_called

# vs without DI:
# Search creates its own client → must monkey-patch
```

## Q7.11: What's the difference between factory function and factory class?

Both serve the same purpose. Function is simpler:
```python
def make_x() -> X: ...
```

Class is appropriate when the factory itself has state or methods (`MyFactoryClass.build_a()`, `MyFactoryClass.build_b()`).

For our singletons, function + `@lru_cache` is enough.

## Q7.12: Is there a downside to singletons?

Yes:
- **Hidden global state** — harder to reason about.
- **Hard to test** in isolation (must clear cache between tests).
- **Tight coupling** — everyone shares the same instance.

For expensive-to-construct services it's worth it. For trivial objects, just instantiate per-use.

## Q7.13: Why use `@lru_cache` over a module-level global?

```python
# Module global — runs at import time
_client = OpenSearchClient(host="...")

# vs. @lru_cache — lazy, runs first time make_x() is called
@lru_cache
def make_x(): return OpenSearchClient(host="...")
```

`@lru_cache` is lazy (no work at import), cacheable per-process, easier to test (can clear cache), pickle-safe.

## Q7.14: What's the strategy pattern?

Encapsulate different algorithms behind the same interface; pick at runtime. Example: chunking strategies.

```python
class Chunker:
    def chunk(self, text): ...

class WordBasedChunker(Chunker): ...
class SectionAwareChunker(Chunker): ...
```

Caller code picks one based on config.

## Q7.15: What design patterns from the GoF book do you use?

- **Singleton** — service factories.
- **Factory** — make_X() functions.
- **Adapter** — embeddings client wrapping SDK.
- **Facade** — PDFParserService, MetadataFetcher.
- **Repository** — paper.py.
- **Strategy** — chunking approach selection.

---

# 8. OpenSearch & Search

## Q8.1: What is OpenSearch?

Lucene-backed distributed search engine. Open-source fork of Elasticsearch. Used for full-text search, log analytics, vector search.

## Q8.2: What's the difference between OpenSearch and Elasticsearch?

OpenSearch is the AWS-maintained fork after Elastic changed the Elasticsearch license. Mostly compatible. AWS prefers OpenSearch; many open-source users moved to it.

## Q8.3: What is an inverted index?

Data structure mapping **word → list of docs containing it**. Foundation of full-text search. Makes word lookup O(1) instead of scanning every doc.

## Q8.4: What is BM25?

Standard relevance-ranking algorithm. Better than naive TF-IDF — accounts for term frequency, IDF (rarity), and doc length normalization.

## Q8.5: What is `multi_match`?

Query that searches the same text across multiple fields, with optional per-field boosts.

```json
{"multi_match": {
  "query": "transformer",
  "fields": ["title^3", "abstract^2", "chunk_text^1"]
}}
```

## Q8.6: What is field boosting (`^N`)?

Per-field score multiplier. `title^3` means title hits contribute 3× to the relevance score.

## Q8.7: What is a `bool` query?

OpenSearch's logical combiner. Four slots:
- `must`: AND, scored.
- `filter`: AND, unscored.
- `should`: OR, scored.
- `must_not`: NOT.

## Q8.8: What's the difference between `must` and `filter`?

Both make docs required to match. Difference: `must` contributes to BM25 score; `filter` is yes/no only (no scoring, cacheable, faster).

Rule: text searches in `must`, restrictions in `filter`.

## Q8.9: What is `term` vs `match`?

- **`term`:** exact match. For `keyword` fields (no analysis). `{"term": {"category": "cs.AI"}}`.
- **`match`:** analyzed match (tokenized, lowercased). For `text` fields. `{"match": {"title": "transformer"}}`.

## Q8.10: What is `_source`?

The original JSON document as stored. Per-query you can include/exclude fields. We exclude `embedding` from search responses to keep them small.

## Q8.11: What is highlighting?

Snippets of matched text with terms wrapped in HTML tags. Lets the UI show *why* a doc matched.

## Q8.12: What is `track_total_hits`?

Controls whether OpenSearch returns the exact total. Default caps at 10K for speed. Set `true` for exact counts (slower).

## Q8.13: What is a mapping?

The index schema. Declares fields, their types, analyzers, special features (k-NN, etc.).

```json
{"properties": {
  "chunk_text": {"type": "text", "analyzer": "standard"},
  "embedding":  {"type": "knn_vector", "dimension": 1024}
}}
```

## Q8.14: What's the difference between `text` and `keyword` field types?

- **text:** analyzed (tokenized, lowercased, stopwords removed). For full-text search.
- **keyword:** stored verbatim. For exact matching, filtering, aggregations.

## Q8.15: What is an analyzer?

A pipeline that transforms text at index time AND query time. Tokenizer (split on whitespace) + filters (lowercase, stem, stopwords).

```json
{"text_analyzer": {
  "type": "custom",
  "tokenizer": "standard",
  "filter": ["lowercase", "stop", "snowball"]
}}
```

## Q8.16: What is the analysis difference between BM25 and vector search?

- **BM25 over text fields:** uses analyzed tokens (lowercased, stemmed) for matching.
- **Vector search over embeddings:** uses raw float vectors. Analysis doesn't apply.

## Q8.17: What is vector search?

Find documents whose embedding vectors are closest to the query vector. Uses distance metrics (cosine, euclidean, dot product).

## Q8.18: What is `knn_vector` field type?

OpenSearch type for storing dense vectors. Requires `dimension`, optionally `method` (HNSW) and `space_type` (cosinesimil, l2, etc.).

## Q8.19: What is HNSW?

Hierarchical Navigable Small World — approximate nearest-neighbor algorithm. Multi-layer graph, greedy search. Trades ~1% recall for 100× speedup vs. exact search.

## Q8.20: What is hybrid search?

Run BM25 + vector search in parallel, fuse results. Best of both: keyword precision + semantic recall.

## Q8.21: What is RRF?

Reciprocal Rank Fusion. Combine multiple ranked lists by summing `1/(60+rank)` per doc per list. No score normalization needed. Standard for hybrid search.

## Q8.22: Why is RRF better than weighted average?

Weighted average requires score normalization (BM25 vs cosine scales are wildly different) and weight tuning per query. RRF works on ranks — no normalization, no tuning, robust across queries.

## Q8.23: What is a search pipeline?

OpenSearch construct that post-processes search results. Used for fusion (RRF), reranking, etc. Created once at setup, applied per search via `?search_pipeline=<id>`.

## Q8.24: What's the difference between an index and a document?

- **Index:** a named collection of documents (like a SQL table).
- **Document:** one JSON record inside an index (like a SQL row).

Word "index" is overloaded — also means "the inverted-index data structure built per field."

## Q8.25: What's a shard?

A horizontal partition of an index. Lets OpenSearch distribute data across nodes for scale. Our local setup uses 1 shard (single-node).

## Q8.26: What's a replica?

A copy of a shard for redundancy. We use 0 replicas locally; production might use 1-2 for fault tolerance.

## Q8.27: How would you scale OpenSearch for 1B documents?

- Multi-node cluster with sharding.
- Replicas for fault tolerance.
- Tune HNSW (`ef_construction`, `m`) for memory vs recall.
- Use `keyword` fields for filterable attributes (cacheable).
- Cache hot queries.
- Consider managed: AWS OpenSearch Service, Bonsai.

## Q8.28: What's `bulk` indexing?

API for sending many docs in one HTTP call. Much faster than individual indexing.

```python
helpers.bulk(client, actions, refresh=True)
```

Our `bulk_index_chunks` uses this.

## Q8.29: What is `refresh=True`?

Forces OpenSearch to immediately make the indexed docs searchable. Without it, there's a delay (~1 sec). Use for tests/notebooks; avoid in production write-heavy paths (it hurts throughput).

## Q8.30: How is the search query built in your project?

`QueryBuilder` class constructs the JSON body. Takes query + size + categories + flags. Methods like `_build_query`, `_build_filters`, `_build_highlight` produce sub-dicts that get assembled in `build()`.

---

# 9. Embeddings & Vectors

## Q9.1: What is an embedding?

A list of numbers (vector) representing the meaning of text in high-dimensional space. Similar meanings → close vectors.

## Q9.2: How are embeddings trained?

Models trained on huge corpora with contrastive objectives — pairs of similar text get pushed close; unrelated pairs get pushed apart. Resulting model encodes semantic relationships.

## Q9.3: What's `text-embedding-3-small`?

OpenAI's embedding model. Native 1536 dimensions, reducible via `dimensions=N` param (Matryoshka representation). Strong quality, cheap ($0.02/1M tokens).

## Q9.4: Why 1024 dimensions instead of 1536?

- 33% smaller index (storage + speed).
- ~4% quality loss.
- Matches our existing OpenSearch index config (was 1024 for Jina v3).

## Q9.5: What is Matryoshka representation?

Embedding models trained so that **prefixes** of the full vector are also valid embeddings. `vec[:1024]` retains most of the signal of `vec[:1536]`.

OpenAI v3 models use this — that's why `dimensions=N` works server-side.

## Q9.6: What's the difference between dense and sparse embeddings?

- **Dense:** every dim has a value (e.g., 1024 floats). What we use.
- **Sparse:** mostly zeros, few non-zero values. SPLADE, BM25-as-vector.

Sparse vectors can be hybrid-search-friendly (interpretable, BM25-like) but less common.

## Q9.7: What is cosine similarity?

Distance metric between vectors. Measures angle, not magnitude. Range -1 to 1; higher = more similar.

`cos(θ) = (a · b) / (|a| × |b|)`

Standard for text embeddings.

## Q9.8: Why cosine over Euclidean for text?

Embeddings can have different magnitudes. Cosine focuses on direction (meaning). Euclidean conflates magnitude differences with meaning differences.

## Q9.9: What is dot product similarity?

`a · b` — sum of element-wise products. Equivalent to cosine if vectors are normalized. Faster to compute (no division).

## Q9.10: Why do you batch embeddings?

Network round-trips dominate. One API call for 100 inputs ≈ 100× faster than 100 individual calls.

## Q9.11: What's OpenAI's per-request limit?

~2048 inputs per call. Our `embed_batch` splits larger inputs into chunks of `settings.batch_size` (default 100, safer).

## Q9.12: What's the cost of embedding 1000 papers?

`text-embedding-3-small`: $0.02 per 1M tokens.
- ~20 chunks/paper × ~700 tokens/chunk = ~14K tokens/paper.
- 1000 papers × 14K = 14M tokens = $0.28.

Cheap compared to LLM costs.

## Q9.13: How do you ensure embedding-query and embedding-document use the same model?

We track `embedding_model` as a field on each chunk doc. Critical: changing the embedding model means re-embedding everything. Mixing models produces nonsense similarity.

## Q9.14: What is query embedding?

The same model that embeds documents also embeds the user's search query at search time. Same vector space → can compare.

## Q9.15: What's the cost difference between OpenAI and local embeddings?

| Model | Cost per 1M tokens | Quality |
|---|---|---|
| OpenAI `text-embedding-3-small` | $0.02 | Strong |
| Cohere | $0.13 | Strong |
| `sentence-transformers/all-MiniLM-L6-v2` (local) | $0 | OK for small projects |
| Jina v3 (API) | $0.02 | Strong |

Local saves money but needs GPU for speed; API is simpler.

---

# 10. Chunking

## Q10.1: Why chunk documents at all?

1. **Embedding quality** — embedding a 30-page paper is mush; embedding a paragraph captures specific meaning.
2. **Retrieval precision** — return the exact paragraph, not the whole doc.
3. **LLM context limits** — can't feed whole 60-page papers into the model.

## Q10.2: What's the right chunk size?

Standard: 300-800 words. Below: too little context. Above: blurry embeddings. We use 600 with 100 overlap.

## Q10.3: What is section-aware chunking?

Use document structure (sections from Docling) instead of fixed word splits. Better — sections are coherent semantic units.

## Q10.4: How does your section-aware chunker handle small sections?

Two-stage merging:
1. Iterate sections; collect consecutive small (<100 words) sections in a buffer; flush when interrupted by large section or end.
2. When flushing: if combined buffer + header is still small AND a previous chunk exists, merge into it (mutate in place). Otherwise, form a new chunk.

## Q10.5: What's chunk overlap?

Consecutive chunks share some words. Prevents key sentences from being split at chunk boundaries.

Stride = chunk_size - overlap. So with 600-word chunks and 100-word overlap, each chunk starts 500 words after the previous.

## Q10.6: What other chunking strategies exist?

- **Fixed-word** (e.g., 500 words).
- **Sentence-based** (split on sentences, group N).
- **Section-aware** (uses document structure).
- **Semantic chunking** (group based on embedding similarity of adjacent sentences).
- **Recursive splitting** (LangChain `RecursiveCharacterTextSplitter`).

## Q10.7: Why didn't you use LangChain's text splitter?

LangChain treats text as a flat string. Throwing away the section structure that Docling gave us would be wasteful. Custom 200-line section-aware chunker > generic library.

## Q10.8: How do you decide chunk size?

Trade-off: longer chunks have more context for the LLM but blurrier embeddings and less retrieval precision. Empirically, 500-800 words is the sweet spot for academic content.

## Q10.9: What's "chunk header"?

Prepending title + abstract to every chunk. Gives each chunk paper-level context even when it's just a paragraph from page 14.

## Q10.10: Could overlap cause duplicate retrieval?

Yes — same content appears in two adjacent chunks. Search might return both. Mitigations:
- Deduplicate by paper_id at top of search results.
- Or accept the redundancy (the LLM can handle context with some repetition).

---

# 11. RAG

## Q11.1: What is RAG?

Retrieval-Augmented Generation. Retrieve relevant chunks from a knowledge base, ground an LLM in them, return an answer.

## Q11.2: Why RAG over fine-tuning?

- **Cheap:** no model training cost.
- **Fresh:** index updates immediately reflect in answers.
- **Verifiable:** citations link back to source.
- **Private data:** keep documents in your own infra.

Fine-tuning bakes knowledge into weights — slow to update, expensive, hard to verify.

## Q11.3: What are the parts of a RAG system?

1. **Ingestion** — fetch, parse, chunk documents.
2. **Embedding** — turn chunks into vectors.
3. **Indexing** — store chunks + vectors in a search engine.
4. **Retrieval** — embed user query, search for top-K chunks.
5. **Generation** — prompt LLM with chunks as context.
6. **(Optional)** reranking, citation extraction, evaluation.

## Q11.4: What's the retriever?

The component that takes a query and returns relevant chunks. In our project: `OpenSearchClient.search_chunks_hybrid`.

## Q11.5: What is "grounding"?

Forcing the LLM to answer from provided context, not its training data. Done via prompt: *"Answer ONLY using the following context. If the context doesn't contain the answer, say so."*

## Q11.6: How do you handle hallucination?

- **Grounding prompt** — instruct LLM to use only provided context.
- **Citations** — require LLM to cite chunks; if no chunk cited, suspicious.
- **Confidence filtering** — drop retrieval results below a score threshold.
- **Eval** — measure groundedness with LLM-as-judge or RAGAS-style metrics.

## Q11.7: What's the chunk-to-LLM prompt look like?

```
System: You are a research assistant. Answer ONLY from the following context.
Cite arxiv_ids in [brackets].

Context:
[chunk 1 text] (arxiv_id: 1706.03762)
[chunk 2 text] (arxiv_id: 1810.04805)
...

Question: {user query}
```

## Q11.8: How do you handle "I don't know"?

Two ways:
1. **Prompt the LLM** — instruct it to say "I couldn't find this in the indexed papers" if context is insufficient.
2. **Retrieval threshold** — if no chunks score above 0.5, return a "no results" response without calling the LLM.

## Q11.9: How would you evaluate retrieval quality?

- **Recall@K** — does the relevant chunk appear in top K?
- **MRR (Mean Reciprocal Rank)** — average of `1/rank` of first relevant result.
- **NDCG** — relevance-weighted ranking metric.

Requires labeled query-chunk pairs (manually curated or LLM-generated).

## Q11.10: How would you evaluate generation quality?

- **RAGAS:** faithfulness (is answer supported by context), answer relevance, context precision.
- **LLM-as-judge:** GPT-4 scores answers on a rubric.
- **Human eval** for high-stakes cases.

## Q11.11: What is "naive RAG" vs "advanced RAG"?

- **Naive:** single retrieve → single generate. What we built.
- **Advanced:** query rewriting, multiple retrievals, reranking, self-correction loops, multi-step reasoning. Usually built with LangGraph.

## Q11.12: When does RAG fail?

- Query phrased very differently from indexed content (vector helps but not perfectly).
- Answer requires synthesizing across many docs (single retrieval may miss).
- Question is about something not in the index (LLM should say "I don't know").
- Chunks are too small to contain full context.

## Q11.13: How would you add reranking?

After retrieval, pass top-50 chunks to a cross-encoder reranker (e.g., Cohere Rerank, BGE-reranker). Reranker scores query-chunk pairs more accurately than bi-encoder embeddings. Keep top-5 after reranking.

## Q11.14: What's hybrid search's role in RAG?

Better recall. Vector catches paraphrases; BM25 catches exact terms. Together: fewer relevant chunks missed → better generation quality.

## Q11.15: How does the LLM cite sources in your design?

Each chunk has an arxiv_id. We pass `[arxiv_id: ...]` in the prompt context. The LLM is instructed to wrap citations in brackets. We parse the bracketed IDs from the answer and link to the original PDFs.

---

# 12. Agentic AI

## Q12.1: What is an agent?

An LLM that can take multiple steps, use tools, decide what to do next. Not just one input → one output.

## Q12.2: How is an agent different from a single LLM call?

Single call: input → output, one-shot. Agent: loop. Reads state, picks action, executes, sees result, picks next action, until done.

## Q12.3: What is LangGraph?

Library for building stateful, multi-step LLM workflows as graphs. Nodes are functions, edges are control flow, state passes between them.

## Q12.4: Why LangGraph over plain LangChain chains?

LangChain chains are linear. LangGraph supports loops, branches, conditional steps — needed for retries, query rewriting, grading, multi-tool orchestration.

## Q12.5: What is tool calling?

Letting the LLM decide to invoke a function instead of just generating text. Pass tool definitions in the prompt; LLM returns structured calls; your code executes them.

```
User: "What's the latest cs.AI paper?"
LLM: { "tool": "search_papers", "args": {"category": "cs.AI", "latest": true} }
Your code runs the tool → feeds result back → LLM summarizes
```

## Q12.6: What's an agent's state?

The accumulated context across steps. Usually: original query, retrieved chunks, intermediate decisions, draft answer. Pydantic model or TypedDict.

```python
class AgentState(TypedDict):
    query: str
    chunks: List[Chunk]
    answer: str
    iteration: int
```

## Q12.7: What's a node in LangGraph?

A function that takes state, returns updated state. Each node does one thing — retrieve, grade, generate, rewrite.

## Q12.8: How does branching work in LangGraph?

Edges can be conditional. After a "grade chunks" node, an edge function decides: if grades are good → go to "generate"; if not → go to "rewrite query."

## Q12.9: What would your agent do?

Simple v1: retrieve → generate. Linear, no LangGraph state machine.

Advanced v2: query rewrite → retrieve → grade chunks → if bad, rewrite again (max 2 iterations) → generate → cite → return. LangGraph-based.

## Q12.10: What's a ReAct agent?

Reasoning + Acting. LLM thinks ("I should search for X"), acts (calls search tool), observes (sees results), repeats until done. Pattern from a 2022 paper.

## Q12.11: When NOT to use an agent?

When a single LLM call suffices. Agents add latency (multiple calls), cost, and failure modes (infinite loops if not bounded). Use them only for multi-step problems.

## Q12.12: How do you bound agent iterations?

Max iteration limit. After N steps, force the agent to produce a final answer or return "couldn't answer."

## Q12.13: What's tool-use vs function-calling?

Same concept, different naming:
- **OpenAI:** "function calling."
- **Anthropic, LangChain:** "tool use."

Both: structured way for the LLM to request external function executions.

## Q12.14: How do you handle tool errors?

Tool returns an error string in the result. The LLM sees it and can react (retry, switch tools, give up gracefully). Critical: don't crash the agent on tool errors — feed errors back as observations.

## Q12.15: What's the agentic future of this project?

- Query rewriter (rephrase ambiguous user queries).
- Reranker after retrieval.
- Multi-step research (compare two papers).
- Source citation extractor.
- Self-correction loop (verify the answer is supported by chunks).

---

# 13. Airflow & Orchestration

## Q13.1: What is Apache Airflow?

Open-source workflow orchestrator. Python-defined DAGs of tasks, scheduling, retries, observability, web UI.

## Q13.2: What is a DAG?

Directed Acyclic Graph. Tasks (nodes) connected by directional dependencies (edges) with no cycles.

## Q13.3: What is a task?

A unit of work in a DAG. In Python: a `PythonOperator` wrapping a function. Can also be `BashOperator`, `SQLOperator`, etc.

## Q13.4: What is the Airflow scheduler?

A daemon that decides when to run DAGs based on their `schedule` and current time. Spawns task instances when prerequisites are met.

## Q13.5: What's the Airflow executor?

Component that actually runs tasks. Local (single machine), Celery (distributed via Redis/RabbitMQ), Kubernetes (each task in a pod). We use LocalExecutor.

## Q13.6: What is XCom?

Cross-Communication. Small key-value pairs stored in Airflow's metadata DB, used to pass data between tasks.

```python
ti.xcom_push(key="fetch_results", value=results)
# in another task:
results = ti.xcom_pull(task_ids="fetch_daily_papers", key="fetch_results")
```

## Q13.7: Why is idempotency important in Airflow?

Tasks retry on failure. Same input can run multiple times. Idempotent operations produce the same end state regardless. Without idempotency, retries cause duplicates or corruption.

## Q13.8: How does retry work in Airflow?

DAG defaults: `retries`, `retry_delay`, `retry_exponential_backoff`. On task failure, Airflow waits and retries up to N times.

```python
default_args = {"retries": 2, "retry_delay": timedelta(minutes=30)}
```

## Q13.9: What is backfill?

Running a DAG for past scheduled dates. Used for new pipelines or recovering from outages.

```bash
airflow dags backfill arxiv_paper_ingestion --start-date 2026-05-20 --end-date 2026-05-28
```

## Q13.10: What is `catchup`?

When you create a DAG with `start_date=X` in the past, should Airflow run it for every missed date? `catchup=False` skips backfill on DAG creation. `catchup=True` runs everything from start_date to now.

## Q13.11: How do you pass data between tasks?

XCom for small data (counts, IDs, status). For large data: write to S3/blob storage, pass the path via XCom.

## Q13.12: How does Airflow handle dependencies?

`a >> b` = b runs after a succeeds. `a >> [b, c]` = b and c run in parallel after a. `[a, b] >> c` = c runs after both.

## Q13.13: What is `max_active_runs`?

Cap on concurrent DAG runs. `max_active_runs=1` means only one instance of this DAG runs at a time. We use this to avoid arxiv rate limits.

## Q13.14: What is a sensor?

A task that waits for an external condition. E.g., `FileSensor` waits for a file to appear; `HttpSensor` waits for an endpoint to respond. Pollers, basically.

## Q13.15: How does scheduling work?

`schedule="0 6 * * 1-5"` = cron expression (6 AM UTC, Mon-Fri). Also: `@daily`, `@hourly`, presets. Or a `timedelta`. Or `None` for manual only.

## Q13.16: How would you scale Airflow?

- Switch to CeleryExecutor or KubernetesExecutor for distributed tasks.
- Separate metadata DB on dedicated Postgres.
- Worker autoscaling.
- Use TaskFlow API for cleaner DAGs.

## Q13.17: How is your DAG structured?

```
setup → fetch_daily_papers → index_papers_hybrid → verify_hybrid_index → generate_daily_report → cleanup_temp_files
```

Linear; each task depends on the previous. Daily schedule, Mon-Fri 6 AM UTC.

## Q13.18: What's the difference between `execution_date` and `data_interval_start`?

Old Airflow: `execution_date` = the start of the data window the run covers.
Newer: `data_interval_start` and `data_interval_end` make this explicit.

Common confusion: a daily run with `execution_date=2026-06-08` is the run *for* June 8th — but it runs *on* June 9th (after the data interval closes).

## Q13.19: How do you debug a failed task?

1. Airflow UI → click the task → "Log" tab.
2. CLI: `docker exec rag-airflow airflow tasks logs <dag_id> <task_id> <run_id>`.
3. Re-run locally: `airflow tasks test <dag_id> <task_id> <date>`.

## Q13.20: How does the DAG handle arxiv rate limits?

ArxivClient has internal rate-limit logic (sleep 3 sec between requests). But cumulative requests across runs can still trigger 429. Airflow's retry policy handles this — wait 30 min, try again.

---

# 14. arXiv & PDF Parsing

## Q14.1: What is arxiv?

Open-access repository of academic preprints — millions of papers in physics, CS, math, etc. Free API (`export.arxiv.org/api/query`).

## Q14.2: What's their rate limit?

~1 request per 3 seconds. Aggressive bursts trigger 429. Our client respects this internally; cumulative across runs can still hit it.

## Q14.3: How do you handle 429?

Exponential backoff retry. Airflow's task retry handles persistent 429s by waiting 30 minutes. Don't auto-retry harder — makes it worse.

## Q14.4: What is Docling?

IBM's structure-aware PDF parser. Multimodal model trained on academic papers. Returns text + sections + tables + figures as structured Python objects.

## Q14.5: Why Docling over PyPDF / pdfplumber?

PyPDF returns one big text blob — no structure. Docling preserves sections (Intro/Method/Results), tables, figures. Critical for section-aware chunking.

## Q14.6: What's slow about Docling?

First run downloads ~1GB of ML model weights. Per-paper parsing takes 5-30 seconds depending on length. Heavier than text-only parsers, but vastly better output.

## Q14.7: How do you cache parsed PDFs?

Store the file locally in `/opt/airflow/data/arxiv_pdfs/` (mapped to host `./data/arxiv_pdfs/` via Docker volume). PDF cache is checked first; download only on miss.

We do NOT cache the *parsed* output — parsing is cheap relative to downloading + indexing.

## Q14.8: What if a PDF fails to parse?

Catch `PDFParsingException`, log, skip the paper, continue with the next. One bad PDF shouldn't kill the whole batch. Our notebook now retries with the next paper in the candidate list.

## Q14.9: Can Docling handle non-English PDFs?

Yes, but quality varies by language and document layout. For arxiv (mostly English academic format), it's excellent.

## Q14.10: What about scanned PDFs (images)?

Docling supports OCR via `do_ocr=True` setting. OFF by default because OCR is slow and most arxiv PDFs are digital-born (already have selectable text).

---

# 15. Docker & Infrastructure

## Q15.1: What is Docker?

Containerization platform. Packages app + dependencies + system libs into portable images that run identically anywhere.

## Q15.2: What's the difference between image and container?

- **Image:** the blueprint (read-only).
- **Container:** a running instance of an image (writable).

Many containers can run from one image, like many processes from one executable.

## Q15.3: What is a Dockerfile?

Recipe for building an image. Each line is a step: pick a base image, copy files, install deps, define entrypoint.

```dockerfile
FROM python:3.12-slim
COPY . /app
RUN pip install -r /app/requirements.txt
CMD ["uvicorn", "src.main:app"]
```

## Q15.4: What is Docker Compose?

Tool for defining multi-container apps in YAML. One file describes all services + networks + volumes; `docker compose up` brings them all up.

## Q15.5: What's in our docker-compose.yml?

- `postgres` — DB.
- `airflow` — orchestration.
- `opensearch` + `opensearch-dashboards` — search.
- `redis` — Airflow Celery (or future caching).
- `langfuse-*` — observability stack.

## Q15.6: What is a Docker volume?

Persistent storage that survives container restarts. Two types:
- **Named volume:** managed by Docker (e.g., `postgres_data`).
- **Bind mount:** maps a host directory into the container (e.g., `./data:/opt/airflow/data`).

## Q15.7: Why does the Postgres container have a volume?

So data survives container restarts. Without it, `docker compose down` would wipe the database.

## Q15.8: What is a Docker network?

Virtual network connecting containers. Containers on the same network reach each other by service name (`opensearch:9200`).

## Q15.9: Why does `localhost:9200` work from your Mac but not from inside a container?

`localhost` inside a container is the container itself — not the host. Use `host.docker.internal` to reach the host from inside a container, or use the Docker service name to reach another container.

## Q15.10: Why is `opensearch:9200` invalid from your Mac?

`opensearch` is a Docker DNS name resolvable only inside the Docker network. From your Mac (outside), use `localhost:9200` (the forwarded port).

## Q15.11: How do you start only specific services?

```bash
docker compose up -d postgres opensearch
```

Docker Compose honors `depends_on` to start prerequisites automatically.

## Q15.12: What's `depends_on`?

Tells Docker Compose to start service A before service B. Can use `condition: service_healthy` to wait for healthchecks.

```yaml
airflow:
  depends_on:
    postgres:
      condition: service_healthy
```

## Q15.13: What is a healthcheck?

A command Docker runs periodically to check if a container is "healthy." Used by `depends_on: condition: service_healthy`.

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:9200/_cluster/health"]
  interval: 30s
```

## Q15.14: What is `.env`?

A file with key-value pairs that Docker Compose reads automatically. Used for secrets and per-environment config. Don't commit production secrets.

## Q15.15: What's `docker compose up -d`?

`-d` = detached mode. Containers run in the background. Without `-d`, the terminal stays attached to the container logs.

## Q15.16: What's `docker compose down -v`?

`-v` = also remove volumes. Wipes all data. Without `-v`, volumes persist after stopping.

## Q15.17: How do you debug a container?

- `docker logs <container>` — view logs.
- `docker exec -it <container> bash` — shell into a running container.
- `docker compose ps` — see status.

## Q15.18: What's the difference between EXPOSE and ports?

- **EXPOSE** (Dockerfile): documentation only — says "this image listens on this port."
- **ports** (compose): actually forwards host port → container port (`8080:8080`).

## Q15.19: How would you deploy this to production?

- Push images to a registry (ECR, GHCR).
- Use Kubernetes or AWS ECS for orchestration.
- Managed services for stateful pieces: RDS for Postgres, OpenSearch Service for OS, MWAA for Airflow.
- Secrets via Secrets Manager / KMS, not `.env`.
- Logging to CloudWatch / Datadog.

## Q15.20: What's the smallest Docker image you could use?

`python:3.12-slim` (~120 MB) or `python:3.12-alpine` (~50 MB). Alpine is smallest but musl libc can break some Python packages. `slim` is the safe default.

---

# 16. System Design & Scaling

## Q16.1: How would you scale this to 1M papers?

- Postgres: partition by year, add indexes on `arxiv_id` and `published_date`.
- OpenSearch: multi-node cluster, sharding (5-10 shards), replicas (1-2).
- Embeddings: batch larger jobs, possibly use GPU-backed local model.
- Airflow: switch to CeleryExecutor with multiple workers.

## Q16.2: How would you handle 10K queries/second?

- Cache layer: Redis caching common query results.
- Replicas for OpenSearch (read scaling).
- Read replicas for Postgres.
- Load balancer in front of FastAPI (N instances behind nginx or ALB).
- Async streaming for LLM responses (better perceived latency).

## Q16.3: Where's the bottleneck right now?

For the current scale (hundreds of papers), Docling parsing dominates. At larger scale: embedding API latency, LLM call latency, OpenSearch indexing throughput.

## Q16.4: How do you handle a corrupted paper in the pipeline?

`MetadataFetcher.fetch_and_process_papers` uses `asyncio.gather(return_exceptions=True)` — exceptions become results. Failed papers logged + skipped. Successful papers still committed. Airflow task succeeds with partial results.

## Q16.5: How do you make the indexing idempotent?

- Postgres upsert (by `arxiv_id`).
- OpenSearch `_id` = `arxiv_id_chunk_index`. Re-indexing same chunk overwrites instead of duplicating.

## Q16.6: How would you add real-time ingestion?

Replace daily Airflow DAG with:
- Webhook or polling for new arxiv papers (sub-hour).
- Stream into a queue (Kafka, SQS).
- Worker consumer processes papers as they arrive.
- Same downstream (chunk → embed → index).

## Q16.7: How do you keep the search index in sync with Postgres?

Currently: indexing task reads from Postgres, writes to OpenSearch. Risk: drift if OpenSearch fails partially.

Better: change-data-capture (CDC) from Postgres → Kafka → OpenSearch indexer. Or periodic full reconcile.

## Q16.8: How would you cache search results?

Redis. Key = hash of (query, filters, search mode). Value = JSON results. TTL = 1 hour or whatever's tolerable.

```python
@cache.cached(ttl=3600)
def search(query, ...): ...
```

## Q16.9: How would you do A/B testing on the retrieval strategy?

- Run two strategies in parallel (e.g., BM25-only vs hybrid).
- Log query + chosen results + user feedback (click-through).
- Compare aggregated metrics.
- Feature flag to switch strategies per user/percentage.

## Q16.10: What metrics would you monitor in production?

- Latency: p50, p95, p99 of `/search`, `/ask`.
- Error rate per endpoint.
- LLM API latency + error rate.
- OpenSearch indexing throughput.
- Daily ingestion success rate.
- Search result quality (CTR, eval scores).

## Q16.11: How would you handle PII / privacy?

- Encrypt at rest (DB, object storage).
- Encrypt in transit (TLS).
- Audit logs for access.
- Role-based access control on the API.
- Regular security review.

Not relevant for arxiv (public data) but real for legal/medical RAG.

## Q16.12: What's the cost at 100K papers / 10K queries per day?

Rough estimate:
- Embedding 100K papers: ~$30 one-time.
- Daily ingestion (~50 new papers/day): ~$0.10/day.
- Query embeddings: 10K × 100 tokens × $0.02/1M = ~$0.02/day.
- LLM (gpt-4o-mini for /ask): 10K × ~3K tokens × $0.15/1M = ~$4.50/day.
- OpenSearch hosting: ~$50-100/month managed.
- Total: ~$5-10/day for queries + ~$50-100/month infrastructure.

## Q16.13: How would you do canary deployments?

- New version goes to 5% of traffic.
- Watch error rates + latencies.
- Gradually shift to 50%, 100%.
- Auto-rollback on anomalies.

In FastAPI + Kubernetes: use Istio or Argo Rollouts.

## Q16.14: How would you handle multi-tenancy?

- Per-tenant index (separate OpenSearch index per customer).
- Or shared index with tenant_id field + filter on every query.
- Per-tenant API keys.
- Per-tenant rate limits.

## Q16.15: What if OpenSearch goes down?

Search fails. Two mitigations:
1. Graceful degradation — return cached results or "search unavailable" message.
2. Multi-region OpenSearch deployment for HA.

---

# 17. Trade-offs & Design Choices

## Q17.1: Why OpenAI embeddings over local?

- **Pros of OpenAI:** simple (API), high quality, fast at small scale, cheap per token.
- **Cons:** vendor lock-in, network latency, cost at scale, data leaves your infra.

For learning + small scale, OpenAI wins. For privacy/scale: switch to local sentence-transformers or BGE.

## Q17.2: Why Postgres AND OpenSearch?

Postgres = source of truth (transactions, strong consistency).
OpenSearch = derived search index (denormalized, search-optimized).

Could you use just one? OpenSearch alone: no transactions, weaker consistency. Postgres alone: no fast full-text + vector search.

## Q17.3: Why FastAPI over Flask?

Type-hint driven, async native, auto-docs, better performance. Flask is fine for simple stuff but you'd build a lot of FastAPI's batteries-included features yourself.

## Q17.4: Why Airflow over cron?

Cron = "run X at time Y." Airflow = retries, dependencies, backfill, observability, web UI, dynamic DAGs. For real pipelines, the gap is huge.

## Q17.5: Why hybrid search over pure vector?

Vector alone misses exact-term matches ("BERT" → returns related pre-training papers, might miss the actual BERT paper). BM25 alone misses paraphrases. Hybrid covers both.

## Q17.6: Why section-aware chunking?

Sections are semantic units. Cutting mid-paragraph loses context. Better retrieval → better generation. Worth the ~150 extra lines of code.

## Q17.7: Why split DAG into per-concern files?

- Easier to read and modify per concern.
- Cleaner git diffs.
- Per-file ownership (in a team).

Cost: slight overhead, more imports. Worth it for projects with 5+ tasks.

## Q17.8: Why `@lru_cache` over module-level globals?

Lazy initialization, easier testing (clear cache between tests), no work at import time.

## Q17.9: Why custom chunker over LangChain?

LangChain ignores section structure (it splits flat text). Throwing away Docling's structured output would waste the parser's value. Custom 200-line section-aware splitter > generic library.

## Q17.10: Why repository pattern over Active Record?

- Active Record (Django-style): models contain query methods directly (`Paper.objects.upsert(...)`).
- Repository: separate class holds queries.

Repository is more testable (mock the repo), more aligned with SOLID (single responsibility — model is data, repo is queries). Active Record is more convenient.

## Q17.11: Why Pydantic v2 over v1?

v2 is 5-50× faster, stricter validation, better error messages, modern type-hint support. v1 is deprecated.

## Q17.12: Why typed settings (Pydantic) over raw `os.environ`?

- Type validation (catch "SECRET=abc" when an int was expected).
- Defaults declared in one place.
- IDE autocomplete.
- Single source of truth.

## Q17.13: Why TextChunker as a class, not a function?

It has state (`chunk_size`, `overlap_size`, `min_chunk_size`) shared across methods. A class is the natural way to encapsulate that. Functions with 3 kwargs every call would be uglier.

## Q17.14: Why composable services over a monolith?

- Each service is testable in isolation.
- Swap implementations (Jina ↔ OpenAI ↔ local) without changing consumers.
- Reuse: same `ArxivClient` is used by the DAG + the notebook + (future) admin tools.

## Q17.15: Why async over multiprocessing?

Our work is I/O-bound (network calls). Async is more efficient than multiprocessing for I/O (no process overhead) and easier to reason about. Multiprocessing makes sense for CPU-bound work, which we don't have.

---

# 18. Production & Operations

## Q18.1: How do you log?

Standard Python `logging` module. INFO for normal events, WARNING for recoverable issues, ERROR for failures. Middleware logs every HTTP request.

## Q18.2: How would you add structured logging?

Use `python-json-logger` or `structlog` to output JSON logs:
```
{"timestamp": "...", "level": "INFO", "request_id": "abc", "endpoint": "/search", "duration_ms": 23}
```
Easier to parse with Loki, Datadog, etc.

## Q18.3: How would you add observability for the LLM calls?

Langfuse (already a dependency). Wraps OpenAI calls to log:
- Input/output text.
- Token counts.
- Latency.
- Cost.
- Custom traces across agentic flows.

## Q18.4: How would you trace a request across services?

OpenTelemetry — adds a trace ID to each request, propagates it through FastAPI → OpenSearch → LLM calls. View the full request graph in Jaeger or Datadog APM.

## Q18.5: How would you handle secrets?

- **Dev:** `.env` file (gitignored).
- **Prod:** AWS Secrets Manager / Vault. Inject as env vars at container start.

NEVER commit secrets. Use `.env.example` with placeholders for documentation.

## Q18.6: How would you handle DB schema migrations in production?

Alembic. Each schema change = a migration script. Apply in order during deploy. Reversible.

`Base.metadata.create_all()` is fine for first creation but doesn't handle alterations.

## Q18.7: What's the CI/CD setup?

(Not yet implemented but planned:)
- GitHub Actions: lint → typecheck → unit tests → build container → push to registry.
- Deploy via ArgoCD or similar GitOps tool.

## Q18.8: How would you test the chunker?

Unit tests with concrete inputs:
- Empty text → returns `[]`.
- Text below `min_chunk_size` → single chunk.
- Long text → multiple chunks with correct overlap.
- Sections of various sizes → correct merging.

## Q18.9: How would you test FastAPI endpoints?

`TestClient(app)` — synchronous client. For async tests: `httpx.AsyncClient(app=app, base_url="http://test")`. Test happy path + edge cases + error paths.

## Q18.10: How would you load-test the API?

`locust` or `k6` — define user behavior (random queries from a corpus), ramp up users, watch latency + error rate. Identify breaking point.

## Q18.11: How do you handle backups?

- **Postgres:** `pg_dump` daily to S3. Test restore quarterly.
- **OpenSearch:** snapshots to S3 daily.
- Code in git is its own "backup."

## Q18.12: How would you do disaster recovery?

- RPO (Recovery Point Objective): max acceptable data loss.
- RTO (Recovery Time Objective): max acceptable downtime.

Backup strategy + multi-region deployment + tested restore procedures. The "tested" part is what most teams skip.

## Q18.13: What metrics define success?

- **Reliability:** uptime, error rate.
- **Performance:** p95 latency.
- **Quality:** retrieval recall, answer faithfulness (RAG-specific).
- **Adoption:** queries per day, retention.
- **Cost:** $/query, $/paper indexed.

## Q18.14: How would you handle a runaway LLM call (infinite tokens)?

- Set `max_tokens` on every OpenAI call.
- Set per-request timeout.
- Per-user rate limit.
- Daily budget cap (e.g., $5/user/day).

## Q18.15: What's the lifecycle of a paper in your system?

```
Day 0:  arxiv API → ArxivClient.fetch_papers → returns metadata
Day 0:  PDF downloaded to /opt/airflow/data/
Day 0:  Docling parses → PdfContent (sections, tables, raw_text)
Day 0:  PaperRepository.upsert → row in `papers` table
Day 0:  Chunker splits paper → 20 chunks
Day 0:  Embedder embeds chunks → 20 × 1024-dim vectors
Day 0:  bulk_index_chunks → 20 docs in OpenSearch
Day N:  User asks question
Day N:  Query embedded → opensearch.search_chunks_hybrid → top-5 chunks
Day N:  LLM with chunks as context → answer + citations
```

---

# QUICK INTERVIEW DRILLS

Cover the answer, recite out loud:

| Question | One-line answer |
|---|---|
| What is RAG? | Retrieve relevant chunks → ground LLM in them. Fixes hallucination + freshness + private data. |
| Why hybrid search? | BM25 catches exact terms; vector catches paraphrases. Fused via RRF for best coverage. |
| What is RRF? | Reciprocal Rank Fusion: score = sum of 1/(60+rank) per doc per list. No tuning, no normalization. |
| Why chunk papers? | Embedding quality, retrieval precision, LLM context limits. Section-aware > fixed-width. |
| What's an inverted index? | Word → list of docs containing it. Foundation of full-text search. |
| What is BM25? | TF-IDF with doc-length normalization. Default keyword ranking. |
| What is HNSW? | Approximate nearest-neighbor algo. 1% recall loss for 100× speedup. |
| Why `must` vs `filter`? | `must` is scored (ranks); `filter` is yes/no (cacheable, faster, no scoring). |
| What is `app.state`? | Per-app storage living for server lifetime. Set in lifespan, read via request.app.state.x. |
| Why DI in FastAPI? | Routes declare what they need; FastAPI injects from app.state. Clean, testable, no per-request construction. |
| What is the repository pattern? | One class per entity owns all DB queries. Routes/services use it, not raw SQL. |
| Why upsert? | Idempotent writes. Pipelines retry; without upsert, retries cause duplicate-key errors. |
| What is a singleton? | One instance per app. Python: `@lru_cache(maxsize=1)` on a factory function. |
| Why factory pattern? | Centralized construction. Callers call `make_X()`, don't know about config/wiring. |
| What is SQLAlchemy? | Python's main ORM. Maps classes to SQL tables; generates queries from object ops. |
| What is async/await? | I/O-bound concurrency without threads. `await` yields during I/O; event loop runs other tasks. |
| What is asyncio.gather? | Run N coroutines concurrently, wait for all, get results in order. |
| What is XCom? | Airflow's cross-task data passing. Small key-value pairs in metadata DB. |
| What is idempotency? | Operation produces same result no matter how many times it runs. Critical for pipelines that retry. |
| What is backfill? | Re-run a DAG for past dates. Used for new pipelines or recovering missed runs. |
| Why Postgres + OpenSearch? | Postgres = source of truth (transactions). OpenSearch = derived search index (denormalized). |
| What is Docker Compose? | Multi-container app definition in YAML. `docker compose up` brings up the whole stack. |
| What is a Docker volume? | Persistent storage that survives container restarts. Named volume or bind mount. |
| Why is `opensearch:9200` invalid from Mac? | Docker DNS only works inside the network. From host: use `localhost:9200` (forwarded port). |
| What is middleware? | Code that runs around every request. Cross-cutting concerns: logging, auth, timing. |
| What is OpenAPI? | Machine-readable API description. FastAPI auto-generates it. Powers Swagger UI, Postman, SDK generators. |
| What is Pydantic? | Type-driven data validation. Define classes with type-hinted fields; auto-validate on construction. |
| What is `ConfigDict`? | Pydantic v2's model configuration. Replaces `class Config:` from v1. |
| What is `json_schema_extra`? | Attaches example values to a model's JSON schema. Shows in FastAPI's /docs "Try it out." |
| What is `from_` (underscore)? | Avoids the Python `from` keyword. Use `alias="from"` to map back to standard JSON name. |
| What is Docling? | IBM's structure-aware PDF parser. Returns sections, tables, figures — not just flat text. |
| Why 1024 dims not 1536? | Matryoshka representation. 33% smaller index, ~4% quality loss. Faster kNN. |
| Why batch embeddings? | Network round-trips dominate. One call with N inputs = N× faster than N calls. |
| What's a session? | SQLAlchemy's unit of work. Stage changes in memory; commit them atomically. Auto-rollback on exception. |
| What is `lifespan`? | FastAPI's startup/shutdown context manager. Build singletons before serving; tear down at exit. |
| What is a router? | Modular collection of routes. Split big APIs into files; mount via `app.include_router(...)`. |
| What is a Pydantic field alias? | Alternate name for a field. Used for JSON/Python keyword conflicts (`from_` ↔ `"from"`). |
| Why LangGraph over LangChain chains? | Chains are linear. LangGraph supports loops, branches, multi-step state machines. Needed for real agents. |
| What's the retriever in RAG? | Component that takes a query → returns chunks. Ours: `opensearch.search_chunks_hybrid`. |
| What is grounding? | Forcing the LLM to answer from provided context. Done via prompt instruction. |

---

# 60-SECOND PROJECT PITCH

> "I built an end-to-end production RAG pipeline for arXiv research papers. A daily Apache Airflow DAG fetches new papers, parses them with Docling for structured sections, chunks them section-aware (~600 words with 100-word overlap), embeds with OpenAI text-embedding-3-small reduced to 1024 dims, and indexes each chunk into OpenSearch with both BM25-searchable text fields and a `knn_vector` field for semantic search. Search is hybrid — BM25 + k-NN fused via native RRF pipeline. A FastAPI service exposes `/search` and `/ask`; the `/ask` endpoint runs a LangGraph agent that retrieves top-K chunks and grounds an LLM with them, returning answers with arxiv_id citations. Built with async I/O throughout, SQLAlchemy + Postgres as source of truth, repository pattern for data access, factory-pattern singletons for services, Docker Compose for the full stack, and idempotent upserts for retry-safe pipelines."

Practice this until you can recite it without thinking.

---

# HOW TO USE THIS SHEET

1. **First pass:** Read top to bottom once. Don't try to memorize.
2. **Daily drills:** Pick 5-10 questions randomly. Cover the answer. Say the interview line out loud.
3. **Add as you go:** When a new question comes up in an interview, add it here with your answer.
4. **Mock interviews:** Have a friend pick 10 random questions; you answer cold.
5. **Test recall after 1 week:** if you can recite 80%+ without looking, you're interview-ready.

Good luck.
