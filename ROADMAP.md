# Research Assistant Roadmap

**Goal:** turn the current RAG system into an agentic research assistant —
one solid, deep project over 2-3 months, not several shallow ones.

**Status as of start:** backend complete through week 7 of the course
(ingestion, hybrid search, cache, agentic RAG with guardrail/grade/rewrite,
LangSmith tracing + feedback, chat UI). Everything below is new scope.

**Total estimate:** ~13 weeks (~3 months), part-time.

---

## Phase 1 — Conversational Memory (Weeks 1-2)

**Problem today:** every `/ask` and `/agentic_ask` call is stateless. Follow-up
questions ("how many heads did they use?") fail because the backend never
sees prior turns — only `thread_id` exists, stamped as LangSmith metadata,
never actually used for context.

**Build:**
- `ConversationStore` service (`src/services/conversation/`) — Redis-backed,
  same shape as your existing `CacheClient`. `get_history(thread_id)`,
  `append_turn(thread_id, human, ai)`, TTL-based expiry.
- Server-side history (not client-resent) — keyed by `thread_id`, which you
  already generate per page-load in the UI.
- Question-condensing step — reuses the `QueryRewriteOutput` pattern: given
  history + a follow-up, produce a standalone query before retrieval.
- Context window management — once history exceeds ~N turns, roll old turns
  into an LLM-generated summary rather than truncating blindly.
- Wire into both routers: load history via `thread_id` → condense → existing
  pipeline unchanged from there.

**Success criteria:** "What is multi-head attention?" → "How many heads did
they use?" resolves correctly. Condensed query visible in the LangSmith trace.

---

## Phase 2 — Multi-Tool Agent + Live Corpus Fetch (Weeks 3-6)

**Problem today:** the agent has exactly one tool (`retrieve_papers`), and
the corpus is fixed to whatever the daily DAG happened to fetch. Ask about a
topic outside that window and the agent has no way to fill the gap.

**Build — new tools** (`src/services/agents/tools.py`):
- `summarize_paper(arxiv_id)` — full-paper summary from stored `raw_text`,
  not just top-k chunks.
- `compare_papers(arxiv_ids: list)` — retrieves per-paper, generates a
  structured comparison.
- `list_by_topic(topic, limit)` — lightweight metadata-only search
  (title/abstract), no full RAG generation needed.
- `fetch_live_papers(topic)` — **the corpus-gap-filler.** Reuses existing
  `ArxivClient` → `PDFParserService` → `HybridIndexingService` pipeline,
  triggered synchronously by the agent instead of the daily DAG.

**Build — graph changes:**
- Tool-selection routing — either an explicit routing node (structured
  output, same pattern as `RoutingDecision`) or LangGraph's `create_react_agent`
  style with multiple tools bound to one LLM call.
- Extend the existing rewrite-loop: after N rewrite attempts still fail →
  route to `fetch_live_papers` → re-retrieve → generate. Same "try harder"
  pattern you already built, one level up (whole-corpus scope, not just
  query-phrasing scope).

**Build — live-fetch specifics (the hard part):**
- Query translation: natural language → arXiv API search syntax (`all:`,
  `abs:`, category filters) — an LLM step, same shape as `rewrite_query_node`.
- Rate-limit guard: cap live-fetch to once per thread per session (arXiv
  bans at ~1 req/3s cumulative — already documented in CLAUDE.md gotcha #3).
- Latency: Docling parsing is 10-30s/paper: fetching+indexing 3-5 papers is
  1-3 minutes. v1: accept the blocking call, surface progress via
  `reasoning_steps`. Stretch: SSE streaming of status to the UI.

**Success criteria:** "compare BERT and GPT approaches" correctly invokes
`compare_papers`, not the default retriever. A query on a topic verifiably
absent from the corpus triggers live fetch, corpus grows, retry succeeds.

**Note:** the daily Airflow DAG stays as-is — broad, scheduled corpus
building. Live-fetch is a separate, narrow, on-demand supplement. Don't
merge them.

---

## Phase 3 — Eval Harness (Weeks 7-8)

**Problem today:** no quantified answer to "is this RAG system actually
good?" — the single highest-leverage gap for interviews, and the phase most
portfolios skip.

**Build:**
- Eval dataset — pull 👎/👍 feedback from LangSmith via API, plus ~30-50
  hand-written golden Q&A pairs covering: clean queries, vague queries,
  off-topic queries, comparison queries, live-fetch-triggering queries.
- Retrieval metrics — recall@k, MRR against a labeled "correct arxiv_id"
  set, run against `/hybrid_search`.
- Answer-quality metrics — LLM-as-judge scoring for groundedness (is the
  answer supported by retrieved chunks) and relevance. Structured output,
  same pattern as `GradeDocuments`.
- Regression harness — one script/notebook that re-runs the full eval set
  against `/ask` and `/agentic_ask`, produces a scorecard. Re-run after any
  prompt or model change to catch regressions.
- Optional: upload the golden set as a LangSmith Dataset, use their eval SDK
  (you already have the UI for this — `Datasets & Experiments` tab).

**Success criteria:** one command produces a scorecard (recall@k,
groundedness %, off-topic refusal rate). Re-run after Phase 2 changes,
confirm no regression from the added multi-tool complexity.

---

## Phase 4 — Personalization (Weeks 9-10)

**Problem today:** zero memory across sessions — every user is a stranger
every time.

**Build:**
- Lightweight identity — persistent `user_id` via browser-generated UUID
  (same pattern as `thread_id`), not a full auth system. Auth is its own
  project; not the point here.
- `UserProfile` (Postgres) — `user_id`, rolling interest embedding (average
  or list of past query embeddings), timestamps.
- Update on every query — append/blend the query embedding into the
  profile's interest vector.
- `GET /api/v1/recommendations?user_id=...` — vector-search the corpus
  using the profile's interest embedding, return unseen papers.
- UI — a "Papers you might like" panel using this endpoint.

**Success criteria:** after several transformer-related questions,
recommendations surface transformer-related papers over unrelated ones.

---

## Phase 5 — Proactive Digest (Weeks 11-12)

**Problem today:** fully reactive — the system never surfaces anything
unless asked.

**Build:**
- New Airflow task, `generate_daily_digest`, running after daily ingestion —
  for each user profile, find newly-ingested papers matching their interest
  vector, LLM-summarize top 3, store in a `digests` table.
- UI — a digest panel/notification on load ("3 new papers matching your
  interests since your last visit").
- Stretch (likely out of scope given time budget): email digest via
  SES/SendGrid — flag as a "could extend to" line, not a build target.

**Success criteria:** after a DAG run ingests new papers, a user with
tracked interests sees a digest referencing genuinely new, relevant papers.

---

## Phase 6 — Deploy + Polish (Week 13 / buffer)

**Problem today:** Docker Compose on a laptop isn't a demo-able artifact.

**Build:**
- Cloud deployment — pick one: Fly.io/Railway (simplest, good for a demo
  link) vs AWS (more "real" for infra-heavy interviews, more setup work).
  **Decision needed before this phase** — see open questions below.
- README overhaul — architecture diagram, demo GIF, live link if deployed
  publicly.
- Final interview-prep pass reflecting the new capabilities.

**Success criteria:** a stranger can open a URL and use the assistant
without you running anything locally.

---

## Sequencing logic (why this order)

1. **Memory before multi-tool** — tool-selection agents behave badly without
   conversation context ("compare them" needs to know what "them" is).
2. **Eval before personalization** — once you start recommending things, you
   need a way to know if recommendations are actually good. Eval
   infrastructure should exist first.
3. **Deploy last** — polish and packaging come after substance.

## Open questions to resolve before Phase 6

- Cloud target: Fly.io/Railway vs AWS — affects how OpenSearch gets hosted
  (self-host on a small VM vs managed alternative).
- Whether email digest is in scope or explicitly cut.

## Working agreement

- One phase at a time. Each phase gets its own success criteria checked
  before moving on — no half-finished phases carried forward.
- Re-run the Phase 3 eval harness after every phase from 4 onward, to catch
  regressions from added complexity.
