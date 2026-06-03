# `src/services/arxiv/` — arxiv API client

Talks to the arxiv API. Fetches paper metadata and downloads PDFs. Handles
rate limiting, retries, and the local PDF cache.

---

## Files

```
arxiv/
├── client.py    ← ArxivClient (the work)
└── factory.py   ← make_arxiv_client() (the cached constructor)
```

| File | Defines | Purpose |
|---|---|---|
| `client.py` | `ArxivClient` | Async client for arxiv search + PDF download |
| `factory.py` | `make_arxiv_client()` | `@lru_cache`d singleton constructor |

---

## What `ArxivClient` does

Two public async methods that drive everything:

### `fetch_papers(...) -> List[ArxivPaper]`

Hits the arxiv API's `/api/query` endpoint. Used by the orchestrator to get
N most recent papers in a category and date range.

Internally:

1. Builds a query URL like:
   `?search_query=cat:cs.AI AND submittedDate:[202605290000 TO 202605292359]&max_results=15&sortBy=submittedDate&sortOrder=descending`
2. Issues an async HTTP GET.
3. Parses the returned Atom XML using `xmltodict` into `ArxivPaper`
   instances.
4. Returns the list.

### `download_pdf(paper, force_download=False) -> Optional[Path]`

For a given `ArxivPaper`, downloads its PDF to the local cache directory.

Internally:

1. Builds the cache path from `pdf_cache_dir` (config) + a safe filename
   derived from `arxiv_id`.
2. If the file already exists and `force_download=False` — returns the
   cached path immediately (no network call).
3. Otherwise, downloads with exponential-backoff retry.
4. Returns the local `Path`.

### Rate limiting (important)

arxiv enforces a 1-request-per-3-seconds rate limit and bans aggressively.
The client respects this internally:

```python
if time_since_last_req < self.rate_limit_delay:
    sleep_time = self.rate_limit_delay - time_since_last_req
    await asyncio.sleep(sleep_time)
```

There's a similar delay between PDF downloads. If you hit a 429 anyway,
it's almost always because of **cumulative requests across multiple runs**
in a short window (notebook testing + Airflow triggers) — not a bug in
this client.

---

## The factory

```python
@lru_cache(maxsize=1)
def make_arxiv_client() -> ArxivClient:
    settings = get_settings()
    return ArxivClient(settings.arxiv)
```

Singleton. Cached for the lifetime of the process. The cache matters here
because the rate-limiter state lives **on the instance** — if you built a
fresh client every call, you'd reset the "last request time" and slam
arxiv with bursts.

---

## Configuration (what comes from `config.py`)

`settings.arxiv` controls everything tunable:

| Setting | Default | Purpose |
|---|---|---|
| `api_base_url` | `https://export.arxiv.org/api/query` | API endpoint |
| `max_results` | `15` | How many papers per fetch |
| `default_categories` | `["cs.AI"]` | Default category filter |
| `pdf_cache_dir` | `./data/arxiv_pdfs` | Where PDFs land |
| `rate_limit_delay` | `3.0` | Seconds between API calls |
| `download_max_retries` | `3` | Retry budget per PDF |
| `download_retry_delay_base` | `5.0` | Exponential backoff base |
| `max_concurrent_downloads` | `5` | Throttles concurrent downloads |
| `download_timeout` | (set per request) | Per-request timeout |

---

## Dependencies

**Imports from:**

- `src.config.ArxivSettings` — typed settings.
- `src.exceptions` — `ArxivAPIException`, `ArxivAPITimeoutError`,
  `ArxivAPIRateLimitError`, `ArxivParseError`, `PDFDownloadException`,
  `PDFDownloadTimeoutError`. Specific exception types so callers can
  handle each case differently.
- `src.schemas.arxiv.paper.ArxivPaper` — the parsed output type.
- External: `httpx` (async HTTP), `xmltodict` (XML → dict).

**Imported by:**

- `src.services.metadata_fetcher` — calls both methods in the pipeline.
- `airflow/dags/arxiv_ingestion/common.py` — calls `make_arxiv_client()`.
- Notebooks — for manual exploration.

---

## Common questions

**"Why is the PDF cache directory `./data/arxiv_pdfs`? Where does that
land in Docker?"** — Inside the Airflow container, the CWD is
`/opt/airflow`, so the cache writes to `/opt/airflow/data/arxiv_pdfs/`.
That path is mounted to `./data/arxiv_pdfs/` on your host via
`docker-compose.yml`, so cached PDFs persist on your Mac and survive
container restarts.

**"Why does fetching the same date twice in a row 429 me?"** — arxiv
counts cumulative requests over a sliding window per IP. Within a single
run the client respects the 3s rule, but if you triggered a DAG run, then
ran a notebook cell, then triggered again, you've burned through the
budget. Wait a few minutes and try again — there's no code fix needed.

**"How do I add a new search query (e.g. filter by author)?"** — Modify
the URL building in `fetch_papers`. arxiv's query syntax is documented at
the arxiv API docs page.
