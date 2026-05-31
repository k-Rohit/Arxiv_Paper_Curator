# QueryBuilder — What Each Method Does in OpenSearch Terms

This file walks through `query_builder.py` purely from the **OpenSearch side**:
what each method produces, what those JSON keys mean to OpenSearch, and why
each option exists.

> The class's job is one thing: **produce a JSON dict that OpenSearch's
> `_search` endpoint understands.** Each method builds one slice of that dict.

---

## The shape it produces

After `qb.build()`, you get a dict roughly like this:

```json
{
  "query": {
    "bool": {
      "must":   [ ...text-search clause(s)... ],
      "filter": [ ...filter clause(s)... ]
    }
  },
  "size": 10,
  "from": 0,
  "track_total_hits": true,
  "_source": { ... },
  "highlight": { ... },
  "sort": [ ... ]
}
```

Map of which method builds which key:

| Top-level key       | Built by                  |
| ------------------- | ------------------------- |
| `query.bool`        | `_build_query`            |
| `query.bool.must[]` | `_build_text_query`       |
| `query.bool.filter[]` | `_build_filters`        |
| `size`, `from`      | direct from `self.size`, `self.from_` |
| `track_total_hits`  | direct from `self.track_total_hits` |
| `_source`           | `_build_source_fields`    |
| `highlight`         | `_build_highlight`        |
| `sort`              | `_build_sort`             |

`build()` is just the glue that assembles everything.

---

## Method walkthrough

### `build()` — the outer envelope

Produces the top-level dict. Every search request to OpenSearch needs at
minimum a `query` block — everything else is optional but useful.

Notable behavior: `sort` is only added if `_build_sort()` returns something.
Many OpenSearch requests don't include `sort`, in which case results come
back ordered by relevance score (highest first), which is what you usually
want.

---

### `_build_query()` — the `bool` query

OpenSearch's `bool` query is the standard wrapper for combining multiple
clauses. It has four slots:

| Slot       | Effect on score     | Effect on matching         |
| ---------- | ------------------- | -------------------------- |
| `must`     | Contributes to score | Doc MUST match              |
| `should`   | Contributes to score | Optional (OR-like)          |
| `must_not` | No score            | Doc MUST NOT match          |
| `filter`   | **No score**        | Doc MUST match (yes/no)     |

This file uses just **`must` and `filter`** — the most common pair.

**Why split them?**

- `must` = "this is part of the search query — rank by it." A `multi_match`
  for the user's text goes here.
- `filter` = "yes/no restriction, doesn't affect ranking." Category filter,
  date range, "only published papers," etc. go here.

Putting filters in `filter` instead of `must` is faster (OpenSearch can cache
filter results) and avoids polluting the relevance score.

**The fallback when there's no query text:**

```python
if must_clauses:
    bool_query["must"] = must_clauses
else:
    bool_query["must"] = [{"match_all": {}}]
```

`match_all` is OpenSearch's "return everything" query. The code uses it as a
fallback so that browsing by filters alone (e.g. "show all cs.AI papers
sorted by date") still works.

---

### `_build_text_query()` — `multi_match`

This is **the heart of the BM25 text search.** It produces:

```json
{
  "multi_match": {
    "query": "transformer architectures",
    "fields": ["chunk_text^3", "title^2", "abstract^1"],
    "type": "best_fields",
    "operator": "or",
    "fuzziness": "AUTO",
    "prefix_length": 2
  }
}
```

Each option:

- **`query`** — the text to search for (literal user input).
- **`fields`** — which fields to look in. The `^N` is a **boost**: a hit in
  `chunk_text` is worth 3× a hit in `abstract`. Boosts let you encode "the
  title matters more than the body."
- **`type: "best_fields"`** — when one term matches multiple fields, take the
  score from the single best-matching field, not the sum. Standard for short
  text searches (titles, queries). Other options: `most_fields` (sum scores),
  `cross_fields` (treat fields as one big concatenation).
- **`operator: "or"`** — at least ONE term must match. Use `"and"` for stricter
  "all terms must match." For RAG-style search, `or` gives more recall.
- **`fuzziness: "AUTO"`** — typo tolerance. "attenton" still matches
  "attention". `AUTO` adjusts based on word length (more tolerant for longer
  words). Can also be `0`, `1`, `2` for fixed edit distance.
- **`prefix_length: 2`** — the first 2 characters must match exactly. Prevents
  fuzziness from going wild on short queries (e.g. `cat` matching `bat`).

---

### `_build_filters()` — the `terms` filter

Produces a list of filter clauses. Currently only category filter, but the
list structure makes it easy to add date ranges, etc.

```json
[
  { "terms": { "categories": ["cs.AI", "cs.LG"] } }
]
```

Two related OpenSearch clauses to know:

| Clause | Use when… | Example |
|---|---|---|
| `term`  | matching ONE exact value | `{"term": {"category": "cs.AI"}}` |
| `terms` | matching ANY of several values (OR) | `{"terms": {"category": ["cs.AI","cs.LG"]}}` |

Both work only on **`keyword`** fields, not on analyzed `text` fields. That's
why your index config defines `"categories": {"type": "keyword"}` — so it
can be filtered exactly without tokenization.

**Why these go in `filter` instead of `must`:** filters don't compute a
relevance score, OpenSearch can cache the result of "give me all docs in
cs.AI", and they're MUCH faster. Always put yes/no restrictions in `filter`.

---

### `_build_source_fields()` — what comes back in results

Controls the `_source` field in each returned hit. Two patterns here:

**Paper mode** (`search_chunks=False`):
```json
["arxiv_id", "title", "authors", "abstract", "categories", "published_date", "pdf_url"]
```

This is an **include list** — return ONLY these fields. Useful when the doc
has tons of fields and you only want a few.

**Chunk mode** (`search_chunks=True`):
```json
{ "excludes": ["embedding"] }
```

This is an **exclude list** — return everything EXCEPT `embedding`.

Why? Each chunk doc has a 1024-dim vector in `embedding`. You don't want
OpenSearch shipping 1024 floats back per hit when you just want to display
results to a user. `excludes` strips it before sending.

You can also use `"_source": false` to return NO fields (just `_id` and
`_score`) — useful when you only need to know which docs matched, not their
content.

---

### `_build_highlight()` — wrap matched terms with `<mark>` tags

Highlighting is OpenSearch generating **snippets of the matched text with
the matching terms wrapped in HTML tags**. Frontend can then render them
bold/yellow.

Example response when you search for "attention":

```json
"highlight": {
  "title": [ "<mark>Attention</mark> Is All You Need" ],
  "abstract": [ "...uses an <mark>attention</mark> mechanism to..." ]
}
```

Options the file uses:

- **`fields`** — which fields to highlight. Each field can have its own config.
- **`fragment_size`** — how many characters per snippet. `0` = return the
  whole field (used for short fields like `title`).
- **`number_of_fragments`** — how many snippets to return. `0` for whole
  field, otherwise N snippets max.
- **`pre_tags` / `post_tags`** — the HTML markers. Default is `<em>` /
  `</em>`. The code uses `<mark>` / `</mark>` because it semantically means
  "highlighted text."
- **`require_field_match: false`** — highlight even if the term matched in a
  different field. Useful when you search across multiple fields but want
  the matched word highlighted everywhere it appears.

The chunk-mode and paper-mode configs differ because chunks are short
(highlight everything) while papers have a long abstract (only 1-3 snippets
of 150 chars each).

---

### `_build_sort()` — order of results

Returns either `None` (let OpenSearch sort by relevance), or a list of sort
criteria.

**Three behaviors:**

1. If `latest_papers=True`: sort by `published_date` desc, with `_score` as
   tiebreaker.
2. If `query` text is empty (browsing mode): same as above — sort by date.
3. Otherwise: return `None` → OpenSearch sorts by `_score` desc by default.

A sort clause looks like:

```json
[
  { "published_date": { "order": "desc" } },
  "_score"
]
```

This means: "sort by `published_date` newest first; for docs with the same
date, fall back to relevance score." Multi-field sort is just a list — first
field wins, ties broken by next field.

`_score` is OpenSearch's special "current relevance score" sort key. Useful
as a tiebreaker after a date sort.

---

## OpenSearch concepts cheat sheet

A short reference for the DSL keywords this file uses:

| Keyword | What it does |
|---|---|
| `bool` | Wraps multiple query clauses with `must`/`should`/`must_not`/`filter` |
| `must` | Clause that contributes to score AND must match |
| `filter` | Yes/no clause that doesn't contribute to score (fast, cacheable) |
| `match_all` | Matches every document |
| `multi_match` | Search the same text across multiple fields |
| `term` / `terms` | Exact value match (single / list) — for `keyword` fields |
| `_source` | The original JSON of the doc; can be filtered with include/exclude |
| `track_total_hits` | If `true`, returns exact hit count; if `false` (default), caps at 10000 for speed |
| `from` / `size` | Offset and page size for pagination |
| `sort` | List of sort criteria; `_score` for relevance |
| `highlight` | Generate snippets with matched terms wrapped in tags |
| `fields` (in highlight) | Per-field highlight config |

---

## End-to-end example

```python
qb = QueryBuilder(
    query="attention mechanism",
    size=5,
    categories=["cs.AI"],
    search_chunks=True,
)
body = qb.build()
```

Produces:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "attention mechanism",
            "fields": ["chunk_text^3", "title^2", "abstract^1"],
            "type": "best_fields",
            "operator": "or",
            "fuzziness": "AUTO",
            "prefix_length": 2
          }
        }
      ],
      "filter": [
        { "terms": { "categories": ["cs.AI"] } }
      ]
    }
  },
  "size": 5,
  "from": 0,
  "track_total_hits": true,
  "_source": { "excludes": ["embedding"] },
  "highlight": {
    "fields": {
      "chunk_text": { "fragment_size": 150, "number_of_fragments": 2, "pre_tags": ["<mark>"], "post_tags": ["</mark>"] },
      "title":      { "fragment_size": 0, "number_of_fragments": 0, "pre_tags": ["<mark>"], "post_tags": ["</mark>"] },
      "abstract":   { "fragment_size": 150, "number_of_fragments": 1, "pre_tags": ["<mark>"], "post_tags": ["</mark>"] }
    },
    "require_field_match": false
  }
}
```

Translating this dict back into English:

> "Search for documents where `chunk_text`, `title`, or `abstract` matches
> 'attention mechanism' (with typo tolerance), AND the doc's `categories`
> field contains 'cs.AI'. Boost matches in `chunk_text` 3×, `title` 2×.
> Return the top 5 results sorted by relevance, including all fields except
> the 1024-dim embedding. For each hit, give me up to 2 highlighted snippets
> from `chunk_text`, 1 from `abstract`, and the full highlighted title."

---

## What this file does NOT do

Even though it lives in the hybrid-search package, this class builds only
the **BM25 (lexical) half** of a search. There's no `knn` query for vector
search, no RRF fusion. Those live elsewhere — typically in `client.py`,
which:

1. Calls `QueryBuilder.build()` for the BM25 query body.
2. Separately builds a `knn` query block using the query's embedding vector.
3. Sends both to OpenSearch in one request with `?search_pipeline=hybrid-rrf-pipeline`.
4. OpenSearch fuses the two ranked lists using the RRF post-processor you
   defined in `index_config_hybrid.py`.

So mentally:

```
QueryBuilder.build()    ← BM25 half (this file)
embed(query_text)       ← user text → vector
{ "knn": { ... } }      ← vector half (built in client.py)
        ↓
client.hybrid_search()  ← sends both, OpenSearch applies RRF pipeline
```

`QueryBuilder` is the focused, well-tested "produce the BM25 query body"
component. Everything else is composition around it.
