# `src/services/` — Business logic and external integrations

Everything that *does work* (calls an external API, parses a PDF, indexes
to OpenSearch, runs the pipeline) lives here. The layers below
(`db/`, `models/`, `repositories/`, `schemas/`) provide infrastructure;
this layer composes that infrastructure into actual features.

---

## Layout

```
services/
├── metadata_fetcher.py     ← ★ the orchestrator
├── arxiv/                  ← arxiv API client (see arxiv/README.md)
├── pdf_parser/             ← Docling-backed PDF parsing (see pdf_parser/README.md)
└── opensearch/             ← search index client + query builder (see opensearch/README.md)
```

Each sub-folder is a self-contained service with the same shape:

```
<service>/
├── client.py    ← the class that does the work
├── factory.py   ← make_<service>() singleton constructor
└── ...          ← supporting types/configs for that service
```

This consistent shape means once you've read one service, you can navigate
any of them.

---

## The orchestrator: `metadata_fetcher.py`

This is the **hub** that ties every other service together. It's the only
file at the top level of `services/` (not in a sub-folder) because it
doesn't belong to one domain — it composes all of them.

### What it does

`MetadataFetcher.fetch_and_process_papers(...)` is the end-to-end pipeline:

```
1. Call ArxivClient        → fetch N paper metadata records
2. For each paper, concurrently:
     - download_pdf()       → PDF on disk
     - PDFParserService.parse_pdf()
                            → structured PdfContent (sections, text, tables)
3. Build PaperCreate per paper (metadata + parsed content)
4. PaperRepository.upsert(...)
                            → write to Postgres (idempotent)
5. Return stats dict       → {papers_fetched, pdfs_downloaded, papers_stored, errors, ...}
```

### How the concurrency works

`fetch_and_process_papers` uses `asyncio.gather` to download and parse PDFs
in parallel, with semaphores throttling concurrency:

```python
download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)  # default 5
parse_semaphore    = asyncio.Semaphore(self.max_concurrent_parsing)    # default 2
```

This is why everything in the pipeline (`ArxivClient.download_pdf`,
`PDFParserService.parse_pdf`, the wrapper task in the DAG) is `async`. The
single Airflow task fans out into dozens of concurrent network operations.

### What gets injected

The factory `make_metadata_fetcher(arxiv_client, pdf_parser)` takes the two
services as **parameters** rather than building them inside. This is
dependency injection — it lets you mock them in tests, share singletons
across tasks, and reuse a single ArxivClient (which has a rate limiter
that has to track state across calls).

The database is *not* injected at constructor time — the caller passes a
session per call (`db_session=session`), because each DAG task needs its
own transaction scope.

---

## Dependencies

**This folder imports from:**

- `src.config` — every factory pulls settings from here.
- `src.exceptions` — every service raises domain exceptions defined in
  one place.
- `src.repositories.paper.PaperRepository` — the orchestrator's write path.
- `src.schemas.arxiv.paper`, `src.schemas.pdf_parser.models` — input/output
  types.

**This folder is imported by:**

- `airflow/dags/arxiv_ingestion/common.py` — calls every `make_*` factory.
- Notebooks — for manual experiments with each service.

---

## The factory pattern

Every service has a `factory.py` with this shape:

```python
@lru_cache(maxsize=1)
def make_<service>() -> <Service>:
    settings = get_settings()
    return <Service>(...settings...)
```

Why `lru_cache(maxsize=1)`?

- The function takes no arguments → only one possible result → caches once
  and reuses forever.
- Effective singleton — Airflow tasks all get the same client instance
  rather than building a new one each time (which would create a new
  connection pool, re-initialize Docling, etc.).
- `make_pdf_parser_service()` is especially important to cache —
  initializing Docling downloads ML models on first call (minutes!).

Callers never construct `ArxivClient` or `PDFParserService` directly. They
go through the factory. The factory is the single seam where dependencies
get wired up.

---

## Adding a new service

If you add e.g. `services/embeddings/`, follow the shape:

1. `embeddings/client.py` — the class that does the work.
2. `embeddings/factory.py` — `make_embeddings_client()` with `@lru_cache`.
3. `embeddings/README.md` — what it does, what it imports, who imports it.
4. Wire into `metadata_fetcher.py` if it joins the pipeline, OR into the
   Airflow task if it's a separate step (e.g. indexing).

Keep one concern per folder. Don't dump unrelated code into an existing
service.
