# `src/services/embeddings/` — Text embeddings

Turns text into **vectors** — fixed-size lists of floats that capture the
"meaning" of the text. Vectors are what enable semantic search in
OpenSearch (the `embedding` field on each chunk doc).

Backed by **OpenAI** (`text-embedding-3-small` by default), accessed via
the official async SDK.

---

## Files

```
embeddings/
├── openai_client.py    ← OpenAIEmbeddingsClient (the work)
├── factory.py          ← make_openai_embeddings_client() (cached constructor)
└── __init__.py
```

| File | Defines | Role |
|---|---|---|
| `openai_client.py` | `OpenAIEmbeddingsClient` | Async wrapper around the OpenAI SDK. Two public methods: `embed_text`, `embed_batch`. Auto-batches large inputs. |
| `factory.py` | `make_openai_embeddings_client()` | `@lru_cache` singleton constructor — reads settings from `config.py`. |

---

## How it works

### The single public surface

```python
class OpenAIEmbeddingsClient:
    async def embed_text(self, text: str) -> List[float]: ...
    async def embed_batch(self, texts: List[str]) -> List[List[float]]: ...
```

Two methods, by intent:

- **`embed_text`** — convenience wrapper for "I have one string, give me one vector."
- **`embed_batch`** — the real workhorse. Takes N strings, returns N vectors, same order.

`embed_text` just calls `embed_batch([text])` and returns the first result.
All API logic lives in `embed_batch` (DRY).

### Auto-batching

OpenAI's API accepts **up to 2048 input strings per request**, but very
long inputs can push the payload past size/time limits sooner. To stay
safe, `embed_batch` splits its input into sub-batches of
`settings.batch_size` (default 100) and makes one API call per sub-batch:

```python
for i in range(0, len(texts), batch_size):
    batch = texts[i : i + batch_size]
    response = await self._client.embeddings.create(
        model=self.settings.model,
        input=batch,
        dimensions=self.settings.dimensions,
    )
    all_vectors.extend(item.embedding for item in response.data)
```

So you can call `client.embed_batch(texts)` with 5000 strings and it just
works — it transparently makes 50 API calls. Returned vectors are in the
same order as input.

### Why async?

Every method is `async def` so it composes with the rest of the pipeline
(`metadata_fetcher.fetch_and_process_papers`, the upcoming indexing task)
which uses `asyncio.gather` for concurrent I/O. Embedding 1000 chunks
across 10 papers can happen in parallel rather than sequentially.

### The factory

```python
@lru_cache(maxsize=1)
def make_openai_embeddings_client(...) -> OpenAIEmbeddingsClient:
    if settings is None:
        settings = get_settings().openai_embeddings
    return OpenAIEmbeddingsClient(settings=settings)
```

Same pattern as `make_arxiv_client`, `make_pdf_parser_service`,
`make_opensearch_client` — **singleton via `@lru_cache(maxsize=1)`**. The
function takes no required arguments, so the cache holds exactly one
instance per process. Cheap to call repeatedly.

The reason to cache: the `AsyncOpenAI` client maintains a connection pool
and retry state. You want one instance, not a new pool per call.

---

## Configuration

All knobs live in `OpenAIEmbeddingsSettings` in [`src/config.py`](../../config.py):

| Setting | Default | What it controls |
|---|---|---|
| `model` | `text-embedding-3-small` | Which OpenAI model. Could switch to `text-embedding-3-large` (3072 native dims) if you want higher quality. |
| `dimensions` | `1024` | Output vector size. **Must match the OpenSearch index config** (`index_config_hybrid.py` has `"dimension": 1024`). |
| `batch_size` | `100` | How many inputs per API call. Lower = more requests; higher = bigger requests. 100 is a safe middle ground. |
| `max_retries` | `3` | SDK auto-retries this many times on transient errors. |
| `timeout_seconds` | `30.0` | Per-request timeout. |

Plus one env var, used directly by the OpenAI SDK (not by our settings
class):

```
OPENAI_API_KEY=sk-...        # required — read by the SDK from the environment
```

To override settings via `.env`:

```
OPENAI_EMBEDDINGS__MODEL=text-embedding-3-large
OPENAI_EMBEDDINGS__DIMENSIONS=1536        # remember to update the OS index too!
OPENAI_EMBEDDINGS__BATCH_SIZE=200
```

---

## Why 1024 dimensions when OpenAI's native is 1536?

Two reasons:

1. **Matches the existing OpenSearch index.** `arxiv-papers-chunks` was
   configured for 1024-dim vectors (originally for Jina v3). Changing
   dims means dropping and recreating the index, plus re-indexing
   everything.
2. **Quality loss is minimal.** OpenAI explicitly designed the v3 models
   to allow dimension reduction — they say it preserves "most" of the
   semantic quality. Reduction is done server-side via the `dimensions`
   parameter on the API call.

If you ever want to switch to native 1536:

1. Change `dimensions: int = 1024` → `1536` in `OpenAIEmbeddingsSettings`.
2. Change `"dimension": 1024` → `1536` in `index_config_hybrid.py`.
3. Call `client.setup_indices(force=True)` to drop and recreate the
   OpenSearch index.
4. Re-index all papers.

---

## Dependencies

**Imports from:**

- `src.config.OpenAIEmbeddingsSettings` — typed settings.
- `src.config.get_settings` — used by the factory.
- External: `openai` (the official Python SDK).

**Imported by (planned):**

- The Airflow `indexing` task (when wired up) — embeds chunk texts before
  passing them to OpenSearch.
- A `HybridIndexingService` (if you build the orchestrator pattern from
  the course) — composes chunker + embeddings + opensearch client.

---

## Cost rough estimate

`text-embedding-3-small` is $0.02 per 1M tokens. Some math:

- An average arxiv chunk is ~500 words ≈ **~700 tokens**.
- One paper produces ~20 chunks → **~14,000 tokens per paper**.
- Embedding **1000 papers** ≈ **14M tokens** → **~$0.28**.

So for the whole course you'll spend cents, not dollars. The cheapest
part of the stack.

---

## Common questions

**"Can I use a local model instead?"** — Yes. Add a sibling file like
`sentence_transformers_client.py` exposing the same `embed_text` /
`embed_batch` interface. Update the factory (or add a second factory) to
return whichever backend you want based on a config flag. The chunker
and indexer don't care which one's behind the interface.

**"Why no `api_key` field in `OpenAIEmbeddingsSettings`?"** — The OpenAI
SDK reads `OPENAI_API_KEY` from the environment automatically. Putting
it in our settings too would duplicate it and risk drift. Cleaner to let
the SDK handle the key directly.

**"Why split `embed_text` and `embed_batch` if `embed_text` just wraps
`embed_batch`?"** — `embed_text` reads better at call sites that
naturally have one string ("embed this query before searching"). The
implementation stays DRY because all API logic is in `embed_batch`.

**"What if OpenAI is down?"** — The SDK retries up to `max_retries`
times with exponential backoff for transient errors (5xx, rate limits).
After that, the exception bubbles up to the caller. The pipeline will
fail the affected paper; Airflow's retry policy can re-run the task.
